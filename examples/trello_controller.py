"""
Trello Controller for TinyHive

A controller for interacting with Trello REST API for board and card management.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "api_key_env": "TRELLO_API_KEY",
    "token_env": "TRELLO_TOKEN"
}

Required Permissions:
--------------------
- list_boards: Read access to member's boards
- get_board: Read access to board
- list_lists: Read access to board lists
- create_list: Write access to board
- list_cards: Read access to list cards
- create_card: Write access to list
- update_card: Write access to card
- add_comment: Write access to card

Dependencies:
------------
None (standard library only)

Method IDs:
  controller.trello.{profile}.list_boards
  controller.trello.{profile}.get_board
  controller.trello.{profile}.list_lists
  controller.trello.{profile}.create_list
  controller.trello.{profile}.list_cards
  controller.trello.{profile}.create_card
  controller.trello.{profile}.update_card
  controller.trello.{profile}.add_comment
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.trello")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

BASE_URL = "https://api.trello.com/1"
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


def list_profiles() -> List[str]:
    """List available Trello profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# Authentication
# =============================================================================

def _get_auth_params(profile: Dict[str, Any]) -> Dict[str, str]:
    """
    Get authentication query parameters for Trello API.

    Trello uses API key and token as query parameters.
    """
    api_key_env = profile.get("api_key_env", "TRELLO_API_KEY")
    token_env = profile.get("token_env", "TRELLO_TOKEN")

    api_key = os.environ.get(api_key_env)
    token = os.environ.get(token_env)

    if not api_key:
        raise ValueError(f"Environment variable '{api_key_env}' not set")
    if not token:
        raise ValueError(f"Environment variable '{token_env}' not set")

    return {"key": api_key, "token": token}


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    profile: Dict[str, Any],
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    query_params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated Trello API call.

    Args:
        profile: Profile configuration dict
        endpoint: API endpoint path (e.g., "/members/me/boards")
        method: HTTP method
        data: Request body data (will be JSON encoded)
        query_params: Additional query parameters
        timeout: Request timeout in seconds

    Returns:
        Dict with 'ok' boolean and either 'result' or 'error'
    """
    # Build query parameters with auth
    params = _get_auth_params(profile)
    if query_params:
        params.update(query_params)

    url = f"{BASE_URL}{endpoint}"
    if params:
        url += f"?{urlencode(params)}"

    headers = {
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
            if isinstance(error_data, dict):
                error_message = error_data.get("message", error_body[:500])
            else:
                error_message = str(error_data)[:500]
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Trello API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Trello API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def list_boards(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all boards for the authenticated user.

    Params:
        filter (str): Filter boards by status (optional)
            Options: all, closed, members, open, organization, public, starred
            Default: all
        fields (str): Comma-separated list of fields to return (optional)
            Default: name,desc,closed,url

    Returns:
        List of boards
    """
    profile = load_profile(profile_name)

    query_params = {}

    filter_val = params.get("filter", "all")
    query_params["filter"] = filter_val

    fields = params.get("fields", "name,desc,closed,url,idOrganization")
    query_params["fields"] = fields

    result = _api_call(profile, "/members/me/boards", query_params=query_params)

    if result.get("ok") and "result" in result:
        boards = result["result"]
        return {
            "ok": True,
            "result": {
                "boards": boards,
                "count": len(boards),
            }
        }
    return result


