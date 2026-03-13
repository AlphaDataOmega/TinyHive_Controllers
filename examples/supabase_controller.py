"""
Supabase Controller for TinyHive

A controller for interacting with Supabase REST API and Storage.

Method IDs:
  controller.supabase.{profile}.select
  controller.supabase.{profile}.insert
  controller.supabase.{profile}.update
  controller.supabase.{profile}.delete
  controller.supabase.{profile}.upsert
  controller.supabase.{profile}.rpc
  controller.supabase.{profile}.upload_file
  controller.supabase.{profile}.list_buckets

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "project_ref": "your-project-ref",
    "api_key_env": "SUPABASE_API_KEY",
    "service_role_key_env": "SUPABASE_SERVICE_ROLE_KEY"
}

Or with direct values (not recommended for production):
{
    "project_ref": "your-project-ref",
    "api_key": "your-anon-key",
    "service_role_key": "your-service-role-key"
}

Environment Variables:
---------------------
- SUPABASE_API_KEY: Your Supabase anon/public key
- SUPABASE_SERVICE_ROLE_KEY: Your Supabase service role key (for admin operations)

Base URLs:
---------
- REST API: https://{project_ref}.supabase.co/rest/v1
- Storage API: https://{project_ref}.supabase.co/storage/v1

Dependencies:
------------
None - uses Python standard library only (urllib)
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.supabase")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with Supabase configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available Supabase profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


def _get_credentials(profile: Dict[str, Any], use_service_role: bool = False) -> tuple:
    """
    Get API key and project URL from profile.

    Returns:
        (api_key, base_url) tuple
    """
    project_ref = profile.get("project_ref")
    if not project_ref:
        raise ValueError("Profile must specify 'project_ref'")

    base_url = f"https://{project_ref}.supabase.co"

    # Get API key (prefer service role for admin operations)
    if use_service_role:
        key_env = profile.get("service_role_key_env", "SUPABASE_SERVICE_ROLE_KEY")
        api_key = profile.get("service_role_key") or os.environ.get(key_env)
        if not api_key:
            # Fall back to regular API key
            key_env = profile.get("api_key_env", "SUPABASE_API_KEY")
            api_key = profile.get("api_key") or os.environ.get(key_env)
    else:
        key_env = profile.get("api_key_env", "SUPABASE_API_KEY")
        api_key = profile.get("api_key") or os.environ.get(key_env)

    if not api_key:
        raise ValueError(
            f"No API key found. Set environment variable '{key_env}' or "
            "add 'api_key' to profile."
        )

    return api_key, base_url


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    api_key: str,
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    content_type: str = "application/json",
    timeout: int = DEFAULT_TIMEOUT,
    extra_headers: Optional[Dict[str, str]] = None,
    prefer: Optional[str] = None
) -> Dict[str, Any]:
    """
    Make an authenticated Supabase API call.

    Args:
        api_key: Supabase API key (anon or service role)
        url: Full URL to call
        method: HTTP method
        data: Request body bytes
        content_type: Content-Type header
        timeout: Request timeout in seconds
        extra_headers: Additional headers to include
        prefer: PostgREST Prefer header value

    Returns:
        {"ok": True, "data": ...} or {"ok": False, "error": ...}
    """
    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": content_type,
    }

    if prefer:
        headers["Prefer"] = prefer

    if extra_headers:
        headers.update(extra_headers)

    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                try:
                    result = json.loads(response_body)
                    return {"ok": True, "data": result}
                except json.JSONDecodeError:
                    return {"ok": True, "data": response_body}
            return {"ok": True, "data": None}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message") or error_data.get("error") or error_body[:500]
            if isinstance(error_message, dict):
                error_message = json.dumps(error_message)
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Supabase API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Supabase API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# PostgREST Query Builder Helpers
# =============================================================================

def _build_filter_query(where: Dict[str, Any]) -> str:
    """
    Build PostgREST filter query parameters from a where dict.

    Supports operators:
        eq, neq, gt, gte, lt, lte, like, ilike, is, in, cs, cd, ov, sl, sr, nxl, nxr, adj

    Example:
        {"id": {"eq": 1}} -> "id=eq.1"
        {"name": {"ilike": "%john%"}} -> "name=ilike.%john%"
        {"status": "active"} -> "status=eq.active" (shorthand for eq)
    """
    parts = []
    for column, condition in where.items():
        if isinstance(condition, dict):
            for op, value in condition.items():
                if op == "in":
                    # in operator expects a list
                    if isinstance(value, list):
                        value = f"({','.join(str(v) for v in value)})"
                    parts.append(f"{column}={op}.{value}")
                else:
                    parts.append(f"{column}={op}.{quote(str(value), safe='')}")
        else:
            # Simple equality
            parts.append(f"{column}=eq.{quote(str(condition), safe='')}")
    return "&".join(parts)


def _build_select_query(params: Dict[str, Any]) -> str:
    """Build query string for select operation."""
    query_parts = []

    # Select columns
    select = params.get("select", "*")
    query_parts.append(f"select={quote(select, safe='*,')}")

    # Where filters
    where = params.get("where")
    if where:
        query_parts.append(_build_filter_query(where))

    # Order
    order = params.get("order")
    if order:
        if isinstance(order, list):
            order = ",".join(order)
        query_parts.append(f"order={quote(order, safe=',.')}")

    # Limit
    limit = params.get("limit")
    if limit is not None:
        query_parts.append(f"limit={limit}")

    # Offset
    offset = params.get("offset")
    if offset is not None:
        query_parts.append(f"offset={offset}")

    return "&".join(query_parts)


# =============================================================================
# Database Actions
# =============================================================================

def select(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Query rows from a table.

    Params:
        table (str): Table name (required)
        select (str): Columns to select (default: "*")
        where (dict): Filter conditions, e.g. {"id": {"eq": 1}}
        order (str|list): Order by columns, e.g. "created_at.desc"
        limit (int): Maximum rows to return
        offset (int): Number of rows to skip

    Returns:
        {"ok": True, "data": [...]} or {"ok": False, "error": "..."}
    """
    profile = load_profile(profile_name)
    api_key, base_url = _get_credentials(profile)

    table = params.get("table")
    if not table:
        return {"ok": False, "error": "table is required"}

    query = _build_select_query(params)
    url = f"{base_url}/rest/v1/{quote(table, safe='')}?{query}"

    return _api_call(api_key, url, method="GET")


