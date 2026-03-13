"""
Webflow Controller for TinyHive

A controller for Webflow CMS API v2 operations.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "site_id": "your-site-id"
}

Environment Variables:
---------------------
WEBFLOW_ACCESS_TOKEN: Bearer token for Webflow API authentication

Required Scopes:
---------------
- sites:read - For list_sites, get_site
- cms:read - For list_collections, get_collection, list_items
- cms:write - For create_item, update_item, publish_items

API Reference:
-------------
https://developers.webflow.com/data/reference
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.webflow")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Webflow API v2 base URL
API_BASE = "https://api.webflow.com/v2"

DEFAULT_TIMEOUT = 60


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
# HTTP Helpers
# =============================================================================

def _get_access_token() -> str:
    """Get the Webflow access token from environment variable."""
    token = os.environ.get("WEBFLOW_ACCESS_TOKEN", "")
    if not token:
        raise ValueError(
            "Environment variable 'WEBFLOW_ACCESS_TOKEN' not set. "
            "Obtain an access token from Webflow dashboard."
        )
    return token


def _api_call(
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Webflow API call."""
    token = _get_access_token()
    url = f"{API_BASE}{endpoint}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "accept": "application/json",
    }

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_data.get("msg", error_body[:500]))
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Webflow API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Webflow API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def list_sites(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all sites accessible with the current access token.

    Required Scope: sites:read

    Params:
        None required
    """
    result = _api_call("/sites")

    if result.get("ok") and "result" in result:
        sites = result["result"].get("sites", [])
        return {
            "ok": True,
            "data": {
                "sites": [
                    {
                        "id": s.get("id"),
                        "displayName": s.get("displayName"),
                        "shortName": s.get("shortName"),
                        "previewUrl": s.get("previewUrl"),
                        "timeZone": s.get("timeZone"),
                        "createdOn": s.get("createdOn"),
                        "lastUpdated": s.get("lastUpdated"),
                        "lastPublished": s.get("lastPublished"),
                    }
                    for s in sites
                ]
            }
        }
    return result


def get_site(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a specific site.

    Required Scope: sites:read

    Params:
        site_id (str): The site ID (default: from profile)
    """
    profile = load_profile(profile_name)
    site_id = params.get("site_id", profile.get("site_id"))

    if not site_id:
        return {"ok": False, "error": "site_id required (in profile or params)"}

    result = _api_call(f"/sites/{site_id}")

    if result.get("ok") and "result" in result:
        s = result["result"]
        return {
            "ok": True,
            "data": {
                "id": s.get("id"),
                "displayName": s.get("displayName"),
                "shortName": s.get("shortName"),
                "previewUrl": s.get("previewUrl"),
                "timeZone": s.get("timeZone"),
                "createdOn": s.get("createdOn"),
                "lastUpdated": s.get("lastUpdated"),
                "lastPublished": s.get("lastPublished"),
                "customDomains": s.get("customDomains", []),
                "locales": s.get("locales", {}),
            }
        }
    return result


def list_collections(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all CMS collections for a site.

    Required Scope: cms:read

    Params:
        site_id (str): The site ID (default: from profile)
    """
    profile = load_profile(profile_name)
    site_id = params.get("site_id", profile.get("site_id"))

    if not site_id:
        return {"ok": False, "error": "site_id required (in profile or params)"}

    result = _api_call(f"/sites/{site_id}/collections")

    if result.get("ok") and "result" in result:
        collections = result["result"].get("collections", [])
        return {
            "ok": True,
            "data": {
                "collections": [
                    {
                        "id": c.get("id"),
                        "displayName": c.get("displayName"),
                        "singularName": c.get("singularName"),
                        "slug": c.get("slug"),
                        "createdOn": c.get("createdOn"),
                        "lastUpdated": c.get("lastUpdated"),
                    }
                    for c in collections
                ]
            }
        }
    return result


def get_collection(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a specific collection including its fields.

    Required Scope: cms:read

    Params:
        collection_id (str): The collection ID (required)
    """
    collection_id = params.get("collection_id")

    if not collection_id:
        return {"ok": False, "error": "collection_id required"}

    result = _api_call(f"/collections/{collection_id}")

    if result.get("ok") and "result" in result:
        c = result["result"]
        return {
            "ok": True,
            "data": {
                "id": c.get("id"),
                "displayName": c.get("displayName"),
                "singularName": c.get("singularName"),
                "slug": c.get("slug"),
                "createdOn": c.get("createdOn"),
                "lastUpdated": c.get("lastUpdated"),
                "fields": c.get("fields", []),
            }
        }
    return result


def list_items(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List items in a collection with pagination.

    Required Scope: cms:read

    Params:
        collection_id (str): The collection ID (required)
        limit (int): Maximum items to return (default: 100, max: 100)
        offset (int): Number of items to skip (default: 0)
    """
    collection_id = params.get("collection_id")

    if not collection_id:
        return {"ok": False, "error": "collection_id required"}

    limit = params.get("limit", 100)
    offset = params.get("offset", 0)

    query_params = {"limit": limit, "offset": offset}
    endpoint = f"/collections/{collection_id}/items?{urlencode(query_params)}"

    result = _api_call(endpoint)

    if result.get("ok") and "result" in result:
        data = result["result"]
        items = data.get("items", [])
        return {
            "ok": True,
            "data": {
                "items": [
                    {
                        "id": item.get("id"),
                        "cmsLocaleId": item.get("cmsLocaleId"),
                        "lastPublished": item.get("lastPublished"),
                        "lastUpdated": item.get("lastUpdated"),
                        "createdOn": item.get("createdOn"),
                        "isArchived": item.get("isArchived"),
                        "isDraft": item.get("isDraft"),
                        "fieldData": item.get("fieldData", {}),
                    }
                    for item in items
                ],
                "pagination": data.get("pagination", {}),
            }
        }
    return result


def create_item(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new item in a collection.

    Required Scope: cms:write

    Params:
        collection_id (str): The collection ID (required)
        fields (dict): Field data for the item (required)
            - Must include all required fields for the collection
            - Field names should match the collection's field slugs
        is_draft (bool): Create as draft (default: False)
        is_archived (bool): Create as archived (default: False)
    """
    collection_id = params.get("collection_id")
    fields = params.get("fields")

    if not collection_id:
        return {"ok": False, "error": "collection_id required"}
    if not fields:
        return {"ok": False, "error": "fields required"}

    is_draft = params.get("is_draft", False)
    is_archived = params.get("is_archived", False)

    payload = {
        "isArchived": is_archived,
        "isDraft": is_draft,
        "fieldData": fields,
    }

    result = _api_call(f"/collections/{collection_id}/items", method="POST", data=payload)

    if result.get("ok") and "result" in result:
        item = result["result"]
        return {
            "ok": True,
            "data": {
                "id": item.get("id"),
                "cmsLocaleId": item.get("cmsLocaleId"),
                "lastPublished": item.get("lastPublished"),
                "lastUpdated": item.get("lastUpdated"),
                "createdOn": item.get("createdOn"),
                "isArchived": item.get("isArchived"),
                "isDraft": item.get("isDraft"),
                "fieldData": item.get("fieldData", {}),
            }
        }
    return result


def update_item(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing item in a collection.

    Required Scope: cms:write

    Params:
        collection_id (str): The collection ID (required)
        item_id (str): The item ID to update (required)
        fields (dict): Field data to update (required)
            - Only include fields you want to change
        is_draft (bool): Set draft status (optional)
        is_archived (bool): Set archived status (optional)
    """
    collection_id = params.get("collection_id")
    item_id = params.get("item_id")
    fields = params.get("fields")

    if not collection_id:
        return {"ok": False, "error": "collection_id required"}
    if not item_id:
        return {"ok": False, "error": "item_id required"}
    if not fields:
        return {"ok": False, "error": "fields required"}

    payload: Dict[str, Any] = {
        "fieldData": fields,
    }

    if "is_draft" in params:
        payload["isDraft"] = params["is_draft"]
    if "is_archived" in params:
        payload["isArchived"] = params["is_archived"]

    result = _api_call(
        f"/collections/{collection_id}/items/{item_id}",
        method="PATCH",
        data=payload
    )

    if result.get("ok") and "result" in result:
        item = result["result"]
        return {
            "ok": True,
            "data": {
                "id": item.get("id"),
                "cmsLocaleId": item.get("cmsLocaleId"),
                "lastPublished": item.get("lastPublished"),
                "lastUpdated": item.get("lastUpdated"),
                "createdOn": item.get("createdOn"),
                "isArchived": item.get("isArchived"),
                "isDraft": item.get("isDraft"),
                "fieldData": item.get("fieldData", {}),
            }
        }
    return result


def publish_items(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Publish one or more items in a collection.

    Required Scope: cms:write

    Params:
        collection_id (str): The collection ID (required)
        item_ids (list): List of item IDs to publish (required)
    """
    collection_id = params.get("collection_id")
    item_ids = params.get("item_ids")

    if not collection_id:
        return {"ok": False, "error": "collection_id required"}
    if not item_ids:
        return {"ok": False, "error": "item_ids required"}
    if not isinstance(item_ids, list):
        return {"ok": False, "error": "item_ids must be a list"}

    payload = {
        "itemIds": item_ids,
    }

    result = _api_call(
        f"/collections/{collection_id}/items/publish",
        method="POST",
        data=payload
    )

    if result.get("ok") and "result" in result:
        data = result["result"]
        return {
            "ok": True,
            "data": {
                "publishedItemIds": data.get("publishedItemIds", []),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_sites": list_sites,
    "get_site": get_site,
    "list_collections": list_collections,
    "get_collection": get_collection,
    "list_items": list_items,
    "create_item": create_item,
    "update_item": update_item,
    "publish_items": publish_items,
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
        return {"ok": False, "error": f"Unknown action: {action}"}

    logger.info(f"Executing webflow.{profile}.{action}")
    return ACTIONS[action](profile, params)
