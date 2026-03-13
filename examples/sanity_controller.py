"""
Sanity Controller for TinyHive

A controller for interacting with Sanity.io headless CMS via REST API.

Method IDs:
  controller.sanity.{profile}.query
  controller.sanity.{profile}.get_document
  controller.sanity.{profile}.create
  controller.sanity.{profile}.create_or_replace
  controller.sanity.{profile}.patch
  controller.sanity.{profile}.delete
  controller.sanity.{profile}.mutate
  controller.sanity.{profile}.get_asset

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "project_id": "your-project-id",
    "dataset": "production",
    "api_version": "v2021-10-21",
    "token_env": "SANITY_API_TOKEN",
    "use_cdn": false
}

Fields:
  - project_id: Your Sanity project ID (required)
  - dataset: Dataset name (default: "production")
  - api_version: API version date string (default: "v2021-10-21")
  - token_env: Environment variable containing API token (default: "SANITY_API_TOKEN")
  - use_cdn: Use CDN for read operations (default: false)

Required Permissions:
--------------------
  - query: Read access to dataset
  - get_document: Read access to dataset
  - create: Write access to dataset
  - create_or_replace: Write access to dataset
  - patch: Write access to dataset
  - delete: Write access to dataset
  - mutate: Write access to dataset
  - get_asset: Read access to assets

Dependencies:
------------
None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.sanity")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

DEFAULT_TIMEOUT = 30
DEFAULT_API_VERSION = "v2021-10-21"
DEFAULT_DATASET = "production"


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


def _get_token(profile: Dict[str, Any]) -> str:
    """Get the API token from environment variable."""
    token_env = profile.get("token_env", "SANITY_API_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(f"Environment variable '{token_env}' not set")
    return token


def _get_api_base(profile: Dict[str, Any], use_cdn: bool = False) -> str:
    """Get the base API URL for the project."""
    project_id = profile.get("project_id")
    if not project_id:
        raise ValueError("project_id is required in profile")

    if use_cdn and profile.get("use_cdn", False):
        return f"https://{project_id}.apicdn.sanity.io"
    return f"https://{project_id}.api.sanity.io"


def _get_dataset(profile: Dict[str, Any]) -> str:
    """Get the dataset name from profile."""
    return profile.get("dataset", DEFAULT_DATASET)


def _get_api_version(profile: Dict[str, Any]) -> str:
    """Get the API version from profile."""
    return profile.get("api_version", DEFAULT_API_VERSION)


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Sanity API call."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_data.get("error", error_body[:500]))
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Sanity API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Sanity API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def query(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a GROQ query against the dataset.

    Params:
        query (str): GROQ query string (required)
        params (dict): Query parameters for parameterized queries (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    groq_query = params.get("query")
    if not groq_query:
        return {"ok": False, "error": "query is required"}

    query_params = params.get("params", {})

    api_base = _get_api_base(profile, use_cdn=True)
    api_version = _get_api_version(profile)
    dataset = _get_dataset(profile)

    # Build query string
    qs_params = {"query": groq_query}
    for key, value in query_params.items():
        # GROQ params are prefixed with $
        param_key = f"${key}" if not key.startswith("$") else key
        qs_params[param_key] = json.dumps(value) if not isinstance(value, str) else f'"{value}"'

    url = f"{api_base}/{api_version}/data/query/{dataset}?{urlencode(qs_params)}"

    result = _api_call(token, url, method="GET")

    if result.get("ok") and "result" in result:
        api_result = result["result"]
        return {
            "ok": True,
            "data": api_result.get("result", []),
            "ms": api_result.get("ms"),
            "query": groq_query
        }
    return result


def get_document(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a single document by ID.

    Params:
        document_id (str): Document ID (required)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    document_id = params.get("document_id")
    if not document_id:
        return {"ok": False, "error": "document_id is required"}

    api_base = _get_api_base(profile, use_cdn=True)
    api_version = _get_api_version(profile)
    dataset = _get_dataset(profile)

    # Use GROQ query to fetch by ID
    groq_query = f'*[_id == "{document_id}"][0]'
    url = f"{api_base}/{api_version}/data/query/{dataset}?{urlencode({'query': groq_query})}"

    result = _api_call(token, url, method="GET")

    if result.get("ok") and "result" in result:
        api_result = result["result"]
        document = api_result.get("result")
        if document is None:
            return {"ok": False, "error": f"Document not found: {document_id}"}
        return {
            "ok": True,
            "data": document,
            "ms": api_result.get("ms")
        }
    return result


def create(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new document.

    Params:
        document (dict): Document to create (required, must have _type)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    document = params.get("document")
    if not document:
        return {"ok": False, "error": "document is required"}
    if not isinstance(document, dict):
        return {"ok": False, "error": "document must be a dict"}
    if "_type" not in document:
        return {"ok": False, "error": "document must have _type field"}

    api_base = _get_api_base(profile)
    api_version = _get_api_version(profile)
    dataset = _get_dataset(profile)

    url = f"{api_base}/{api_version}/data/mutate/{dataset}"

    mutations = {"mutations": [{"create": document}]}
    data = json.dumps(mutations).encode("utf-8")

    result = _api_call(token, url, method="POST", data=data)

    if result.get("ok") and "result" in result:
        api_result = result["result"]
        results = api_result.get("results", [])
        if results:
            return {
                "ok": True,
                "data": {
                    "id": results[0].get("id"),
                    "document": results[0].get("document")
                },
                "transactionId": api_result.get("transactionId")
            }
        return {"ok": True, "data": api_result}
    return result


def create_or_replace(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a document or replace if it already exists.

    Params:
        document (dict): Document to create/replace (required, must have _id and _type)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    document = params.get("document")
    if not document:
        return {"ok": False, "error": "document is required"}
    if not isinstance(document, dict):
        return {"ok": False, "error": "document must be a dict"}
    if "_id" not in document:
        return {"ok": False, "error": "document must have _id field for createOrReplace"}
    if "_type" not in document:
        return {"ok": False, "error": "document must have _type field"}

    api_base = _get_api_base(profile)
    api_version = _get_api_version(profile)
    dataset = _get_dataset(profile)

    url = f"{api_base}/{api_version}/data/mutate/{dataset}"

    mutations = {"mutations": [{"createOrReplace": document}]}
    data = json.dumps(mutations).encode("utf-8")

    result = _api_call(token, url, method="POST", data=data)

    if result.get("ok") and "result" in result:
        api_result = result["result"]
        results = api_result.get("results", [])
        if results:
            return {
                "ok": True,
                "data": {
                    "id": results[0].get("id"),
                    "operation": results[0].get("operation")
                },
                "transactionId": api_result.get("transactionId")
            }
        return {"ok": True, "data": api_result}
    return result


def patch(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Patch an existing document.

    Params:
        document_id (str): Document ID to patch (required)
        set (dict): Fields to set (optional)
        unset (list): Field names to unset (optional)
        inc (dict): Fields to increment (optional)
        dec (dict): Fields to decrement (optional)
        insert (dict): Array insert operations (optional)
        ifRevisionID (str): Only patch if revision matches (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    document_id = params.get("document_id")
    if not document_id:
        return {"ok": False, "error": "document_id is required"}

    # Build patch object
    patch_obj: Dict[str, Any] = {"id": document_id}

    if "set" in params and params["set"]:
        patch_obj["set"] = params["set"]
    if "unset" in params and params["unset"]:
        patch_obj["unset"] = params["unset"]
    if "inc" in params and params["inc"]:
        patch_obj["inc"] = params["inc"]
    if "dec" in params and params["dec"]:
        patch_obj["dec"] = params["dec"]
    if "insert" in params and params["insert"]:
        patch_obj["insert"] = params["insert"]
    if "ifRevisionID" in params:
        patch_obj["ifRevisionID"] = params["ifRevisionID"]

    # Check that at least one operation is specified
    if not any(k in patch_obj for k in ["set", "unset", "inc", "dec", "insert"]):
        return {"ok": False, "error": "At least one patch operation (set, unset, inc, dec, insert) is required"}

    api_base = _get_api_base(profile)
    api_version = _get_api_version(profile)
    dataset = _get_dataset(profile)

    url = f"{api_base}/{api_version}/data/mutate/{dataset}"

    mutations = {"mutations": [{"patch": patch_obj}]}
    data = json.dumps(mutations).encode("utf-8")

    result = _api_call(token, url, method="POST", data=data)

    if result.get("ok") and "result" in result:
        api_result = result["result"]
        results = api_result.get("results", [])
        if results:
            return {
                "ok": True,
                "data": {
                    "id": results[0].get("id"),
                    "operation": results[0].get("operation")
                },
                "transactionId": api_result.get("transactionId")
            }
        return {"ok": True, "data": api_result}
    return result


def delete(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a document by ID.

    Params:
        document_id (str): Document ID to delete (required)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    document_id = params.get("document_id")
    if not document_id:
        return {"ok": False, "error": "document_id is required"}

    api_base = _get_api_base(profile)
    api_version = _get_api_version(profile)
    dataset = _get_dataset(profile)

    url = f"{api_base}/{api_version}/data/mutate/{dataset}"

    mutations = {"mutations": [{"delete": {"id": document_id}}]}
    data = json.dumps(mutations).encode("utf-8")

    result = _api_call(token, url, method="POST", data=data)

    if result.get("ok") and "result" in result:
        api_result = result["result"]
        results = api_result.get("results", [])
        if results:
            return {
                "ok": True,
                "data": {
                    "id": results[0].get("id"),
                    "operation": "delete"
                },
                "transactionId": api_result.get("transactionId")
            }
        return {"ok": True, "data": api_result}
    return result


def mutate(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute batch mutations.

    Params:
        mutations (list): Array of mutation objects (required)
            Each mutation can be one of:
            - {"create": document}
            - {"createOrReplace": document}
            - {"createIfNotExists": document}
            - {"delete": {"id": document_id}}
            - {"patch": {id, set, unset, inc, dec, insert}}
        return_ids (bool): Return IDs of affected documents (default: true)
        return_documents (bool): Return full documents (default: false)
        visibility (str): "sync" or "async" (default: "sync")
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    mutations_list = params.get("mutations")
    if not mutations_list:
        return {"ok": False, "error": "mutations is required"}
    if not isinstance(mutations_list, list):
        return {"ok": False, "error": "mutations must be a list"}
    if len(mutations_list) == 0:
        return {"ok": False, "error": "mutations list cannot be empty"}

    api_base = _get_api_base(profile)
    api_version = _get_api_version(profile)
    dataset = _get_dataset(profile)

    # Build query params
    query_params = {}
    if params.get("return_ids", True):
        query_params["returnIds"] = "true"
    if params.get("return_documents", False):
        query_params["returnDocuments"] = "true"
    if params.get("visibility"):
        query_params["visibility"] = params["visibility"]

    url = f"{api_base}/{api_version}/data/mutate/{dataset}"
    if query_params:
        url += f"?{urlencode(query_params)}"

    mutations = {"mutations": mutations_list}
    data = json.dumps(mutations).encode("utf-8")

    result = _api_call(token, url, method="POST", data=data)

    if result.get("ok") and "result" in result:
        api_result = result["result"]
        return {
            "ok": True,
            "data": {
                "results": api_result.get("results", []),
                "documentIds": api_result.get("documentIds", [])
            },
            "transactionId": api_result.get("transactionId")
        }
    return result


def get_asset(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get asset URL from asset reference.

    Params:
        asset_ref (str): Asset reference ID (e.g., "image-abc123-1200x800-png")

    Returns the CDN URL for the asset.
    """
    profile = load_profile(profile_name)

    asset_ref = params.get("asset_ref")
    if not asset_ref:
        return {"ok": False, "error": "asset_ref is required"}

    project_id = profile.get("project_id")
    if not project_id:
        return {"ok": False, "error": "project_id is required in profile"}

    dataset = _get_dataset(profile)

    # Parse asset reference
    # Format: image-{id}-{dimensions}-{format} or file-{id}-{originalFilename}
    parts = asset_ref.split("-")

    if len(parts) < 2:
        return {"ok": False, "error": f"Invalid asset reference format: {asset_ref}"}

    asset_type = parts[0]

    if asset_type == "image":
        # image-{id}-{width}x{height}-{format}
        if len(parts) < 4:
            return {"ok": False, "error": f"Invalid image asset reference: {asset_ref}"}

        asset_id = parts[1]
        dimensions = parts[2]
        img_format = parts[3]

        # Sanity CDN URL format
        url = f"https://cdn.sanity.io/images/{project_id}/{dataset}/{asset_id}-{dimensions}.{img_format}"

        return {
            "ok": True,
            "data": {
                "url": url,
                "type": "image",
                "asset_id": asset_id,
                "dimensions": dimensions,
                "format": img_format
            }
        }

    elif asset_type == "file":
        # file-{id}-{originalFilename}
        if len(parts) < 3:
            return {"ok": False, "error": f"Invalid file asset reference: {asset_ref}"}

        asset_id = parts[1]
        filename = "-".join(parts[2:])  # Filename may contain dashes

        url = f"https://cdn.sanity.io/files/{project_id}/{dataset}/{asset_id}.{filename.split('.')[-1]}"

        return {
            "ok": True,
            "data": {
                "url": url,
                "type": "file",
                "asset_id": asset_id,
                "filename": filename
            }
        }

    else:
        return {"ok": False, "error": f"Unknown asset type: {asset_type}"}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "query": query,
    "get_document": get_document,
    "create": create,
    "create_or_replace": create_or_replace,
    "patch": patch,
    "delete": delete,
    "mutate": mutate,
    "get_asset": get_asset,
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

    try:
        logger.info(f"Executing sanity.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
