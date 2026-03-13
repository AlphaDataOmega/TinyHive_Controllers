"""
Contentful Controller for TinyHive

A controller for managing content in Contentful CMS via the Content Delivery API (CDA)
and Content Management API (CMA).

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "space_id": "your-space-id",
    "environment": "master",
    "cda_token_env": "CONTENTFUL_CDA_TOKEN",
    "cma_token_env": "CONTENTFUL_CMA_TOKEN"
}

Environment Variables:
---------------------
- CONTENTFUL_CDA_TOKEN: Content Delivery API access token (read-only)
- CONTENTFUL_CMA_TOKEN: Content Management API access token (read/write)

API Endpoints:
-------------
- CDA (read): https://cdn.contentful.com
- CMA (write): https://api.contentful.com

Method IDs:
----------
  controller.contentful.{profile}.get_entries
  controller.contentful.{profile}.get_entry
  controller.contentful.{profile}.create_entry
  controller.contentful.{profile}.update_entry
  controller.contentful.{profile}.publish_entry
  controller.contentful.{profile}.get_assets
  controller.contentful.{profile}.get_content_types
  controller.contentful.{profile}.search

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

logger = logging.getLogger("tinyhive.controller.contentful")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Contentful API endpoints
CDA_BASE = "https://cdn.contentful.com"
CMA_BASE = "https://api.contentful.com"

DEFAULT_TIMEOUT = 30


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile from the profiles directory."""
    profile_path = PROFILES_DIR / f"{name}.json"
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {name}. Create {profile_path} with Contentful configuration.")

    with open(profile_path) as f:
        return json.load(f)


def _get_cda_token(profile: Dict[str, Any]) -> str:
    """Get Content Delivery API token from environment."""
    env_var = profile.get("cda_token_env", "CONTENTFUL_CDA_TOKEN")
    token = os.environ.get(env_var)
    if not token:
        raise ValueError(f"Environment variable '{env_var}' not set for CDA token")
    return token


def _get_cma_token(profile: Dict[str, Any]) -> str:
    """Get Content Management API token from environment."""
    env_var = profile.get("cma_token_env", "CONTENTFUL_CMA_TOKEN")
    token = os.environ.get(env_var)
    if not token:
        raise ValueError(f"Environment variable '{env_var}' not set for CMA token")
    return token


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    content_type: str = "application/vnd.contentful.management.v1+json",
    timeout: int = DEFAULT_TIMEOUT,
    extra_headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Make an authenticated Contentful API call."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
    }
    if extra_headers:
        headers.update(extra_headers)

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
            error_message = error_data.get("message", error_body[:500])
            error_details = error_data.get("details", {})
        except json.JSONDecodeError:
            error_message = error_body[:500]
            error_details = {}
        logger.error("Contentful API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}", "details": error_details}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Contentful API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Entry Actions
# =============================================================================

