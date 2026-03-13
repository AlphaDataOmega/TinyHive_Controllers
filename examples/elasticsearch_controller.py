"""
Elasticsearch Controller for TinyHive

A controller for Elasticsearch REST API operations supporting both
Elastic Cloud (API key auth) and self-hosted clusters (Basic auth).

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Elastic Cloud profile:
{
    "host": "https://my-cluster.es.us-east-1.aws.elastic.cloud:9243",
    "api_key_env": "ELASTICSEARCH_API_KEY"
}

Self-hosted with Basic auth:
{
    "host": "https://localhost:9200",
    "username_env": "ELASTICSEARCH_USERNAME",
    "password_env": "ELASTICSEARCH_PASSWORD",
    "verify_ssl": false
}

Environment Variables:
---------------------
- ELASTICSEARCH_API_KEY: API key for Elastic Cloud (Base64 encoded id:api_key)
- ELASTICSEARCH_USERNAME: Username for Basic auth
- ELASTICSEARCH_PASSWORD: Password for Basic auth

Dependencies:
------------
- None (standard library only)
"""

import base64
import json
import logging
import os
import ssl
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.elasticsearch")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

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


# =============================================================================
# Authentication Helpers
# =============================================================================

def _get_auth_headers(profile: Dict[str, Any]) -> Dict[str, str]:
    """
    Get authentication headers based on profile configuration.

    Supports:
    - API Key auth (for Elastic Cloud): Authorization: ApiKey <key>
    - Basic auth: Authorization: Basic <base64(user:pass)>
    """
    headers = {}

    # API Key authentication (Elastic Cloud)
    api_key_env = profile.get("api_key_env")
    if api_key_env:
        api_key = os.environ.get(api_key_env)
        if api_key:
            headers["Authorization"] = f"ApiKey {api_key}"
            return headers

    # Basic authentication
    username_env = profile.get("username_env")
    password_env = profile.get("password_env")

    if username_env and password_env:
        username = os.environ.get(username_env)
        password = os.environ.get(password_env)

        if username and password:
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
            return headers

    # No auth configured
    return headers