def get_board(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific board.

    Params:
        board_id (str): The board ID - required
        fields (str): Comma-separated list of fields to return (optional)

    Returns:
        Board details
    """
    profile = load_profile(profile_name)

    board_id = params.get("board_id")
    if not board_id:
        return {"ok": False, "error": "board_id is required"}

    query_params = {}
    fields = params.get("fields")
    if fields:
        query_params["fields"] = fields

    result = _api_call(profile, f"/boards/{board_id}", query_params=query_params)

    if result.get("ok") and "result" in result:
        board = result["result"]
        return {
            "ok": True,
            "result": {
                "id": board.get("id"),
                "name": board.get("name"),
                "desc": board.get("desc"),
                "closed": board.get("closed"),
                "url": board.get("url"),
                "shortUrl": board.get("shortUrl"),
                "idOrganization": board.get("idOrganization"),
                "prefs": board.get("prefs"),
            }
        }
    return result


def list_lists(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get all lists on a board.

    Params:
        board_id (str): The board ID - required
        filter (str): Filter lists by status (optional)
            Options: all, closed, none, open
            Default: open
        fields (str): Comma-separated list of fields to return (optional)

    Returns:
        List of lists on the board
    """
    profile = load_profile(profile_name)

    board_id = params.get("board_id")
    if not board_id:
        return {"ok": False, "error": "board_id is required"}

    query_params = {}

    filter_val = params.get("filter", "open")
    query_params["filter"] = filter_val

    fields = params.get("fields")
    if fields:
        query_params["fields"] = fields

    result = _api_call(profile, f"/boards/{board_id}/lists", query_params=query_params)

    if result.get("ok") and "result" in result:
        lists = result["result"]
        return {
            "ok": True,
            "result": {
                "lists": lists,
                "count": len(lists),
            }
        }
    return result


def create_list(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new list on a board.

    Params:
        board_id (str): The board ID - required
        name (str): Name of the list - required
        pos (str|int): Position of the list (optional)
            Options: top, bottom, or a positive number
            Default: top

    Returns:
        Created list details
    """
    profile = load_profile(profile_name)

    board_id = params.get("board_id")
    name = params.get("name")

    if not board_id:
        return {"ok": False, "error": "board_id is required"}
    if not name:
        return {"ok": False, "error": "name is required"}

    query_params = {
        "idBoard": board_id,
        "name": name,
    }

    pos = params.get("pos", "top")
    query_params["pos"] = pos

    result = _api_call(profile, "/lists", method="POST", query_params=query_params)

    if result.get("ok") and "result" in result:
        list_data = result["result"]
        return {
            "ok": True,
            "result": {
                "id": list_data.get("id"),
                "name": list_data.get("name"),
                "closed": list_data.get("closed"),
                "idBoard": list_data.get("idBoard"),
                "pos": list_data.get("pos"),
            }
        }
    return result


def list_cards(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get all cards in a list.

    Params:
        list_id (str): The list ID - required
        filter (str): Filter cards by status (optional)
            Options: all, closed, none, open
            Default: open
        fields (str): Comma-separated list of fields to return (optional)

    Returns:
        List of cards in the list
    """
    profile = load_profile(profile_name)

    list_id = params.get("list_id")
    if not list_id:
        return {"ok": False, "error": "list_id is required"}

    query_params = {}

    filter_val = params.get("filter", "open")
    query_params["filter"] = filter_val

    fields = params.get("fields")
    if fields:
        query_params["fields"] = fields

    result = _api_call(profile, f"/lists/{list_id}/cards", query_params=query_params)

    if result.get("ok") and "result" in result:
        cards = result["result"]
        return {
            "ok": True,
            "result": {
                "cards": cards,
                "count": len(cards),
            }
        }
    return result


def create_card(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new card in a list.

    Params:
        list_id (str): The list ID - required
        name (str): Name of the card - required
        desc (str): Description of the card (optional)
        due (str): Due date in ISO format (optional)
        labels (str): Comma-separated label IDs or colors (optional)
            Colors: blue, green, orange, purple, red, yellow, sky, pink, lime, black
        pos (str|int): Position of the card (optional)
            Options: top, bottom, or a positive number
        idMembers (str): Comma-separated member IDs to assign (optional)

    Returns:
        Created card details
    """
    profile = load_profile(profile_name)

    list_id = params.get("list_id")
    name = params.get("name")

    if not list_id:
        return {"ok": False, "error": "list_id is required"}
    if not name:
        return {"ok": False, "error": "name is required"}

    query_params = {
        "idList": list_id,
        "name": name,
    }

    # Optional parameters
    desc = params.get("desc")
    if desc:
        query_params["desc"] = desc

    due = params.get("due")
    if due:
        query_params["due"] = due

    labels = params.get("labels")
    if labels:
        if isinstance(labels, list):
            query_params["idLabels"] = ",".join(labels)
        else:
            query_params["idLabels"] = labels

    pos = params.get("pos")
    if pos:
        query_params["pos"] = pos

    id_members = params.get("idMembers")
    if id_members:
        if isinstance(id_members, list):
            query_params["idMembers"] = ",".join(id_members)
        else:
            query_params["idMembers"] = id_members

    result = _api_call(profile, "/cards", method="POST", query_params=query_params)

    if result.get("ok") and "result" in result:
        card = result["result"]
        return {
            "ok": True,
            "result": {
                "id": card.get("id"),
                "name": card.get("name"),
                "desc": card.get("desc"),
                "due": card.get("due"),
                "closed": card.get("closed"),
                "idList": card.get("idList"),
                "idBoard": card.get("idBoard"),
                "url": card.get("url"),
                "shortUrl": card.get("shortUrl"),
                "labels": card.get("labels", []),
            }
        }
    return result


def update_card(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing card.

    Params:
        card_id (str): The card ID - required
        fields (dict): Fields to update - required
            Supported fields:
            - name (str): Card name
            - desc (str): Card description
            - due (str): Due date in ISO format (null to remove)
            - dueComplete (bool): Whether due date is complete
            - closed (bool): Whether card is archived
            - idList (str): Move card to different list
            - idBoard (str): Move card to different board
            - pos (str|int): Position (top, bottom, or number)
            - idMembers (str): Comma-separated member IDs
            - idLabels (str): Comma-separated label IDs

    Returns:
        Updated card details
    """
    profile = load_profile(profile_name)

    card_id = params.get("card_id")
    fields = params.get("fields")

    if not card_id:
        return {"ok": False, "error": "card_id is required"}
    if not fields:
        return {"ok": False, "error": "fields is required"}

    # Build query params from fields
    query_params = {}

    # Map supported fields
    field_mapping = [
        "name", "desc", "due", "dueComplete", "closed",
        "idList", "idBoard", "pos", "idMembers", "idLabels"
    ]

    for field in field_mapping:
        if field in fields:
            value = fields[field]
            # Handle list values
            if isinstance(value, list):
                query_params[field] = ",".join(str(v) for v in value)
            elif value is None:
                query_params[field] = "null"
            else:
                query_params[field] = value

    if not query_params:
        return {"ok": False, "error": "No valid fields to update"}

    result = _api_call(profile, f"/cards/{card_id}", method="PUT", query_params=query_params)

    if result.get("ok") and "result" in result:
        card = result["result"]
        return {
            "ok": True,
            "result": {
                "id": card.get("id"),
                "name": card.get("name"),
                "desc": card.get("desc"),
                "due": card.get("due"),
                "closed": card.get("closed"),
                "idList": card.get("idList"),
                "idBoard": card.get("idBoard"),
                "url": card.get("url"),
                "labels": card.get("labels", []),
            }
        }
    return result


def add_comment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a comment to a card.

    Params:
        card_id (str): The card ID - required
        text (str): Comment text - required

    Returns:
        Created comment details
    """
    profile = load_profile(profile_name)

    card_id = params.get("card_id")
    text = params.get("text")

    if not card_id:
        return {"ok": False, "error": "card_id is required"}
    if not text:
        return {"ok": False, "error": "text is required"}

    query_params = {
        "text": text,
    }

    result = _api_call(
        profile,
        f"/cards/{card_id}/actions/comments",
        method="POST",
        query_params=query_params
    )

    if result.get("ok") and "result" in result:
        comment = result["result"]
        return {
            "ok": True,
            "result": {
                "id": comment.get("id"),
                "card_id": card_id,
                "type": comment.get("type"),
                "date": comment.get("date"),
                "text": comment.get("data", {}).get("text"),
                "memberCreator": comment.get("memberCreator", {}).get("fullName"),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_boards": list_boards,
    "get_board": get_board,
    "list_lists": list_lists,
    "create_list": create_list,
    "list_cards": list_cards,
    "create_card": create_card,
    "update_card": update_card,
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
        return {"ok": False, "error": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"}

    try:
        logger.info(f"Executing trello.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