def insert(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Insert rows into a table.

    Params:
        table (str): Table name (required)
        data (dict|list): Row(s) to insert (required)
        return_data (bool): Return inserted rows (default: True)
        on_conflict (str): Conflict resolution (for upsert behavior)

    Returns:
        {"ok": True, "data": [...]} or {"ok": False, "error": "..."}
    """
    profile = load_profile(profile_name)
    api_key, base_url = _get_credentials(profile)

    table = params.get("table")
    if not table:
        return {"ok": False, "error": "table is required"}

    data = params.get("data")
    if data is None:
        return {"ok": False, "error": "data is required"}

    url = f"{base_url}/rest/v1/{quote(table, safe='')}"

    # Build Prefer header
    prefer_parts = []
    if params.get("return_data", True):
        prefer_parts.append("return=representation")
    else:
        prefer_parts.append("return=minimal")

    prefer = ",".join(prefer_parts) if prefer_parts else None

    body = json.dumps(data).encode("utf-8")

    return _api_call(api_key, url, method="POST", data=body, prefer=prefer)


def update(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update rows in a table.

    Params:
        table (str): Table name (required)
        data (dict): Fields to update (required)
        where (dict): Filter conditions (required for safety)
        return_data (bool): Return updated rows (default: True)

    Returns:
        {"ok": True, "data": [...]} or {"ok": False, "error": "..."}
    """
    profile = load_profile(profile_name)
    api_key, base_url = _get_credentials(profile)

    table = params.get("table")
    if not table:
        return {"ok": False, "error": "table is required"}

    data = params.get("data")
    if data is None:
        return {"ok": False, "error": "data is required"}

    where = params.get("where")
    if not where:
        return {"ok": False, "error": "where is required to prevent accidental full-table updates"}

    filter_query = _build_filter_query(where)
    url = f"{base_url}/rest/v1/{quote(table, safe='')}?{filter_query}"

    # Build Prefer header
    prefer_parts = []
    if params.get("return_data", True):
        prefer_parts.append("return=representation")
    else:
        prefer_parts.append("return=minimal")

    prefer = ",".join(prefer_parts) if prefer_parts else None

    body = json.dumps(data).encode("utf-8")

    return _api_call(api_key, url, method="PATCH", data=body, prefer=prefer)


def delete(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete rows from a table.

    Params:
        table (str): Table name (required)
        where (dict): Filter conditions (required for safety)
        return_data (bool): Return deleted rows (default: False)

    Returns:
        {"ok": True, "data": [...]} or {"ok": False, "error": "..."}
    """
    profile = load_profile(profile_name)
    api_key, base_url = _get_credentials(profile)

    table = params.get("table")
    if not table:
        return {"ok": False, "error": "table is required"}

    where = params.get("where")
    if not where:
        return {"ok": False, "error": "where is required to prevent accidental full-table deletes"}

    filter_query = _build_filter_query(where)
    url = f"{base_url}/rest/v1/{quote(table, safe='')}?{filter_query}"

    # Build Prefer header
    prefer = "return=representation" if params.get("return_data", False) else "return=minimal"

    return _api_call(api_key, url, method="DELETE", prefer=prefer)


def upsert(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upsert (insert or update) rows in a table.

    Params:
        table (str): Table name (required)
        data (dict|list): Row(s) to upsert (required)
        on_conflict (str): Conflict column(s), e.g. "id" or "email,org_id"
        return_data (bool): Return upserted rows (default: True)
        ignore_duplicates (bool): Skip duplicates instead of updating (default: False)

    Returns:
        {"ok": True, "data": [...]} or {"ok": False, "error": "..."}
    """
    profile = load_profile(profile_name)
    api_key, base_url = _get_credentials(profile)

    table = params.get("table")
    if not table:
        return {"ok": False, "error": "table is required"}

    data = params.get("data")
    if data is None:
        return {"ok": False, "error": "data is required"}

    # Build URL with on_conflict parameter
    url = f"{base_url}/rest/v1/{quote(table, safe='')}"

    query_parts = []
    on_conflict = params.get("on_conflict")
    if on_conflict:
        query_parts.append(f"on_conflict={quote(on_conflict, safe=',')}")

    if query_parts:
        url += "?" + "&".join(query_parts)

    # Build Prefer header for upsert
    prefer_parts = ["resolution=merge-duplicates"]

    if params.get("ignore_duplicates", False):
        prefer_parts = ["resolution=ignore-duplicates"]

    if params.get("return_data", True):
        prefer_parts.append("return=representation")
    else:
        prefer_parts.append("return=minimal")

    prefer = ",".join(prefer_parts)

    body = json.dumps(data).encode("utf-8")

    return _api_call(api_key, url, method="POST", data=body, prefer=prefer)


def rpc(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call a stored procedure (RPC function).

    Params:
        function_name (str): Name of the function to call (required)
        params (dict): Parameters to pass to the function (default: {})
        method (str): HTTP method - GET for reads, POST for writes (default: POST)

    Returns:
        {"ok": True, "data": ...} or {"ok": False, "error": "..."}
    """
    profile = load_profile(profile_name)
    api_key, base_url = _get_credentials(profile)

    function_name = params.get("function_name")
    if not function_name:
        return {"ok": False, "error": "function_name is required"}

    rpc_params = params.get("params", {})
    method = params.get("method", "POST").upper()

    url = f"{base_url}/rest/v1/rpc/{quote(function_name, safe='')}"

    if method == "GET":
        # For GET, parameters go in query string
        if rpc_params:
            query = urlencode(rpc_params)
            url += f"?{query}"
        return _api_call(api_key, url, method="GET")
    else:
        # For POST, parameters go in body
        body = json.dumps(rpc_params).encode("utf-8")
        return _api_call(api_key, url, method="POST", data=body)


# =============================================================================
# Storage Actions
# =============================================================================

def upload_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upload a file to Supabase Storage.

    Params:
        bucket (str): Bucket name (required)
        path (str): File path in bucket (required)
        file_content (str|bytes): File content (required)
        content_type (str): MIME type (default: application/octet-stream)
        encoding (str): Content encoding - 'utf-8', 'base64' (default: utf-8)
        upsert (bool): Overwrite if exists (default: False)

    Returns:
        {"ok": True, "data": {"Key": "..."}} or {"ok": False, "error": "..."}
    """
    profile = load_profile(profile_name)
    api_key, base_url = _get_credentials(profile, use_service_role=True)

    bucket = params.get("bucket")
    if not bucket:
        return {"ok": False, "error": "bucket is required"}

    path = params.get("path")
    if not path:
        return {"ok": False, "error": "path is required"}

    file_content = params.get("file_content")
    if file_content is None:
        return {"ok": False, "error": "file_content is required"}

    content_type = params.get("content_type", "application/octet-stream")
    encoding = params.get("encoding", "utf-8")
    upsert = params.get("upsert", False)

    # Handle content encoding
    if isinstance(file_content, str):
        if encoding == "base64":
            data = base64.b64decode(file_content)
        else:
            data = file_content.encode("utf-8")
    else:
        data = file_content

    # Clean path
    path = path.lstrip("/")

    url = f"{base_url}/storage/v1/object/{quote(bucket, safe='')}/{quote(path, safe='/')}"

    extra_headers = {}
    if upsert:
        extra_headers["x-upsert"] = "true"

    return _api_call(
        api_key,
        url,
        method="POST",
        data=data,
        content_type=content_type,
        extra_headers=extra_headers
    )


def list_buckets(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all storage buckets.

    Params:
        None required

    Returns:
        {"ok": True, "data": [{"id": "...", "name": "...", ...}]} or {"ok": False, "error": "..."}
    """
    profile = load_profile(profile_name)
    api_key, base_url = _get_credentials(profile, use_service_role=True)

    url = f"{base_url}/storage/v1/bucket"

    return _api_call(api_key, url, method="GET")


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "select": select,
    "insert": insert,
    "update": update,
    "delete": delete,
    "upsert": upsert,
    "rpc": rpc,
    "upload_file": upload_file,
    "list_buckets": list_buckets,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """
    Main dispatch entry point.

    Called by ControllerDispatch with:
        - profile: The profile name from method_id
        - action: The action name from method_id
        - params: Action parameters

    Returns action result dict.
    """
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action '{action}'. Available: {list(ACTIONS.keys())}"}

    try:
        logger.info(f"Executing supabase.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