def _get_ssl_context(profile: Dict[str, Any]) -> Optional[ssl.SSLContext]:
    """Get SSL context based on profile configuration."""
    verify_ssl = profile.get("verify_ssl", True)

    if not verify_ssl:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    return None


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    profile: Dict[str, Any],
    method: str,
    path: str,
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated Elasticsearch API call.

    Args:
        profile: Profile configuration dict
        method: HTTP method (GET, POST, PUT, DELETE)
        path: API path (e.g., /my-index/_search)
        data: Request body as dict (will be JSON encoded)
        timeout: Request timeout in seconds

    Returns:
        Dict with 'ok' status and 'result' or 'error'
    """
    host = profile.get("host", "").rstrip("/")
    if not host:
        return {"ok": False, "error": "Profile missing 'host' configuration"}

    url = f"{host}{path}"

    headers = _get_auth_headers(profile)
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "application/json"

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    ssl_context = _get_ssl_context(profile)

    try:
        req = Request(url, data=body, headers=headers, method=method)

        with urlopen(req, timeout=timeout, context=ssl_context) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                result = json.loads(response_body)
                return {"ok": True, "result": result}
            return {"ok": True, "result": {}}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("error", {})
            if isinstance(error_message, dict):
                error_message = error_message.get("reason", str(error_data))
            else:
                error_message = str(error_data)
        except json.JSONDecodeError:
            error_message = error_body[:500]

        logger.error("Elasticsearch API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}

    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}

    except Exception as e:
        logger.exception("Unexpected error in Elasticsearch API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def search(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search documents in an index.

    Params:
        index (str): Index name or pattern (required)
        query (dict): Elasticsearch query DSL (default: match_all)
        size (int): Number of results to return (default: 10)
        from (int): Offset for pagination (default: 0)
        sort (list): Sort specification (optional)
        _source (list): Fields to return (optional)
        aggs (dict): Aggregations (optional)

    Returns:
        {ok: True, result: {hits: {...}, aggregations: {...}}}
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    index = params.get("index")
    if not index:
        return {"ok": False, "error": "index is required"}

    # Build search body
    body: Dict[str, Any] = {}

    if "query" in params:
        body["query"] = params["query"]
    else:
        body["query"] = {"match_all": {}}

    if "size" in params:
        body["size"] = params["size"]

    if "from" in params:
        body["from"] = params["from"]

    if "sort" in params:
        body["sort"] = params["sort"]

    if "_source" in params:
        body["_source"] = params["_source"]

    if "aggs" in params:
        body["aggs"] = params["aggs"]

    path = f"/{quote(index, safe='*,')}/_search"

    result = _api_call(profile, "POST", path, data=body)

    if result.get("ok") and "result" in result:
        es_result = result["result"]
        return {
            "ok": True,
            "result": {
                "total": es_result.get("hits", {}).get("total", {}).get("value", 0),
                "hits": es_result.get("hits", {}).get("hits", []),
                "aggregations": es_result.get("aggregations"),
                "took": es_result.get("took"),
            }
        }

    return result


def index_doc(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Index (create or replace) a document.

    Params:
        index (str): Index name (required)
        doc_id (str): Document ID (optional, auto-generated if not provided)
        document (dict): Document body (required)
        refresh (str): Refresh policy: 'true', 'false', 'wait_for' (optional)

    Returns:
        {ok: True, result: {_id: ..., _index: ..., _version: ...}}
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    index = params.get("index")
    if not index:
        return {"ok": False, "error": "index is required"}

    document = params.get("document")
    if not document:
        return {"ok": False, "error": "document is required"}

    doc_id = params.get("doc_id")
    refresh = params.get("refresh")

    if doc_id:
        path = f"/{quote(index, safe='')}/_doc/{quote(str(doc_id), safe='')}"
        method = "PUT"
    else:
        path = f"/{quote(index, safe='')}/_doc"
        method = "POST"

    if refresh:
        path += f"?refresh={refresh}"

    result = _api_call(profile, method, path, data=document)

    if result.get("ok") and "result" in result:
        es_result = result["result"]
        return {
            "ok": True,
            "result": {
                "_id": es_result.get("_id"),
                "_index": es_result.get("_index"),
                "_version": es_result.get("_version"),
                "result": es_result.get("result"),
            }
        }

    return result


def get_doc(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a document by ID.

    Params:
        index (str): Index name (required)
        doc_id (str): Document ID (required)
        _source (list): Fields to return (optional)

    Returns:
        {ok: True, result: {_id: ..., _source: {...}}}
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    index = params.get("index")
    if not index:
        return {"ok": False, "error": "index is required"}

    doc_id = params.get("doc_id")
    if not doc_id:
        return {"ok": False, "error": "doc_id is required"}

    path = f"/{quote(index, safe='')}/_doc/{quote(str(doc_id), safe='')}"

    source_fields = params.get("_source")
    if source_fields:
        if isinstance(source_fields, list):
            source_fields = ",".join(source_fields)
        path += f"?_source={quote(source_fields, safe=',')}"

    result = _api_call(profile, "GET", path)

    if result.get("ok") and "result" in result:
        es_result = result["result"]
        if not es_result.get("found", True):
            return {"ok": False, "error": f"Document not found: {doc_id}"}

        return {
            "ok": True,
            "result": {
                "_id": es_result.get("_id"),
                "_index": es_result.get("_index"),
                "_version": es_result.get("_version"),
                "_source": es_result.get("_source"),
                "found": es_result.get("found"),
            }
        }

    return result


def update_doc(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update a document (partial update).

    Params:
        index (str): Index name (required)
        doc_id (str): Document ID (required)
        doc (dict): Partial document with fields to update (required)
        refresh (str): Refresh policy: 'true', 'false', 'wait_for' (optional)
        retry_on_conflict (int): Number of retries on version conflict (optional)

    Returns:
        {ok: True, result: {_id: ..., _version: ..., result: 'updated'}}
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    index = params.get("index")
    if not index:
        return {"ok": False, "error": "index is required"}

    doc_id = params.get("doc_id")
    if not doc_id:
        return {"ok": False, "error": "doc_id is required"}

    doc = params.get("doc")
    if not doc:
        return {"ok": False, "error": "doc is required"}

    path = f"/{quote(index, safe='')}/_update/{quote(str(doc_id), safe='')}"

    query_params = []
    if params.get("refresh"):
        query_params.append(f"refresh={params['refresh']}")
    if params.get("retry_on_conflict"):
        query_params.append(f"retry_on_conflict={params['retry_on_conflict']}")

    if query_params:
        path += "?" + "&".join(query_params)

    body = {"doc": doc}

    result = _api_call(profile, "POST", path, data=body)

    if result.get("ok") and "result" in result:
        es_result = result["result"]
        return {
            "ok": True,
            "result": {
                "_id": es_result.get("_id"),
                "_index": es_result.get("_index"),
                "_version": es_result.get("_version"),
                "result": es_result.get("result"),
            }
        }

    return result


def delete_doc(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a document by ID.

    Params:
        index (str): Index name (required)
        doc_id (str): Document ID (required)
        refresh (str): Refresh policy: 'true', 'false', 'wait_for' (optional)

    Returns:
        {ok: True, result: {_id: ..., result: 'deleted'}}
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    index = params.get("index")
    if not index:
        return {"ok": False, "error": "index is required"}

    doc_id = params.get("doc_id")
    if not doc_id:
        return {"ok": False, "error": "doc_id is required"}

    path = f"/{quote(index, safe='')}/_doc/{quote(str(doc_id), safe='')}"

    refresh = params.get("refresh")
    if refresh:
        path += f"?refresh={refresh}"

    result = _api_call(profile, "DELETE", path)

    if result.get("ok") and "result" in result:
        es_result = result["result"]
        return {
            "ok": True,
            "result": {
                "_id": es_result.get("_id"),
                "_index": es_result.get("_index"),
                "_version": es_result.get("_version"),
                "result": es_result.get("result"),
            }
        }

    return result


def bulk(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform bulk operations.

    Params:
        operations (list): List of operations, each is a dict with:
            - action (str): 'index', 'create', 'update', or 'delete'
            - index (str): Index name
            - doc_id (str): Document ID (optional for index/create)
            - document (dict): Document body (for index/create/update)
        refresh (str): Refresh policy: 'true', 'false', 'wait_for' (optional)

    Example operations:
        [
            {"action": "index", "index": "my-index", "doc_id": "1", "document": {"field": "value"}},
            {"action": "delete", "index": "my-index", "doc_id": "2"},
            {"action": "update", "index": "my-index", "doc_id": "3", "document": {"field": "new_value"}}
        ]

    Returns:
        {ok: True, result: {took: ..., errors: bool, items: [...]}}
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    operations = params.get("operations")
    if not operations:
        return {"ok": False, "error": "operations is required"}

    if not isinstance(operations, list):
        return {"ok": False, "error": "operations must be a list"}

    # Build NDJSON body
    lines = []
    for op in operations:
        action = op.get("action")
        if action not in ("index", "create", "update", "delete"):
            return {"ok": False, "error": f"Invalid action: {action}"}

        index = op.get("index")
        if not index:
            return {"ok": False, "error": "Each operation must have an index"}

        doc_id = op.get("doc_id")

        # Action line
        action_meta = {action: {"_index": index}}
        if doc_id:
            action_meta[action]["_id"] = str(doc_id)

        lines.append(json.dumps(action_meta))

        # Document line (not needed for delete)
        if action == "delete":
            continue

        document = op.get("document")
        if not document:
            return {"ok": False, "error": f"{action} operation requires a document"}

        if action == "update":
            lines.append(json.dumps({"doc": document}))
        else:
            lines.append(json.dumps(document))

    # NDJSON format requires trailing newline
    body = "\n".join(lines) + "\n"

    path = "/_bulk"
    refresh = params.get("refresh")
    if refresh:
        path += f"?refresh={refresh}"

    # For bulk, we need to send as NDJSON
    host = profile.get("host", "").rstrip("/")
    if not host:
        return {"ok": False, "error": "Profile missing 'host' configuration"}

    url = f"{host}{path}"

    headers = _get_auth_headers(profile)
    headers["Content-Type"] = "application/x-ndjson"
    headers["Accept"] = "application/json"

    ssl_context = _get_ssl_context(profile)

    try:
        req = Request(url, data=body.encode("utf-8"), headers=headers, method="POST")

        with urlopen(req, timeout=DEFAULT_TIMEOUT * 2, context=ssl_context) as response:
            response_body = response.read().decode("utf-8")
            es_result = json.loads(response_body)

            return {
                "ok": True,
                "result": {
                    "took": es_result.get("took"),
                    "errors": es_result.get("errors", False),
                    "items": es_result.get("items", []),
                }
            }

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error("Elasticsearch bulk error %d: %s", e.code, error_body[:500])
        return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}

    except Exception as e:
        logger.exception("Unexpected error in bulk operation")
        return {"ok": False, "error": str(e)}


def create_index(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an index.

    Params:
        index (str): Index name (required)
        mappings (dict): Index mappings (optional)
        settings (dict): Index settings (optional)

    Example:
        {
            "index": "my-index",
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "count": {"type": "integer"}
                }
            },
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 1
            }
        }

    Returns:
        {ok: True, result: {acknowledged: True, index: ...}}
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    index = params.get("index")
    if not index:
        return {"ok": False, "error": "index is required"}

    body: Dict[str, Any] = {}

    if params.get("mappings"):
        body["mappings"] = params["mappings"]

    if params.get("settings"):
        body["settings"] = params["settings"]

    path = f"/{quote(index, safe='')}"

    result = _api_call(profile, "PUT", path, data=body if body else None)

    if result.get("ok") and "result" in result:
        es_result = result["result"]
        return {
            "ok": True,
            "result": {
                "acknowledged": es_result.get("acknowledged"),
                "shards_acknowledged": es_result.get("shards_acknowledged"),
                "index": es_result.get("index"),
            }
        }

    return result


def delete_index(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete an index.

    Params:
        index (str): Index name or pattern (required)

    Returns:
        {ok: True, result: {acknowledged: True}}
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    index = params.get("index")
    if not index:
        return {"ok": False, "error": "index is required"}

    path = f"/{quote(index, safe='*,')}"

    result = _api_call(profile, "DELETE", path)

    if result.get("ok") and "result" in result:
        es_result = result["result"]
        return {
            "ok": True,
            "result": {
                "acknowledged": es_result.get("acknowledged"),
            }
        }

    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "search": search,
    "index_doc": index_doc,
    "get_doc": get_doc,
    "update_doc": update_doc,
    "delete_doc": delete_doc,
    "bulk": bulk,
    "create_index": create_index,
    "delete_index": delete_index,
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

    logger.info(f"Executing elasticsearch.{profile}.{action}")
    return ACTIONS[action](profile, params)
