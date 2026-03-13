"""
Confluence Controller for TinyHive

A controller for interacting with Atlassian Confluence REST API.
Supports both Confluence Cloud and Confluence Server/Data Center.

Method IDs:
  controller.confluence.{profile}.list_spaces
  controller.confluence.{profile}.get_space
  controller.confluence.{profile}.list_pages
  controller.confluence.{profile}.get_page
  controller.confluence.{profile}.create_page
  controller.confluence.{profile}.update_page
  controller.confluence.{profile}.search
  controller.confluence.{profile}.add_comment

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Confluence Cloud profile:
{
    "base_url": "https://yoursite.atlassian.net/wiki",
    "email_env": "CONFLUENCE_EMAIL",
    "api_token_env": "CONFLUENCE_API_TOKEN"
}

Confluence Server/Data Center profile:
{
    "base_url": "https://confluence.yourcompany.com",
    "email_env": "CONFLUENCE_USERNAME",
    "api_token_env": "CONFLUENCE_PASSWORD"
}

Required Permissions:
--------------------
- list_spaces: View spaces
- get_space: View space
- list_pages: View pages
- get_page: View page
- create_page: Create page in space
- update_page: Edit page
- search: View content
- add_comment: Add comments

Dependencies:
------------
None (standard library only)
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

logger = logging.getLogger("tinyhive.controller.confluence")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile from the profiles directory."""
    profile_path = PROFILES_DIR / f"{name}.json"
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {name}. Create {profile_path}")

    with open(profile_path) as f:
        return json.load(f)


