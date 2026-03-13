"""Example: Notion controller — Pages, Databases, and Blocks integration.

This is an example of how to build a Notion controller.
Copy to controllers/controller_notion/ and customize.

Method IDs:
  controller.notion.{profile}.query_database
  controller.notion.{profile}.create_page
  controller.notion.{profile}.update_page
  controller.notion.{profile}.get_page
  controller.notion.{profile}.append_blocks
  controller.notion.{profile}.search
  controller.notion.{profile}.list_databases
  controller.notion.{profile}.get_database
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict
from urllib.request import Request, urlopen
from urllib.error import HTTPError

log = logging.getLogger("tinyhive.controller.notion")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'")
    return json.loads(path.read_text())


def _get_token(profile: Dict[str, Any]) -> str:
    """Get Notion integration token from environment variable."""
    env_var = profile.get("token_env", "NOTION_TOKEN")
    token = os.environ.get(env_var, "")
    if not token:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return token


def _api_call(
    token: str,
    endpoint: str,
    method: str = "GET",
    data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Make a Notion API call.

    Notion API uses Bearer token authentication and requires
    a Notion-Version header.
    """
    url = f"{BASE_URL}/{endpoint}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=30) as response:
            return {"ok": True, "result": json.loads(response.read().decode("utf-8"))}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("message", error_body[:500])
        except json.JSONDecodeError:
            error_msg = error_body[:500]
        return {"ok": False, "error": f"HTTP {e.code}: {error_msg}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Database Actions
# ---------------------------------------------------------------------------

def query_database(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Query a Notion database.

    Params:
        - database_id: The database ID to query (required)
        - filter: Filter object for the query (optional)
        - sorts: List of sort objects (optional)
        - page_size: Number of results per page (default: 100, max: 100)
        - start_cursor: Cursor for pagination (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    database_id = params.get("database_id")
    if not database_id:
        return {"ok": False, "error": "database_id is required"}

    query_data = {}

    if params.get("filter"):
        query_data["filter"] = params["filter"]

    if params.get("sorts"):
        query_data["sorts"] = params["sorts"]

    page_size = params.get("page_size", 100)
    query_data["page_size"] = min(int(page_size), 100)

    if params.get("start_cursor"):
        query_data["start_cursor"] = params["start_cursor"]

    return _api_call(token, f"databases/{database_id}/query", method="POST", data=query_data)


def list_databases(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List all databases the integration has access to.

    Params:
        - page_size: Number of results per page (default: 100, max: 100)
        - start_cursor: Cursor for pagination (optional)

    Note: Uses the search endpoint with filter for databases.
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    search_data = {
        "filter": {"value": "database", "property": "object"},
    }

    page_size = params.get("page_size", 100)
    search_data["page_size"] = min(int(page_size), 100)

    if params.get("start_cursor"):
        search_data["start_cursor"] = params["start_cursor"]

    return _api_call(token, "search", method="POST", data=search_data)


def get_database(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get database schema and metadata.

    Params:
        - database_id: The database ID to retrieve (required)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    database_id = params.get("database_id")
    if not database_id:
        return {"ok": False, "error": "database_id is required"}

    return _api_call(token, f"databases/{database_id}")


# ---------------------------------------------------------------------------
# Page Actions
# ---------------------------------------------------------------------------

def create_page(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new page in a database.

    Params:
        - database_id: The parent database ID (required)
        - properties: Page properties matching database schema (required)
        - children: List of block objects for page content (optional)
        - icon: Icon object (emoji or external URL) (optional)
        - cover: Cover object (external URL) (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    database_id = params.get("database_id")
    properties = params.get("properties")

    if not database_id:
        return {"ok": False, "error": "database_id is required"}
    if not properties:
        return {"ok": False, "error": "properties is required"}

    page_data = {
        "parent": {"database_id": database_id},
        "properties": properties,
    }

    if params.get("children"):
        page_data["children"] = params["children"]

    if params.get("icon"):
        page_data["icon"] = params["icon"]

    if params.get("cover"):
        page_data["cover"] = params["cover"]

    return _api_call(token, "pages", method="POST", data=page_data)


def update_page(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Update page properties.

    Params:
        - page_id: The page ID to update (required)
        - properties: Properties to update (optional)
        - archived: Set to True to archive the page (optional)
        - icon: Icon object (emoji or external URL) (optional)
        - cover: Cover object (external URL) (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    page_id = params.get("page_id")
    if not page_id:
        return {"ok": False, "error": "page_id is required"}

    update_data = {}

    if params.get("properties"):
        update_data["properties"] = params["properties"]

    if params.get("archived") is not None:
        update_data["archived"] = params["archived"]

    if params.get("icon"):
        update_data["icon"] = params["icon"]

    if params.get("cover"):
        update_data["cover"] = params["cover"]

    if not update_data:
        return {"ok": False, "error": "At least one of properties, archived, icon, or cover is required"}

    return _api_call(token, f"pages/{page_id}", method="PATCH", data=update_data)


def get_page(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get a page by ID.

    Params:
        - page_id: The page ID to retrieve (required)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    page_id = params.get("page_id")
    if not page_id:
        return {"ok": False, "error": "page_id is required"}

    return _api_call(token, f"pages/{page_id}")


# ---------------------------------------------------------------------------
# Block Actions
# ---------------------------------------------------------------------------

def append_blocks(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Append blocks to a page or block.

    Params:
        - page_id: The page or block ID to append to (required)
        - children: List of block objects to append (required)
        - after: Block ID to insert after (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    page_id = params.get("page_id")
    children = params.get("children")

    if not page_id:
        return {"ok": False, "error": "page_id is required"}
    if not children:
        return {"ok": False, "error": "children is required"}

    append_data = {"children": children}

    if params.get("after"):
        append_data["after"] = params["after"]

    return _api_call(token, f"blocks/{page_id}/children", method="PATCH", data=append_data)


# ---------------------------------------------------------------------------
# Search Action
# ---------------------------------------------------------------------------

def search(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Search pages and databases.

    Params:
        - query: Search query text (optional)
        - filter: Object with 'value' set to 'page' or 'database' (optional)
        - sort: Sort object with 'direction' and 'timestamp' (optional)
        - page_size: Number of results per page (default: 100, max: 100)
        - start_cursor: Cursor for pagination (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    search_data = {}

    if params.get("query"):
        search_data["query"] = params["query"]

    if params.get("filter"):
        search_data["filter"] = params["filter"]

    if params.get("sort"):
        search_data["sort"] = params["sort"]

    page_size = params.get("page_size", 100)
    search_data["page_size"] = min(int(page_size), 100)

    if params.get("start_cursor"):
        search_data["start_cursor"] = params["start_cursor"]

    return _api_call(token, "search", method="POST", data=search_data)


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

ACTIONS = {
    "query_database": query_database,
    "create_page": create_page,
    "update_page": update_page,
    "get_page": get_page,
    "append_blocks": append_blocks,
    "search": search,
    "list_databases": list_databases,
    "get_database": get_database,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """Dispatch an action by name with a profile."""
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action '{action}'"}
    return ACTIONS[action](profile, params)
