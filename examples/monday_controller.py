"""
Monday.com Controller for TinyHive

A controller for interacting with Monday.com GraphQL API for work management,
boards, items, and collaboration.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "api_key_env": "MONDAY_API_KEY"
}

Required Permissions (Monday.com API Key):
------------------------------------------
- list_boards: read access to boards
- get_board: read access to boards
- list_items: read access to items
- create_item: write access to items
- update_item: write access to items
- delete_item: write access to items
- add_update: write access to updates
- create_group: write access to boards

Dependencies:
------------
None (standard library only)

Method IDs:
  controller.monday.{profile}.list_boards
  controller.monday.{profile}.get_board
  controller.monday.{profile}.list_items
  controller.monday.{profile}.create_item
  controller.monday.{profile}.update_item
  controller.monday.{profile}.delete_item
  controller.monday.{profile}.add_update
  controller.monday.{profile}.create_group
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger("tinyhive.controller.monday")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

MONDAY_API_URL = "https://api.monday.com/v2"
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


def _get_api_key(profile: Dict[str, Any]) -> str:
    """Get Monday.com API key from environment variable specified in profile."""
    api_key_env = profile.get("api_key_env", "MONDAY_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ValueError(f"Environment variable '{api_key_env}' not set")
    return api_key


# =============================================================================
# GraphQL Helper
# =============================================================================

def _graphql_call(
    api_key: str,
    query: str,
    variables: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated Monday.com GraphQL API call.

    Args:
        api_key: Monday.com API key
        query: GraphQL query string
        variables: GraphQL variables dict
        timeout: Request timeout in seconds

    Returns:
        Dict with 'ok' boolean and either 'data' or 'error'
    """
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
        "API-Version": "2024-10",
    }

    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    body = json.dumps(payload).encode("utf-8")

    try:
        req = Request(MONDAY_API_URL, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            result = json.loads(response_body)

            # GraphQL can return errors even with 200 status
            if "errors" in result:
                error_messages = [e.get("message", str(e)) for e in result["errors"]]
                error_str = "; ".join(error_messages)
                logger.error("Monday.com GraphQL error: %s", error_str)
                return {"ok": False, "error": f"GraphQL error: {error_str}"}

            return {"ok": True, "data": result.get("data", {})}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            if "errors" in error_data:
                error_messages = [err.get("message", str(err)) for err in error_data["errors"]]
                error_message = "; ".join(error_messages)
            else:
                error_message = error_data.get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Monday.com API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Monday.com API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Helper Functions
# =============================================================================

def _escape_graphql_string(s: str) -> str:
    """Escape a string for safe inclusion in a GraphQL query."""
    if not s:
        return ""
    # Escape backslashes first, then quotes, then newlines
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


# =============================================================================
# Actions
# =============================================================================

def list_boards(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List boards accessible to the user.

    Params:
        limit (int): Maximum number of boards to return (default: 25, max: 100)
        page (int): Page number for pagination (default: 1)

    Returns:
        List of boards with basic details
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    limit = min(params.get("limit", 25), 100)
    page = params.get("page", 1)

    query = """
    query ListBoards($limit: Int!, $page: Int!) {
        boards(limit: $limit, page: $page) {
            id
            name
            description
            state
            board_kind
            workspace_id
            permissions
            item_terminology
            items_count
            columns {
                id
                title
                type
                settings_str
            }
            groups {
                id
                title
                color
                position
            }
            owners {
                id
                name
                email
            }
            creator {
                id
                name
                email
            }
        }
    }
    """

    result = _graphql_call(api_key, query, {"limit": limit, "page": page})

    if result.get("ok") and "data" in result:
        boards_data = result["data"].get("boards", [])

        boards = []
        for board in boards_data:
            boards.append({
                "id": board.get("id"),
                "name": board.get("name"),
                "description": board.get("description"),
                "state": board.get("state"),
                "board_kind": board.get("board_kind"),
                "workspace_id": board.get("workspace_id"),
                "permissions": board.get("permissions"),
                "item_terminology": board.get("item_terminology"),
                "items_count": board.get("items_count"),
                "columns": board.get("columns", []),
                "groups": board.get("groups", []),
                "owners": board.get("owners", []),
                "creator": board.get("creator"),
            })

        return {
            "ok": True,
            "result": {
                "boards": boards,
                "count": len(boards),
                "page": page,
                "limit": limit,
            }
        }
    return result


def get_board(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get detailed information about a specific board including items.

    Params:
        board_id (str): The board ID (required)

    Returns:
        Board details including items, columns, and groups
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    board_id = params.get("board_id")
    if not board_id:
        return {"ok": False, "error": "board_id is required"}

    query = """
    query GetBoard($boardId: ID!) {
        boards(ids: [$boardId]) {
            id
            name
            description
            state
            board_kind
            workspace_id
            permissions
            item_terminology
            items_count
            columns {
                id
                title
                type
                description
                settings_str
            }
            groups {
                id
                title
                color
                position
                archived
            }
            owners {
                id
                name
                email
            }
            creator {
                id
                name
                email
            }
            subscribers {
                id
                name
                email
            }
            items_page(limit: 100) {
                cursor
                items {
                    id
                    name
                    state
                    created_at
                    updated_at
                    creator_id
                    group {
                        id
                        title
                    }
                    column_values {
                        id
                        type
                        text
                        value
                    }
                }
            }
        }
    }
    """

    result = _graphql_call(api_key, query, {"boardId": str(board_id)})

    if result.get("ok") and "data" in result:
        boards = result["data"].get("boards", [])
        if not boards:
            return {"ok": False, "error": f"Board not found: {board_id}"}

        board = boards[0]
        items_page = board.get("items_page", {})

        return {
            "ok": True,
            "result": {
                "id": board.get("id"),
                "name": board.get("name"),
                "description": board.get("description"),
                "state": board.get("state"),
                "board_kind": board.get("board_kind"),
                "workspace_id": board.get("workspace_id"),
                "permissions": board.get("permissions"),
                "item_terminology": board.get("item_terminology"),
                "items_count": board.get("items_count"),
                "columns": board.get("columns", []),
                "groups": board.get("groups", []),
                "owners": board.get("owners", []),
                "creator": board.get("creator"),
                "subscribers": board.get("subscribers", []),
                "items": items_page.get("items", []),
                "items_cursor": items_page.get("cursor"),
            }
        }
    return result


def list_items(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List items in a board.

    Params:
        board_id (str): The board ID (required)
        limit (int): Maximum number of items to return (default: 50, max: 500)

    Returns:
        List of items with their column values
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    board_id = params.get("board_id")
    if not board_id:
        return {"ok": False, "error": "board_id is required"}

    limit = min(params.get("limit", 50), 500)

    query = """
    query ListItems($boardId: ID!, $limit: Int!) {
        boards(ids: [$boardId]) {
            items_page(limit: $limit) {
                cursor
                items {
                    id
                    name
                    state
                    created_at
                    updated_at
                    creator_id
                    group {
                        id
                        title
                        color
                    }
                    column_values {
                        id
                        type
                        text
                        value
                    }
                    subitems {
                        id
                        name
                        state
                    }
                }
            }
        }
    }
    """

    result = _graphql_call(api_key, query, {"boardId": str(board_id), "limit": limit})

    if result.get("ok") and "data" in result:
        boards = result["data"].get("boards", [])
        if not boards:
            return {"ok": False, "error": f"Board not found: {board_id}"}

        items_page = boards[0].get("items_page", {})
        items = items_page.get("items", [])

        return {
            "ok": True,
            "result": {
                "items": items,
                "count": len(items),
                "cursor": items_page.get("cursor"),
            }
        }
    return result


def create_item(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new item in a board.

    Params:
        board_id (str): The board ID (required)
        item_name (str): Name of the item (required)
        group_id (str): Group ID to create the item in (optional)
        column_values (dict): Column values as JSON object (optional)
            Example: {"status": {"label": "Working on it"}, "date": {"date": "2024-01-15"}}

    Returns:
        Created item details
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    board_id = params.get("board_id")
    item_name = params.get("item_name")

    if not board_id:
        return {"ok": False, "error": "board_id is required"}
    if not item_name:
        return {"ok": False, "error": "item_name is required"}

    # Build the mutation
    variables: Dict[str, Any] = {
        "boardId": str(board_id),
        "itemName": item_name,
    }

    group_clause = ""
    if params.get("group_id"):
        variables["groupId"] = params["group_id"]
        group_clause = "group_id: $groupId,"

    column_values_clause = ""
    if params.get("column_values"):
        # Monday.com expects column_values as a JSON string
        variables["columnValues"] = json.dumps(params["column_values"])
        column_values_clause = "column_values: $columnValues,"

    query = f"""
    mutation CreateItem($boardId: ID!, $itemName: String!, {"$groupId: String," if params.get("group_id") else ""} {"$columnValues: JSON," if params.get("column_values") else ""}) {{
        create_item(
            board_id: $boardId,
            item_name: $itemName,
            {group_clause}
            {column_values_clause}
        ) {{
            id
            name
            state
            created_at
            group {{
                id
                title
            }}
            column_values {{
                id
                type
                text
                value
            }}
            board {{
                id
                name
            }}
        }}
    }}
    """

    result = _graphql_call(api_key, query, variables)

    if result.get("ok") and "data" in result:
        item = result["data"].get("create_item")
        if not item:
            return {"ok": False, "error": "Failed to create item"}

        return {
            "ok": True,
            "result": {
                "id": item.get("id"),
                "name": item.get("name"),
                "state": item.get("state"),
                "created_at": item.get("created_at"),
                "group": item.get("group"),
                "column_values": item.get("column_values", []),
                "board": item.get("board"),
            }
        }
    return result


def update_item(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update column values of an existing item.

    Params:
        board_id (str): The board ID (required)
        item_id (str): The item ID to update (required)
        column_values (dict): Column values to update as JSON object (required)
            Example: {"status": {"label": "Done"}, "text": "Updated text"}

    Returns:
        Updated item details
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    board_id = params.get("board_id")
    item_id = params.get("item_id")
    column_values = params.get("column_values")

    if not board_id:
        return {"ok": False, "error": "board_id is required"}
    if not item_id:
        return {"ok": False, "error": "item_id is required"}
    if not column_values:
        return {"ok": False, "error": "column_values is required"}

    # Monday.com expects column_values as a JSON string
    column_values_str = json.dumps(column_values)

    query = """
    mutation UpdateItem($boardId: ID!, $itemId: ID!, $columnValues: JSON!) {
        change_multiple_column_values(
            board_id: $boardId,
            item_id: $itemId,
            column_values: $columnValues
        ) {
            id
            name
            state
            updated_at
            group {
                id
                title
            }
            column_values {
                id
                type
                text
                value
            }
        }
    }
    """

    variables = {
        "boardId": str(board_id),
        "itemId": str(item_id),
        "columnValues": column_values_str,
    }

    result = _graphql_call(api_key, query, variables)

    if result.get("ok") and "data" in result:
        item = result["data"].get("change_multiple_column_values")
        if not item:
            return {"ok": False, "error": "Failed to update item"}

        return {
            "ok": True,
            "result": {
                "id": item.get("id"),
                "name": item.get("name"),
                "state": item.get("state"),
                "updated_at": item.get("updated_at"),
                "group": item.get("group"),
                "column_values": item.get("column_values", []),
            }
        }
    return result


def delete_item(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete an item.

    Params:
        item_id (str): The item ID to delete (required)

    Returns:
        Deleted item ID
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    item_id = params.get("item_id")
    if not item_id:
        return {"ok": False, "error": "item_id is required"}

    query = """
    mutation DeleteItem($itemId: ID!) {
        delete_item(item_id: $itemId) {
            id
        }
    }
    """

    result = _graphql_call(api_key, query, {"itemId": str(item_id)})

    if result.get("ok") and "data" in result:
        deleted_item = result["data"].get("delete_item")
        if not deleted_item:
            return {"ok": False, "error": "Failed to delete item"}

        return {
            "ok": True,
            "result": {
                "id": deleted_item.get("id"),
                "deleted": True,
            }
        }
    return result


def add_update(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add an update (comment) to an item.

    Params:
        item_id (str): The item ID to add update to (required)
        body (str): The update body/text (required)

    Returns:
        Created update details
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    item_id = params.get("item_id")
    body = params.get("body")

    if not item_id:
        return {"ok": False, "error": "item_id is required"}
    if not body:
        return {"ok": False, "error": "body is required"}

    query = """
    mutation AddUpdate($itemId: ID!, $body: String!) {
        create_update(item_id: $itemId, body: $body) {
            id
            body
            text_body
            created_at
            updated_at
            creator {
                id
                name
                email
            }
        }
    }
    """

    result = _graphql_call(api_key, query, {"itemId": str(item_id), "body": body})

    if result.get("ok") and "data" in result:
        update = result["data"].get("create_update")
        if not update:
            return {"ok": False, "error": "Failed to add update"}

        return {
            "ok": True,
            "result": {
                "id": update.get("id"),
                "body": update.get("body"),
                "text_body": update.get("text_body"),
                "created_at": update.get("created_at"),
                "updated_at": update.get("updated_at"),
                "creator": update.get("creator"),
            }
        }
    return result


def create_group(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new group in a board.

    Params:
        board_id (str): The board ID (required)
        group_name (str): Name of the group (required)

    Returns:
        Created group details
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    board_id = params.get("board_id")
    group_name = params.get("group_name")

    if not board_id:
        return {"ok": False, "error": "board_id is required"}
    if not group_name:
        return {"ok": False, "error": "group_name is required"}

    query = """
    mutation CreateGroup($boardId: ID!, $groupName: String!) {
        create_group(board_id: $boardId, group_name: $groupName) {
            id
            title
            color
            position
            archived
        }
    }
    """

    result = _graphql_call(api_key, query, {"boardId": str(board_id), "groupName": group_name})

    if result.get("ok") and "data" in result:
        group = result["data"].get("create_group")
        if not group:
            return {"ok": False, "error": "Failed to create group"}

        return {
            "ok": True,
            "result": {
                "id": group.get("id"),
                "title": group.get("title"),
                "color": group.get("color"),
                "position": group.get("position"),
                "archived": group.get("archived"),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_boards": list_boards,
    "get_board": get_board,
    "list_items": list_items,
    "create_item": create_item,
    "update_item": update_item,
    "delete_item": delete_item,
    "add_update": add_update,
    "create_group": create_group,
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
        logger.info(f"Executing monday.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