def list_profiles() -> List[str]:
    """List available Confluence profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# Authentication
# =============================================================================

def _get_auth_header(profile: Dict[str, Any]) -> str:
    """Get Basic Auth header value from profile configuration."""
    email_env = profile.get("email_env", "CONFLUENCE_EMAIL")
    token_env = profile.get("api_token_env", "CONFLUENCE_API_TOKEN")

    email = os.environ.get(email_env)
    api_token = os.environ.get(token_env)

    if not email:
        raise ValueError(f"Environment variable '{email_env}' not set")
    if not api_token:
        raise ValueError(f"Environment variable '{token_env}' not set")

    credentials = f"{email}:{api_token}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    profile: Dict[str, Any],
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Confluence API call."""
    base_url = profile.get("base_url", "").rstrip("/")
    if not base_url:
        return {"ok": False, "error": "base_url not configured in profile"}

    url = f"{base_url}/rest/api{endpoint}"

    headers = {
        "Authorization": _get_auth_header(profile),
        "Content-Type": "application/json",
        "Accept": "application/json",
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
            error_message = error_data.get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Confluence API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Confluence API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def list_spaces(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List Confluence spaces.

    Params:
        limit (int): Maximum number of spaces to return (default: 25, max: 100)
        start (int): Starting index for pagination (default: 0)
        type (str): Filter by space type: 'global', 'personal' (optional)
    """
    try:
        profile = load_profile(profile_name)

        query_params = {}
        if params.get("limit"):
            query_params["limit"] = min(int(params["limit"]), 100)
        if params.get("start"):
            query_params["start"] = int(params["start"])
        if params.get("type"):
            query_params["type"] = params["type"]

        endpoint = "/space"
        if query_params:
            endpoint += "?" + urlencode(query_params)

        result = _api_call(profile, endpoint)

        if result.get("ok") and "result" in result:
            spaces = result["result"].get("results", [])
            return {
                "ok": True,
                "data": {
                    "spaces": [
                        {
                            "id": s.get("id"),
                            "key": s.get("key"),
                            "name": s.get("name"),
                            "type": s.get("type"),
                            "status": s.get("status"),
                        }
                        for s in spaces
                    ],
                    "start": result["result"].get("start", 0),
                    "limit": result["result"].get("limit", 25),
                    "size": result["result"].get("size", len(spaces)),
                }
            }
        return result
    except Exception as e:
        logger.exception("list_spaces failed")
        return {"ok": False, "error": str(e)}


def get_space(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific space.

    Params:
        space_key (str): The space key (required)
    """
    try:
        profile = load_profile(profile_name)

        space_key = params.get("space_key")
        if not space_key:
            return {"ok": False, "error": "space_key is required"}

        endpoint = f"/space/{quote(space_key, safe='')}"

        result = _api_call(profile, endpoint)

        if result.get("ok") and "result" in result:
            space = result["result"]
            return {
                "ok": True,
                "data": {
                    "id": space.get("id"),
                    "key": space.get("key"),
                    "name": space.get("name"),
                    "type": space.get("type"),
                    "status": space.get("status"),
                    "description": space.get("description", {}).get("plain", {}).get("value"),
                    "homepage": space.get("homepage", {}).get("id") if space.get("homepage") else None,
                }
            }
        return result
    except Exception as e:
        logger.exception("get_space failed")
        return {"ok": False, "error": str(e)}


def list_pages(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List pages in a space or search by title.

    Params:
        space_key (str): Filter by space key (optional)
        title (str): Filter by exact page title (optional)
        limit (int): Maximum number of pages to return (default: 25, max: 100)
        start (int): Starting index for pagination (default: 0)
    """
    try:
        profile = load_profile(profile_name)

        query_params = {"type": "page"}
        if params.get("space_key"):
            query_params["spaceKey"] = params["space_key"]
        if params.get("title"):
            query_params["title"] = params["title"]
        if params.get("limit"):
            query_params["limit"] = min(int(params["limit"]), 100)
        if params.get("start"):
            query_params["start"] = int(params["start"])

        endpoint = "/content?" + urlencode(query_params)

        result = _api_call(profile, endpoint)

        if result.get("ok") and "result" in result:
            pages = result["result"].get("results", [])
            return {
                "ok": True,
                "data": {
                    "pages": [
                        {
                            "id": p.get("id"),
                            "title": p.get("title"),
                            "type": p.get("type"),
                            "status": p.get("status"),
                            "space_key": p.get("space", {}).get("key") if p.get("space") else None,
                        }
                        for p in pages
                    ],
                    "start": result["result"].get("start", 0),
                    "limit": result["result"].get("limit", 25),
                    "size": result["result"].get("size", len(pages)),
                }
            }
        return result
    except Exception as e:
        logger.exception("list_pages failed")
        return {"ok": False, "error": str(e)}


def get_page(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a specific page with its content.

    Params:
        page_id (str): The page ID (required)
        expand (str): Comma-separated list of properties to expand
                      (default: 'body.storage,version,space')
    """
    try:
        profile = load_profile(profile_name)

        page_id = params.get("page_id")
        if not page_id:
            return {"ok": False, "error": "page_id is required"}

        expand = params.get("expand", "body.storage,version,space")
        endpoint = f"/content/{quote(str(page_id), safe='')}?expand={quote(expand, safe=',')}"

        result = _api_call(profile, endpoint)

        if result.get("ok") and "result" in result:
            page = result["result"]
            return {
                "ok": True,
                "data": {
                    "id": page.get("id"),
                    "title": page.get("title"),
                    "type": page.get("type"),
                    "status": page.get("status"),
                    "space_key": page.get("space", {}).get("key") if page.get("space") else None,
                    "version": page.get("version", {}).get("number"),
                    "body": page.get("body", {}).get("storage", {}).get("value"),
                    "created_by": page.get("version", {}).get("by", {}).get("displayName"),
                    "created_at": page.get("version", {}).get("when"),
                }
            }
        return result
    except Exception as e:
        logger.exception("get_page failed")
        return {"ok": False, "error": str(e)}


def create_page(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new page in a space.

    Params:
        space_key (str): The space key where the page will be created (required)
        title (str): The page title (required)
        body (str): The page content in Confluence storage format (XHTML) (required)
        parent_id (str): Parent page ID for creating a child page (optional)
    """
    try:
        profile = load_profile(profile_name)

        space_key = params.get("space_key")
        title = params.get("title")
        body = params.get("body")

        if not space_key:
            return {"ok": False, "error": "space_key is required"}
        if not title:
            return {"ok": False, "error": "title is required"}
        if not body:
            return {"ok": False, "error": "body is required"}

        data: Dict[str, Any] = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {
                "storage": {
                    "value": body,
                    "representation": "storage"
                }
            }
        }

        parent_id = params.get("parent_id")
        if parent_id:
            data["ancestors"] = [{"id": str(parent_id)}]

        result = _api_call(profile, "/content", method="POST", data=data)

        if result.get("ok") and "result" in result:
            page = result["result"]
            return {
                "ok": True,
                "data": {
                    "id": page.get("id"),
                    "title": page.get("title"),
                    "space_key": page.get("space", {}).get("key") if page.get("space") else space_key,
                    "version": page.get("version", {}).get("number", 1),
                    "status": page.get("status"),
                }
            }
        return result
    except Exception as e:
        logger.exception("create_page failed")
        return {"ok": False, "error": str(e)}


def update_page(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing page.

    Params:
        page_id (str): The page ID to update (required)
        title (str): The new page title (required)
        body (str): The new page content in Confluence storage format (required)
        version (int): The current version number of the page (required)
                       The API will increment this automatically.
    """
    try:
        profile = load_profile(profile_name)

        page_id = params.get("page_id")
        title = params.get("title")
        body = params.get("body")
        version = params.get("version")

        if not page_id:
            return {"ok": False, "error": "page_id is required"}
        if not title:
            return {"ok": False, "error": "title is required"}
        if not body:
            return {"ok": False, "error": "body is required"}
        if version is None:
            return {"ok": False, "error": "version is required"}

        data = {
            "type": "page",
            "title": title,
            "body": {
                "storage": {
                    "value": body,
                    "representation": "storage"
                }
            },
            "version": {
                "number": int(version) + 1
            }
        }

        endpoint = f"/content/{quote(str(page_id), safe='')}"
        result = _api_call(profile, endpoint, method="PUT", data=data)

        if result.get("ok") and "result" in result:
            page = result["result"]
            return {
                "ok": True,
                "data": {
                    "id": page.get("id"),
                    "title": page.get("title"),
                    "version": page.get("version", {}).get("number"),
                    "status": page.get("status"),
                }
            }
        return result
    except Exception as e:
        logger.exception("update_page failed")
        return {"ok": False, "error": str(e)}


def search(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search Confluence content using CQL (Confluence Query Language).

    Params:
        cql (str): CQL query string (required)
                   Examples:
                     - 'text ~ "search term"'
                     - 'space = "MYSPACE" AND title ~ "doc"'
                     - 'type = page AND lastModified > "2024-01-01"'
        limit (int): Maximum number of results (default: 25, max: 100)
        start (int): Starting index for pagination (default: 0)
    """
    try:
        profile = load_profile(profile_name)

        cql = params.get("cql")
        if not cql:
            return {"ok": False, "error": "cql is required"}

        query_params = {"cql": cql}
        if params.get("limit"):
            query_params["limit"] = min(int(params["limit"]), 100)
        if params.get("start"):
            query_params["start"] = int(params["start"])

        endpoint = "/content/search?" + urlencode(query_params)

        result = _api_call(profile, endpoint)

        if result.get("ok") and "result" in result:
            results = result["result"].get("results", [])
            return {
                "ok": True,
                "data": {
                    "results": [
                        {
                            "id": r.get("id"),
                            "title": r.get("title"),
                            "type": r.get("type"),
                            "status": r.get("status"),
                            "space_key": r.get("space", {}).get("key") if r.get("space") else None,
                        }
                        for r in results
                    ],
                    "start": result["result"].get("start", 0),
                    "limit": result["result"].get("limit", 25),
                    "size": result["result"].get("size", len(results)),
                    "total_size": result["result"].get("totalSize"),
                }
            }
        return result
    except Exception as e:
        logger.exception("search failed")
        return {"ok": False, "error": str(e)}


def add_comment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a comment to a page.

    Params:
        page_id (str): The page ID to comment on (required)
        body (str): The comment content in Confluence storage format (required)
    """
    try:
        profile = load_profile(profile_name)

        page_id = params.get("page_id")
        body = params.get("body")

        if not page_id:
            return {"ok": False, "error": "page_id is required"}
        if not body:
            return {"ok": False, "error": "body is required"}

        data = {
            "type": "comment",
            "container": {
                "id": str(page_id),
                "type": "page"
            },
            "body": {
                "storage": {
                    "value": body,
                    "representation": "storage"
                }
            }
        }

        result = _api_call(profile, "/content", method="POST", data=data)

        if result.get("ok") and "result" in result:
            comment = result["result"]
            return {
                "ok": True,
                "data": {
                    "id": comment.get("id"),
                    "type": comment.get("type"),
                    "status": comment.get("status"),
                    "container_id": page_id,
                    "created_by": comment.get("version", {}).get("by", {}).get("displayName"),
                    "created_at": comment.get("version", {}).get("when"),
                }
            }
        return result
    except Exception as e:
        logger.exception("add_comment failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_spaces": list_spaces,
    "get_space": get_space,
    "list_pages": list_pages,
    "get_page": get_page,
    "create_page": create_page,
    "update_page": update_page,
    "search": search,
    "add_comment": add_comment,
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
        logger.info(f"Executing confluence.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
