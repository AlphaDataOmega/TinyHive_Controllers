"""Pinterest Controller for TinyHive

A controller for integrating with Pinterest API v5.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Pinterest profile:
{
    "token_env": "PINTEREST_ACCESS_TOKEN"
}

Required OAuth Scopes:
----------------------
- user_accounts:read    - For get_user_account
- boards:read           - For list_boards
- boards:write          - For create_board
- pins:read             - For get_pin, list_pins, search_pins
- pins:write            - For create_pin
- analytics:read        - For get_analytics

Dependencies:
-------------
- None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.pinterest")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Pinterest API v5 base URL
BASE_URL = "https://api.pinterest.com/v5"

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


def _get_token(profile: Dict[str, Any]) -> str:
    """Get the Pinterest access token from environment variable."""
    token_env = profile.get("token_env", "PINTEREST_ACCESS_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(
            f"Environment variable '{token_env}' not set. "
            "Set your Pinterest access token in this environment variable."
        )
    return token


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    token: str,
    endpoint: str,
    method: str = "GET",
    data: Dict[str, Any] = None,
    query_params: Dict[str, Any] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated Pinterest API call.

    Args:
        token: Pinterest access token
        endpoint: API endpoint (e.g., 'user_account')
        method: HTTP method (GET, POST, etc.)
        data: Request body data (for POST/PUT/PATCH)
        query_params: URL query parameters
        timeout: Request timeout in seconds

    Returns:
        Response dict with 'ok' field and result/error
    """
    url = f"{BASE_URL}/{endpoint}"

    if query_params:
        # Filter out None values
        filtered_params = {k: v for k, v in query_params.items() if v is not None}
        if filtered_params:
            url = f"{url}?{urlencode(filtered_params)}"

    headers = {
        "Authorization": f"Bearer {token}",
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
            else:
                result = {}
            return {"ok": True, "result": result}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("message", error_body[:500])
        except json.JSONDecodeError:
            error_msg = error_body[:500]
        logger.error("Pinterest HTTP error %d: %s", e.code, error_msg)
        return {"ok": False, "error": f"HTTP {e.code}: {error_msg}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Pinterest API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def get_user_account(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the authenticated user's Pinterest account info.

    Params:
        (none required)

    Returns:
        ok (bool): Success status
        result (dict): User account info including username, account_type,
                       profile_image, website_url, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        return _api_call(token, "user_account")

    except Exception as e:
        logger.exception("get_user_account failed")
        return {"ok": False, "error": str(e)}


def list_boards(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all boards for the authenticated user.

    Params:
        bookmark (str): Cursor for pagination (optional)
        page_size (int): Number of boards to return (default: 25, max: 250)
        privacy (str): Filter by privacy: 'PUBLIC', 'PROTECTED', 'SECRET' (optional)

    Returns:
        ok (bool): Success status
        result (dict): Response including items (list of boards) and bookmark for pagination
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        query_params = {
            "bookmark": params.get("bookmark"),
            "page_size": params.get("page_size", 25),
            "privacy": params.get("privacy"),
        }

        return _api_call(token, "boards", query_params=query_params)

    except Exception as e:
        logger.exception("list_boards failed")
        return {"ok": False, "error": str(e)}


def create_pin(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new pin on a board.

    Params:
        board_id (str): The board ID to pin to (required)
        title (str): Pin title (optional, max 100 chars)
        description (str): Pin description (optional, max 800 chars)
        link (str): Destination link URL (optional)
        media_source (dict): Media source object (required), one of:
            - {"source_type": "image_url", "url": "https://..."}
            - {"source_type": "image_base64", "content_type": "image/png", "data": "base64..."}
            - {"source_type": "video_id", "cover_image_url": "https://...", "media_id": "..."}
        alt_text (str): Alt text for accessibility (optional, max 500 chars)

    Returns:
        ok (bool): Success status
        result (dict): Created pin object with id, title, description, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        board_id = params.get("board_id")
        media_source = params.get("media_source")

        if not board_id:
            return {"ok": False, "error": "board_id is required"}
        if not media_source:
            return {"ok": False, "error": "media_source is required"}

        pin_data = {
            "board_id": board_id,
            "media_source": media_source,
        }

        if params.get("title"):
            pin_data["title"] = params["title"][:100]

        if params.get("description"):
            pin_data["description"] = params["description"][:800]

        if params.get("link"):
            pin_data["link"] = params["link"]

        if params.get("alt_text"):
            pin_data["alt_text"] = params["alt_text"][:500]

        return _api_call(token, "pins", method="POST", data=pin_data)

    except Exception as e:
        logger.exception("create_pin failed")
        return {"ok": False, "error": str(e)}


def get_pin(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific pin.

    Params:
        pin_id (str): The pin ID to retrieve (required)
        ad_account_id (str): Include if pin belongs to an ad account (optional)

    Returns:
        ok (bool): Success status
        result (dict): Pin object with id, title, description, link, media, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        pin_id = params.get("pin_id")
        if not pin_id:
            return {"ok": False, "error": "pin_id is required"}

        query_params = {
            "ad_account_id": params.get("ad_account_id"),
        }

        return _api_call(token, f"pins/{pin_id}", query_params=query_params)

    except Exception as e:
        logger.exception("get_pin failed")
        return {"ok": False, "error": str(e)}


def list_pins(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List pins on a specific board.

    Params:
        board_id (str): The board ID to list pins from (required)
        bookmark (str): Cursor for pagination (optional)
        page_size (int): Number of pins to return (default: 25, max: 250)

    Returns:
        ok (bool): Success status
        result (dict): Response including items (list of pins) and bookmark for pagination
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        board_id = params.get("board_id")
        if not board_id:
            return {"ok": False, "error": "board_id is required"}

        query_params = {
            "bookmark": params.get("bookmark"),
            "page_size": params.get("page_size", 25),
        }

        return _api_call(token, f"boards/{board_id}/pins", query_params=query_params)

    except Exception as e:
        logger.exception("list_pins failed")
        return {"ok": False, "error": str(e)}


def create_board(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new board.

    Params:
        name (str): Board name (required, max 50 chars)
        description (str): Board description (optional, max 500 chars)
        privacy (str): Board privacy: 'PUBLIC', 'PROTECTED', 'SECRET' (default: 'PUBLIC')

    Returns:
        ok (bool): Success status
        result (dict): Created board object with id, name, description, privacy, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        name = params.get("name")
        if not name:
            return {"ok": False, "error": "name is required"}

        board_data = {
            "name": name[:50],
        }

        if params.get("description"):
            board_data["description"] = params["description"][:500]

        privacy = params.get("privacy", "PUBLIC")
        if privacy in ("PUBLIC", "PROTECTED", "SECRET"):
            board_data["privacy"] = privacy
        else:
            return {"ok": False, "error": "privacy must be 'PUBLIC', 'PROTECTED', or 'SECRET'"}

        return _api_call(token, "boards", method="POST", data=board_data)

    except Exception as e:
        logger.exception("create_board failed")
        return {"ok": False, "error": str(e)}


def get_analytics(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get analytics for a specific pin.

    Params:
        pin_id (str): The pin ID to get analytics for (required)
        start_date (str): Start date in YYYY-MM-DD format (required)
        end_date (str): End date in YYYY-MM-DD format (required)
        metric_types (list): List of metrics to retrieve (required), options:
            - 'IMPRESSION', 'SAVE', 'PIN_CLICK', 'OUTBOUND_CLICK',
            - 'VIDEO_MRC_VIEW', 'VIDEO_AVG_WATCH_TIME', 'VIDEO_V50_WATCH_TIME',
            - 'QUARTILE_95_PERCENT_VIEW', 'VIDEO_10S_VIEW', 'VIDEO_START'
        app_types (str): App type filter: 'ALL', 'MOBILE', 'TABLET', 'WEB' (default: 'ALL')
        split_field (str): How to split results: 'NO_SPLIT', 'APP_TYPE' (default: 'NO_SPLIT')
        ad_account_id (str): Include if pin belongs to an ad account (optional)

    Returns:
        ok (bool): Success status
        result (dict): Analytics data including metrics and daily breakdowns
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        pin_id = params.get("pin_id")
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        metric_types = params.get("metric_types")

        if not pin_id:
            return {"ok": False, "error": "pin_id is required"}
        if not start_date:
            return {"ok": False, "error": "start_date is required"}
        if not end_date:
            return {"ok": False, "error": "end_date is required"}
        if not metric_types:
            return {"ok": False, "error": "metric_types is required"}

        # Convert list to comma-separated string if needed
        if isinstance(metric_types, list):
            metric_types = ",".join(metric_types)

        query_params = {
            "start_date": start_date,
            "end_date": end_date,
            "metric_types": metric_types,
            "app_types": params.get("app_types", "ALL"),
            "split_field": params.get("split_field", "NO_SPLIT"),
            "ad_account_id": params.get("ad_account_id"),
        }

        return _api_call(token, f"pins/{pin_id}/analytics", query_params=query_params)

    except Exception as e:
        logger.exception("get_analytics failed")
        return {"ok": False, "error": str(e)}


def search_pins(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for pins.

    Params:
        query (str): Search query string (required)
        bookmark (str): Cursor for pagination (optional)

    Returns:
        ok (bool): Success status
        result (dict): Response including items (list of pins) and bookmark for pagination

    Note: This uses the user's saved pins search endpoint. For broader search,
    consider using the catalogs or ads endpoints if available.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        query = params.get("query")
        if not query:
            return {"ok": False, "error": "query is required"}

        query_params = {
            "query": query,
            "bookmark": params.get("bookmark"),
        }

        return _api_call(token, "search/pins", query_params=query_params)

    except Exception as e:
        logger.exception("search_pins failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "get_user_account": get_user_account,
    "list_boards": list_boards,
    "create_pin": create_pin,
    "get_pin": get_pin,
    "list_pins": list_pins,
    "create_board": create_board,
    "get_analytics": get_analytics,
    "search_pins": search_pins,
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

    logger.info(f"Executing pinterest.{profile}.{action}")
    return ACTIONS[action](profile, params)
