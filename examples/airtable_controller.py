"""
Airtable Controller for TinyHive

A controller for integrating with Airtable REST API.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Airtable profile:
{
    "api_key_env": "AIRTABLE_API_KEY"
}

Required API Token Scopes:
--------------------------
- data.records:read       - For list_records, get_record
- data.records:write      - For create_record, create_records, update_record, delete_record
- schema.bases:read       - For list_bases, get_schema

Method IDs:
  controller.airtable.{profile}.list_records
  controller.airtable.{profile}.get_record
  controller.airtable.{profile}.create_record
  controller.airtable.{profile}.create_records
  controller.airtable.{profile}.update_record
  controller.airtable.{profile}.delete_record
  controller.airtable.{profile}.list_bases
  controller.airtable.{profile}.get_schema

Dependencies:
------------
- None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.airtable")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Airtable API base URL
AIRTABLE_API_BASE = "https://api.airtable.com/v0"

DEFAULT_TIMEOUT = 30


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile from the profiles directory."""
    profile_path = PROFILES_DIR / f"{name}.json"
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {name}")

    with open(profile_path) as f:
        return json.load(f)


def _get_api_key(profile: Dict[str, Any]) -> str:
    """Get the Airtable API key from environment variable."""
    api_key_env = profile.get("api_key_env", "AIRTABLE_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ValueError(
            f"Environment variable '{api_key_env}' not set. "
            "Set your Airtable API key or Personal Access Token in this environment variable."
        )
    return api_key


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    api_key: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated Airtable API call.

    Args:
        api_key: Airtable API key or Personal Access Token
        endpoint: API endpoint path (appended to base URL)
        method: HTTP method (GET, POST, PATCH, DELETE)
        data: Request body as dict (for POST/PATCH)
        params: Query parameters (for GET)
        timeout: Request timeout in seconds

    Returns:
        Response dict with 'ok' field and result/error
    """
    url = f"{AIRTABLE_API_BASE}/{endpoint}"

    # Add query parameters for GET requests
    if params:
        filtered_params = {k: v for k, v in params.items() if v is not None}
        if filtered_params:
            url = f"{url}?{urlencode(filtered_params, doseq=True)}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                result = json.loads(response_body)
                return {"ok": True, "data": result}
            else:
                return {"ok": True, "data": {}}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("error", {}).get("message", error_body[:500])
        except json.JSONDecodeError:
            error_msg = error_body[:500]
        logger.error("Airtable HTTP error %d: %s", e.code, error_msg)
        return {"ok": False, "error": f"HTTP {e.code}: {error_msg}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Airtable API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Record Actions
# =============================================================================

def list_records(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List records from an Airtable table.

    Params:
        base_id (str): The ID of the base (required)
        table_name (str): The name or ID of the table (required)
        fields (list): Only return specific fields (optional)
        filter_formula (str): Airtable formula to filter records (optional)
        max_records (int): Maximum number of records to return (optional)
        sort (list): List of dicts with 'field' and 'direction' (optional)
            e.g., [{"field": "Name", "direction": "asc"}]
        page_size (int): Number of records per page (default: 100, max: 100)
        offset (str): Pagination offset from previous response (optional)
        view (str): Name or ID of a view to use (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response including records list and optional offset
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)

        base_id = params.get("base_id")
        table_name = params.get("table_name")

        if not base_id:
            return {"ok": False, "error": "base_id is required"}
        if not table_name:
            return {"ok": False, "error": "table_name is required"}

        # Build query parameters
        query_params: Dict[str, Any] = {}

        if params.get("fields"):
            # Airtable expects fields[] parameter format
            query_params["fields[]"] = params["fields"]

        if params.get("filter_formula"):
            query_params["filterByFormula"] = params["filter_formula"]

        if params.get("max_records"):
            query_params["maxRecords"] = params["max_records"]

        if params.get("page_size"):
            query_params["pageSize"] = min(params["page_size"], 100)

        if params.get("offset"):
            query_params["offset"] = params["offset"]

        if params.get("view"):
            query_params["view"] = params["view"]

        # Handle sort parameter
        if params.get("sort"):
            for i, sort_item in enumerate(params["sort"]):
                query_params[f"sort[{i}][field]"] = sort_item.get("field")
                if sort_item.get("direction"):
                    query_params[f"sort[{i}][direction]"] = sort_item.get("direction")

        encoded_table = quote(table_name, safe="")
        endpoint = f"{base_id}/{encoded_table}"

        return _api_call(api_key, endpoint, method="GET", params=query_params)

    except Exception as e:
        logger.exception("list_records failed")
        return {"ok": False, "error": str(e)}


def get_record(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a single record from an Airtable table.

    Params:
        base_id (str): The ID of the base (required)
        table_name (str): The name or ID of the table (required)
        record_id (str): The ID of the record (required)

    Returns:
        ok (bool): Success status
        data (dict): Record object with id, fields, and createdTime
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)

        base_id = params.get("base_id")
        table_name = params.get("table_name")
        record_id = params.get("record_id")

        if not base_id:
            return {"ok": False, "error": "base_id is required"}
        if not table_name:
            return {"ok": False, "error": "table_name is required"}
        if not record_id:
            return {"ok": False, "error": "record_id is required"}

        encoded_table = quote(table_name, safe="")
        endpoint = f"{base_id}/{encoded_table}/{record_id}"

        return _api_call(api_key, endpoint, method="GET")

    except Exception as e:
        logger.exception("get_record failed")
        return {"ok": False, "error": str(e)}


def create_record(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a single record in an Airtable table.

    Params:
        base_id (str): The ID of the base (required)
        table_name (str): The name or ID of the table (required)
        fields (dict): Field values for the new record (required)
        typecast (bool): Automatic data conversion (default: false)

    Returns:
        ok (bool): Success status
        data (dict): Created record object with id, fields, and createdTime
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)

        base_id = params.get("base_id")
        table_name = params.get("table_name")
        fields = params.get("fields")

        if not base_id:
            return {"ok": False, "error": "base_id is required"}
        if not table_name:
            return {"ok": False, "error": "table_name is required"}
        if not fields:
            return {"ok": False, "error": "fields is required"}

        payload: Dict[str, Any] = {"fields": fields}

        if params.get("typecast"):
            payload["typecast"] = True

        encoded_table = quote(table_name, safe="")
        endpoint = f"{base_id}/{encoded_table}"

        return _api_call(api_key, endpoint, method="POST", data=payload)

    except Exception as e:
        logger.exception("create_record failed")
        return {"ok": False, "error": str(e)}


def create_records(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Batch create multiple records in an Airtable table.

    Params:
        base_id (str): The ID of the base (required)
        table_name (str): The name or ID of the table (required)
        records (list): List of record objects, each with 'fields' dict (required)
            e.g., [{"fields": {"Name": "Alice"}}, {"fields": {"Name": "Bob"}}]
            Maximum 10 records per request
        typecast (bool): Automatic data conversion (default: false)

    Returns:
        ok (bool): Success status
        data (dict): Response with 'records' list of created records
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)

        base_id = params.get("base_id")
        table_name = params.get("table_name")
        records = params.get("records")

        if not base_id:
            return {"ok": False, "error": "base_id is required"}
        if not table_name:
            return {"ok": False, "error": "table_name is required"}
        if not records:
            return {"ok": False, "error": "records is required"}
        if not isinstance(records, list):
            return {"ok": False, "error": "records must be a list"}
        if len(records) > 10:
            return {"ok": False, "error": "Maximum 10 records per batch request"}

        payload: Dict[str, Any] = {"records": records}

        if params.get("typecast"):
            payload["typecast"] = True

        encoded_table = quote(table_name, safe="")
        endpoint = f"{base_id}/{encoded_table}"

        return _api_call(api_key, endpoint, method="POST", data=payload)

    except Exception as e:
        logger.exception("create_records failed")
        return {"ok": False, "error": str(e)}


def update_record(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update a single record in an Airtable table.

    Params:
        base_id (str): The ID of the base (required)
        table_name (str): The name or ID of the table (required)
        record_id (str): The ID of the record to update (required)
        fields (dict): Field values to update (required)
        typecast (bool): Automatic data conversion (default: false)

    Returns:
        ok (bool): Success status
        data (dict): Updated record object with id, fields, and createdTime
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)

        base_id = params.get("base_id")
        table_name = params.get("table_name")
        record_id = params.get("record_id")
        fields = params.get("fields")

        if not base_id:
            return {"ok": False, "error": "base_id is required"}
        if not table_name:
            return {"ok": False, "error": "table_name is required"}
        if not record_id:
            return {"ok": False, "error": "record_id is required"}
        if not fields:
            return {"ok": False, "error": "fields is required"}

        payload: Dict[str, Any] = {"fields": fields}

        if params.get("typecast"):
            payload["typecast"] = True

        encoded_table = quote(table_name, safe="")
        endpoint = f"{base_id}/{encoded_table}/{record_id}"

        return _api_call(api_key, endpoint, method="PATCH", data=payload)

    except Exception as e:
        logger.exception("update_record failed")
        return {"ok": False, "error": str(e)}


def delete_record(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a single record from an Airtable table.

    Params:
        base_id (str): The ID of the base (required)
        table_name (str): The name or ID of the table (required)
        record_id (str): The ID of the record to delete (required)

    Returns:
        ok (bool): Success status
        data (dict): Response with 'id' and 'deleted' fields
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)

        base_id = params.get("base_id")
        table_name = params.get("table_name")
        record_id = params.get("record_id")

        if not base_id:
            return {"ok": False, "error": "base_id is required"}
        if not table_name:
            return {"ok": False, "error": "table_name is required"}
        if not record_id:
            return {"ok": False, "error": "record_id is required"}

        encoded_table = quote(table_name, safe="")
        endpoint = f"{base_id}/{encoded_table}/{record_id}"

        return _api_call(api_key, endpoint, method="DELETE")

    except Exception as e:
        logger.exception("delete_record failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Base/Schema Actions
# =============================================================================

def list_bases(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all bases accessible to the authenticated user.

    Params:
        offset (str): Pagination offset from previous response (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response with 'bases' list and optional 'offset'
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)

        query_params: Dict[str, Any] = {}

        if params.get("offset"):
            query_params["offset"] = params["offset"]

        # Note: list bases uses the meta API endpoint
        url = "https://api.airtable.com/v0/meta/bases"

        if query_params:
            url = f"{url}?{urlencode(query_params)}"

        headers = {
            "Authorization": f"Bearer {api_key}",
        }

        try:
            req = Request(url, headers=headers, method="GET")
            with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
                response_body = response.read().decode("utf-8")
                result = json.loads(response_body)
                return {"ok": True, "data": result}

        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            try:
                error_json = json.loads(error_body)
                error_msg = error_json.get("error", {}).get("message", error_body[:500])
            except json.JSONDecodeError:
                error_msg = error_body[:500]
            logger.error("Airtable HTTP error %d: %s", e.code, error_msg)
            return {"ok": False, "error": f"HTTP {e.code}: {error_msg}"}

    except Exception as e:
        logger.exception("list_bases failed")
        return {"ok": False, "error": str(e)}


def get_schema(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the schema (tables and fields) for a base.

    Params:
        base_id (str): The ID of the base (required)

    Returns:
        ok (bool): Success status
        data (dict): Response with 'tables' list containing table schemas
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)

        base_id = params.get("base_id")

        if not base_id:
            return {"ok": False, "error": "base_id is required"}

        # Note: get schema uses the meta API endpoint
        url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"

        headers = {
            "Authorization": f"Bearer {api_key}",
        }

        try:
            req = Request(url, headers=headers, method="GET")
            with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
                response_body = response.read().decode("utf-8")
                result = json.loads(response_body)
                return {"ok": True, "data": result}

        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            try:
                error_json = json.loads(error_body)
                error_msg = error_json.get("error", {}).get("message", error_body[:500])
            except json.JSONDecodeError:
                error_msg = error_body[:500]
            logger.error("Airtable HTTP error %d: %s", e.code, error_msg)
            return {"ok": False, "error": f"HTTP {e.code}: {error_msg}"}

    except Exception as e:
        logger.exception("get_schema failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_records": list_records,
    "get_record": get_record,
    "create_record": create_record,
    "create_records": create_records,
    "update_record": update_record,
    "delete_record": delete_record,
    "list_bases": list_bases,
    "get_schema": get_schema,
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
        return {"ok": False, "error": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"}

    logger.info(f"Executing airtable.{profile}.{action}")
    return ACTIONS[action](profile, params)