def get_entries(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get entries from Contentful (CDA - read-only).

    Params:
        content_type (str): Filter by content type ID (optional)
        limit (int): Maximum entries to return (default: 100, max: 1000)
        skip (int): Number of entries to skip (default: 0)
        order (str): Order results (e.g., '-sys.createdAt')
        query (dict): Additional query parameters (optional)

    Returns:
        List of entries with their fields and metadata.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_cda_token(profile)
        space_id = profile.get("space_id")
        environment = profile.get("environment", "master")

        if not space_id:
            return {"ok": False, "error": "space_id required in profile"}

        # Build query parameters
        query_params = {}

        if params.get("content_type"):
            query_params["content_type"] = params["content_type"]

        if params.get("limit"):
            query_params["limit"] = min(int(params["limit"]), 1000)

        if params.get("skip"):
            query_params["skip"] = int(params["skip"])

        if params.get("order"):
            query_params["order"] = params["order"]

        # Merge additional query params
        if params.get("query") and isinstance(params["query"], dict):
            query_params.update(params["query"])

        url = f"{CDA_BASE}/spaces/{space_id}/environments/{environment}/entries"
        if query_params:
            url += f"?{urlencode(query_params)}"

        result = _api_call(token, url, method="GET")

        if result.get("ok") and "result" in result:
            data = result["result"]
            entries = data.get("items", [])
            return {
                "ok": True,
                "data": {
                    "entries": entries,
                    "total": data.get("total", len(entries)),
                    "skip": data.get("skip", 0),
                    "limit": data.get("limit", 100),
                    "includes": data.get("includes", {})
                }
            }
        return result
    except Exception as e:
        logger.exception("get_entries failed")
        return {"ok": False, "error": str(e)}


def get_entry(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a single entry by ID (CDA - read-only).

    Params:
        entry_id (str): The entry ID (required)
        locale (str): Locale code (optional, e.g., 'en-US')

    Returns:
        Entry with fields and metadata.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_cda_token(profile)
        space_id = profile.get("space_id")
        environment = profile.get("environment", "master")

        if not space_id:
            return {"ok": False, "error": "space_id required in profile"}

        entry_id = params.get("entry_id")
        if not entry_id:
            return {"ok": False, "error": "entry_id is required"}

        query_params = {}
        if params.get("locale"):
            query_params["locale"] = params["locale"]

        url = f"{CDA_BASE}/spaces/{space_id}/environments/{environment}/entries/{quote(entry_id)}"
        if query_params:
            url += f"?{urlencode(query_params)}"

        result = _api_call(token, url, method="GET")

        if result.get("ok") and "result" in result:
            return {"ok": True, "data": result["result"]}
        return result
    except Exception as e:
        logger.exception("get_entry failed")
        return {"ok": False, "error": str(e)}


def create_entry(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new entry (CMA - write).

    Params:
        content_type (str): Content type ID (required)
        fields (dict): Entry fields with locale (required)
            Example: {"title": {"en-US": "Hello"}, "body": {"en-US": "World"}}

    Returns:
        Created entry with sys metadata.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_cma_token(profile)
        space_id = profile.get("space_id")
        environment = profile.get("environment", "master")

        if not space_id:
            return {"ok": False, "error": "space_id required in profile"}

        content_type = params.get("content_type")
        if not content_type:
            return {"ok": False, "error": "content_type is required"}

        fields = params.get("fields")
        if not fields:
            return {"ok": False, "error": "fields is required"}

        url = f"{CMA_BASE}/spaces/{space_id}/environments/{environment}/entries"

        body = {"fields": fields}
        data = json.dumps(body).encode("utf-8")

        extra_headers = {
            "X-Contentful-Content-Type": content_type
        }

        result = _api_call(
            token, url, method="POST", data=data,
            extra_headers=extra_headers
        )

        if result.get("ok") and "result" in result:
            entry = result["result"]
            return {
                "ok": True,
                "data": {
                    "id": entry.get("sys", {}).get("id"),
                    "version": entry.get("sys", {}).get("version"),
                    "entry": entry
                }
            }
        return result
    except Exception as e:
        logger.exception("create_entry failed")
        return {"ok": False, "error": str(e)}


def update_entry(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing entry (CMA - write).

    Params:
        entry_id (str): The entry ID (required)
        fields (dict): Entry fields with locale (required)
        version (int): Current entry version for optimistic locking (required)

    Returns:
        Updated entry with new version number.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_cma_token(profile)
        space_id = profile.get("space_id")
        environment = profile.get("environment", "master")

        if not space_id:
            return {"ok": False, "error": "space_id required in profile"}

        entry_id = params.get("entry_id")
        if not entry_id:
            return {"ok": False, "error": "entry_id is required"}

        fields = params.get("fields")
        if not fields:
            return {"ok": False, "error": "fields is required"}

        version = params.get("version")
        if version is None:
            return {"ok": False, "error": "version is required for optimistic locking"}

        url = f"{CMA_BASE}/spaces/{space_id}/environments/{environment}/entries/{quote(entry_id)}"

        body = {"fields": fields}
        data = json.dumps(body).encode("utf-8")

        extra_headers = {
            "X-Contentful-Version": str(version)
        }

        result = _api_call(
            token, url, method="PUT", data=data,
            extra_headers=extra_headers
        )

        if result.get("ok") and "result" in result:
            entry = result["result"]
            return {
                "ok": True,
                "data": {
                    "id": entry.get("sys", {}).get("id"),
                    "version": entry.get("sys", {}).get("version"),
                    "entry": entry
                }
            }
        return result
    except Exception as e:
        logger.exception("update_entry failed")
        return {"ok": False, "error": str(e)}


def publish_entry(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Publish an entry (CMA - write).

    Params:
        entry_id (str): The entry ID (required)
        version (int): Current entry version (required)

    Returns:
        Published entry with publishedVersion.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_cma_token(profile)
        space_id = profile.get("space_id")
        environment = profile.get("environment", "master")

        if not space_id:
            return {"ok": False, "error": "space_id required in profile"}

        entry_id = params.get("entry_id")
        if not entry_id:
            return {"ok": False, "error": "entry_id is required"}

        version = params.get("version")
        if version is None:
            return {"ok": False, "error": "version is required"}

        url = f"{CMA_BASE}/spaces/{space_id}/environments/{environment}/entries/{quote(entry_id)}/published"

        extra_headers = {
            "X-Contentful-Version": str(version)
        }

        result = _api_call(
            token, url, method="PUT", data=None,
            extra_headers=extra_headers
        )

        if result.get("ok") and "result" in result:
            entry = result["result"]
            return {
                "ok": True,
                "data": {
                    "id": entry.get("sys", {}).get("id"),
                    "version": entry.get("sys", {}).get("version"),
                    "publishedVersion": entry.get("sys", {}).get("publishedVersion"),
                    "entry": entry
                }
            }
        return result
    except Exception as e:
        logger.exception("publish_entry failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Asset Actions
# =============================================================================

def get_assets(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get assets from Contentful (CDA - read-only).

    Params:
        limit (int): Maximum assets to return (default: 100, max: 1000)
        skip (int): Number of assets to skip (default: 0)
        mimetype_group (str): Filter by MIME type group (image, plaintext, etc.)
        query (dict): Additional query parameters (optional)

    Returns:
        List of assets with their fields and file metadata.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_cda_token(profile)
        space_id = profile.get("space_id")
        environment = profile.get("environment", "master")

        if not space_id:
            return {"ok": False, "error": "space_id required in profile"}

        query_params = {}

        if params.get("limit"):
            query_params["limit"] = min(int(params["limit"]), 1000)

        if params.get("skip"):
            query_params["skip"] = int(params["skip"])

        if params.get("mimetype_group"):
            query_params["mimetype_group"] = params["mimetype_group"]

        # Merge additional query params
        if params.get("query") and isinstance(params["query"], dict):
            query_params.update(params["query"])

        url = f"{CDA_BASE}/spaces/{space_id}/environments/{environment}/assets"
        if query_params:
            url += f"?{urlencode(query_params)}"

        result = _api_call(token, url, method="GET")

        if result.get("ok") and "result" in result:
            data = result["result"]
            assets = data.get("items", [])
            return {
                "ok": True,
                "data": {
                    "assets": assets,
                    "total": data.get("total", len(assets)),
                    "skip": data.get("skip", 0),
                    "limit": data.get("limit", 100)
                }
            }
        return result
    except Exception as e:
        logger.exception("get_assets failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Content Type Actions
# =============================================================================

def get_content_types(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get content types from Contentful (CDA - read-only).

    Params:
        limit (int): Maximum content types to return (default: 100)
        skip (int): Number to skip (default: 0)

    Returns:
        List of content types with their field definitions.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_cda_token(profile)
        space_id = profile.get("space_id")
        environment = profile.get("environment", "master")

        if not space_id:
            return {"ok": False, "error": "space_id required in profile"}

        query_params = {}

        if params.get("limit"):
            query_params["limit"] = min(int(params["limit"]), 1000)

        if params.get("skip"):
            query_params["skip"] = int(params["skip"])

        url = f"{CDA_BASE}/spaces/{space_id}/environments/{environment}/content_types"
        if query_params:
            url += f"?{urlencode(query_params)}"

        result = _api_call(token, url, method="GET")

        if result.get("ok") and "result" in result:
            data = result["result"]
            content_types = data.get("items", [])
            return {
                "ok": True,
                "data": {
                    "content_types": [
                        {
                            "id": ct.get("sys", {}).get("id"),
                            "name": ct.get("name"),
                            "description": ct.get("description"),
                            "displayField": ct.get("displayField"),
                            "fields": ct.get("fields", [])
                        }
                        for ct in content_types
                    ],
                    "total": data.get("total", len(content_types))
                }
            }
        return result
    except Exception as e:
        logger.exception("get_content_types failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Search Actions
# =============================================================================

def search(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search content in Contentful (CDA - read-only).

    Params:
        query (str): Full-text search query (required)
        content_type (str): Filter by content type ID (optional)
        limit (int): Maximum results (default: 100, max: 1000)
        skip (int): Number of results to skip (default: 0)
        include (int): Levels of linked entries to include (default: 1, max: 10)

    Returns:
        Search results with entries and linked assets/entries.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_cda_token(profile)
        space_id = profile.get("space_id")
        environment = profile.get("environment", "master")

        if not space_id:
            return {"ok": False, "error": "space_id required in profile"}

        query_text = params.get("query")
        if not query_text:
            return {"ok": False, "error": "query is required"}

        query_params = {
            "query": query_text
        }

        if params.get("content_type"):
            query_params["content_type"] = params["content_type"]

        if params.get("limit"):
            query_params["limit"] = min(int(params["limit"]), 1000)

        if params.get("skip"):
            query_params["skip"] = int(params["skip"])

        if params.get("include"):
            query_params["include"] = min(int(params["include"]), 10)

        url = f"{CDA_BASE}/spaces/{space_id}/environments/{environment}/entries"
        url += f"?{urlencode(query_params)}"

        result = _api_call(token, url, method="GET")

        if result.get("ok") and "result" in result:
            data = result["result"]
            entries = data.get("items", [])
            return {
                "ok": True,
                "data": {
                    "entries": entries,
                    "total": data.get("total", len(entries)),
                    "skip": data.get("skip", 0),
                    "limit": data.get("limit", 100),
                    "includes": data.get("includes", {})
                }
            }
        return result
    except Exception as e:
        logger.exception("search failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "get_entries": get_entries,
    "get_entry": get_entry,
    "create_entry": create_entry,
    "update_entry": update_entry,
    "publish_entry": publish_entry,
    "get_assets": get_assets,
    "get_content_types": get_content_types,
    "search": search,
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
        logger.info(f"Executing contentful.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
