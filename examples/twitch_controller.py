"""
Twitch Controller for TinyHive

A controller for interacting with the Twitch Helix API.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "client_id_env": "TWITCH_CLIENT_ID",
    "oauth_token_env": "TWITCH_OAUTH_TOKEN"
}

Environment Variables:
---------------------
- TWITCH_CLIENT_ID: Your Twitch application Client ID
- TWITCH_OAUTH_TOKEN: OAuth Bearer token (without "Bearer " prefix)

To obtain credentials:
1. Register an app at https://dev.twitch.tv/console/apps
2. Get Client ID from the app dashboard
3. Generate an OAuth token via OAuth flow or https://twitchtokengenerator.com

Required Scopes (depending on action):
- Most read actions: No scope required (app access token)
- Chat settings: moderator:read:chat_settings (for moderator info)

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
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.twitch")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Twitch Helix API base URL
TWITCH_API_BASE = "https://api.twitch.tv/helix"

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


def _get_credentials(profile: Dict[str, Any]) -> tuple:
    """Get Client ID and OAuth token from environment variables."""
    client_id_env = profile.get("client_id_env", "TWITCH_CLIENT_ID")
    oauth_token_env = profile.get("oauth_token_env", "TWITCH_OAUTH_TOKEN")

    client_id = os.environ.get(client_id_env)
    oauth_token = os.environ.get(oauth_token_env)

    if not client_id:
        raise ValueError(f"Missing environment variable: {client_id_env}")
    if not oauth_token:
        raise ValueError(f"Missing environment variable: {oauth_token_env}")

    return client_id, oauth_token


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    client_id: str,
    oauth_token: str,
    endpoint: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated Twitch Helix API call.

    Args:
        client_id: Twitch application Client ID
        oauth_token: OAuth Bearer token
        endpoint: API endpoint (e.g., "/users")
        method: HTTP method
        params: Query parameters
        data: JSON body data (for POST/PATCH)
        timeout: Request timeout in seconds

    Returns:
        Dict with "ok" status and "data" or "error"
    """
    url = f"{TWITCH_API_BASE}{endpoint}"

    if params:
        # Filter out None values and build query string
        filtered_params = {k: v for k, v in params.items() if v is not None}
        if filtered_params:
            url += "?" + urlencode(filtered_params, doseq=True)

    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {oauth_token}",
        "Content-Type": "application/json",
    }

    body = None
    if data:
        body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                result = json.loads(response_body)
                return {"ok": True, "data": result}
            return {"ok": True, "data": {}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Twitch API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Twitch API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def get_users(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get information about one or more Twitch users.

    Params:
        id (str|list): User ID(s) to look up (up to 100)
        login (str|list): User login name(s) to look up (up to 100)

    At least one of id or login is required.

    Returns:
        data: List of user objects with id, login, display_name, type,
              broadcaster_type, description, profile_image_url, etc.
    """
    try:
        profile = load_profile(profile_name)
        client_id, oauth_token = _get_credentials(profile)

        user_id = params.get("id")
        login = params.get("login")

        if not user_id and not login:
            return {"ok": False, "error": "At least one of 'id' or 'login' is required"}

        query_params = {}
        if user_id:
            query_params["id"] = user_id if isinstance(user_id, list) else [user_id]
        if login:
            query_params["login"] = login if isinstance(login, list) else [login]

        return _api_call(client_id, oauth_token, "/users", params=query_params)
    except Exception as e:
        logger.exception("get_users failed")
        return {"ok": False, "error": str(e)}


def get_streams(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get information about active streams.

    Params:
        user_id (str|list): Filter by user ID(s) (up to 100)
        user_login (str|list): Filter by user login(s) (up to 100)
        game_id (str|list): Filter by game ID(s) (up to 100)
        type (str): Stream type filter ("all" or "live", default: "all")
        language (str|list): Filter by language(s)
        first (int): Number of results (1-100, default: 20)
        before (str): Cursor for backward pagination
        after (str): Cursor for forward pagination

    Returns:
        data: List of stream objects with id, user_id, user_login, game_id,
              game_name, type, title, viewer_count, started_at, language, etc.
        pagination: Cursor for pagination
    """
    try:
        profile = load_profile(profile_name)
        client_id, oauth_token = _get_credentials(profile)

        query_params = {}

        user_id = params.get("user_id")
        if user_id:
            query_params["user_id"] = user_id if isinstance(user_id, list) else [user_id]

        user_login = params.get("user_login")
        if user_login:
            query_params["user_login"] = user_login if isinstance(user_login, list) else [user_login]

        game_id = params.get("game_id")
        if game_id:
            query_params["game_id"] = game_id if isinstance(game_id, list) else [game_id]

        if params.get("type"):
            query_params["type"] = params["type"]
        if params.get("language"):
            lang = params["language"]
            query_params["language"] = lang if isinstance(lang, list) else [lang]
        if params.get("first"):
            query_params["first"] = min(100, max(1, int(params["first"])))
        if params.get("before"):
            query_params["before"] = params["before"]
        if params.get("after"):
            query_params["after"] = params["after"]

        return _api_call(client_id, oauth_token, "/streams", params=query_params)
    except Exception as e:
        logger.exception("get_streams failed")
        return {"ok": False, "error": str(e)}


def get_channel(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get channel information for one or more broadcasters.

    Params:
        broadcaster_id (str|list): Broadcaster user ID(s) (required, up to 100)

    Returns:
        data: List of channel objects with broadcaster_id, broadcaster_login,
              broadcaster_name, game_name, game_id, broadcaster_language,
              title, delay, tags, etc.
    """
    try:
        profile = load_profile(profile_name)
        client_id, oauth_token = _get_credentials(profile)

        broadcaster_id = params.get("broadcaster_id")
        if not broadcaster_id:
            return {"ok": False, "error": "'broadcaster_id' is required"}

        query_params = {
            "broadcaster_id": broadcaster_id if isinstance(broadcaster_id, list) else [broadcaster_id]
        }

        return _api_call(client_id, oauth_token, "/channels", params=query_params)
    except Exception as e:
        logger.exception("get_channel failed")
        return {"ok": False, "error": str(e)}


def search_channels(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for channels by query string.

    Params:
        query (str): Search query (required)
        first (int): Number of results (1-100, default: 20)
        after (str): Cursor for forward pagination
        live_only (bool): Filter to only live channels (default: false)

    Returns:
        data: List of channel objects with broadcaster_language, broadcaster_login,
              display_name, game_id, game_name, id, is_live, tags, title, etc.
        pagination: Cursor for pagination
    """
    try:
        profile = load_profile(profile_name)
        client_id, oauth_token = _get_credentials(profile)

        query = params.get("query")
        if not query:
            return {"ok": False, "error": "'query' is required"}

        query_params = {"query": query}

        if params.get("first"):
            query_params["first"] = min(100, max(1, int(params["first"])))
        if params.get("after"):
            query_params["after"] = params["after"]
        if params.get("live_only"):
            query_params["live_only"] = "true" if params["live_only"] else "false"

        return _api_call(client_id, oauth_token, "/search/channels", params=query_params)
    except Exception as e:
        logger.exception("search_channels failed")
        return {"ok": False, "error": str(e)}


def get_videos(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get video information by video ID, user, or game.

    Params:
        id (str|list): Video ID(s) to look up (up to 100)
        user_id (str): User ID to get videos for
        game_id (str): Game ID to get videos for
        type (str): Video type filter ("all", "upload", "archive", "highlight")
        language (str): Filter by language
        period (str): Time period ("all", "day", "week", "month")
        sort (str): Sort order ("time", "trending", "views")
        first (int): Number of results (1-100, default: 20)
        before (str): Cursor for backward pagination
        after (str): Cursor for forward pagination

    One of id, user_id, or game_id is required.

    Returns:
        data: List of video objects with id, stream_id, user_id, user_login,
              user_name, title, description, created_at, published_at,
              url, thumbnail_url, viewable, view_count, language, type, duration
        pagination: Cursor for pagination
    """
    try:
        profile = load_profile(profile_name)
        client_id, oauth_token = _get_credentials(profile)

        video_id = params.get("id")
        user_id = params.get("user_id")
        game_id = params.get("game_id")

        if not video_id and not user_id and not game_id:
            return {"ok": False, "error": "One of 'id', 'user_id', or 'game_id' is required"}

        query_params = {}

        if video_id:
            query_params["id"] = video_id if isinstance(video_id, list) else [video_id]
        if user_id:
            query_params["user_id"] = user_id
        if game_id:
            query_params["game_id"] = game_id
        if params.get("type"):
            query_params["type"] = params["type"]
        if params.get("language"):
            query_params["language"] = params["language"]
        if params.get("period"):
            query_params["period"] = params["period"]
        if params.get("sort"):
            query_params["sort"] = params["sort"]
        if params.get("first"):
            query_params["first"] = min(100, max(1, int(params["first"])))
        if params.get("before"):
            query_params["before"] = params["before"]
        if params.get("after"):
            query_params["after"] = params["after"]

        return _api_call(client_id, oauth_token, "/videos", params=query_params)
    except Exception as e:
        logger.exception("get_videos failed")
        return {"ok": False, "error": str(e)}


def get_clips(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get clip information.

    Params:
        id (str|list): Clip ID(s) to look up (up to 100)
        broadcaster_id (str): Broadcaster ID to get clips for
        game_id (str): Game ID to get clips for
        started_at (str): RFC3339 timestamp for clip creation start
        ended_at (str): RFC3339 timestamp for clip creation end
        first (int): Number of results (1-100, default: 20)
        before (str): Cursor for backward pagination
        after (str): Cursor for forward pagination

    One of id, broadcaster_id, or game_id is required.

    Returns:
        data: List of clip objects with id, url, embed_url, broadcaster_id,
              broadcaster_name, creator_id, creator_name, video_id, game_id,
              language, title, view_count, created_at, thumbnail_url, duration
        pagination: Cursor for pagination
    """
    try:
        profile = load_profile(profile_name)
        client_id, oauth_token = _get_credentials(profile)

        clip_id = params.get("id")
        broadcaster_id = params.get("broadcaster_id")
        game_id = params.get("game_id")

        if not clip_id and not broadcaster_id and not game_id:
            return {"ok": False, "error": "One of 'id', 'broadcaster_id', or 'game_id' is required"}

        query_params = {}

        if clip_id:
            query_params["id"] = clip_id if isinstance(clip_id, list) else [clip_id]
        if broadcaster_id:
            query_params["broadcaster_id"] = broadcaster_id
        if game_id:
            query_params["game_id"] = game_id
        if params.get("started_at"):
            query_params["started_at"] = params["started_at"]
        if params.get("ended_at"):
            query_params["ended_at"] = params["ended_at"]
        if params.get("first"):
            query_params["first"] = min(100, max(1, int(params["first"])))
        if params.get("before"):
            query_params["before"] = params["before"]
        if params.get("after"):
            query_params["after"] = params["after"]

        return _api_call(client_id, oauth_token, "/clips", params=query_params)
    except Exception as e:
        logger.exception("get_clips failed")
        return {"ok": False, "error": str(e)}


def get_games(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get game/category information.

    Params:
        id (str|list): Game ID(s) to look up (up to 100)
        name (str|list): Game name(s) to look up (up to 100)
        igdb_id (str|list): IGDB ID(s) to look up (up to 100)

    At least one of id, name, or igdb_id is required.

    Returns:
        data: List of game objects with id, name, box_art_url, igdb_id
    """
    try:
        profile = load_profile(profile_name)
        client_id, oauth_token = _get_credentials(profile)

        game_id = params.get("id")
        name = params.get("name")
        igdb_id = params.get("igdb_id")

        if not game_id and not name and not igdb_id:
            return {"ok": False, "error": "At least one of 'id', 'name', or 'igdb_id' is required"}

        query_params = {}

        if game_id:
            query_params["id"] = game_id if isinstance(game_id, list) else [game_id]
        if name:
            query_params["name"] = name if isinstance(name, list) else [name]
        if igdb_id:
            query_params["igdb_id"] = igdb_id if isinstance(igdb_id, list) else [igdb_id]

        return _api_call(client_id, oauth_token, "/games", params=query_params)
    except Exception as e:
        logger.exception("get_games failed")
        return {"ok": False, "error": str(e)}


def get_chat_settings(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get chat settings for a broadcaster's channel.

    Params:
        broadcaster_id (str): Broadcaster user ID (required)
        moderator_id (str): Moderator user ID (optional, for additional fields)

    Returns:
        data: List containing chat settings object with broadcaster_id,
              emote_mode, follower_mode, follower_mode_duration,
              slow_mode, slow_mode_wait_time, subscriber_mode,
              unique_chat_mode, non_moderator_chat_delay,
              non_moderator_chat_delay_duration (if moderator_id provided)
    """
    try:
        profile = load_profile(profile_name)
        client_id, oauth_token = _get_credentials(profile)

        broadcaster_id = params.get("broadcaster_id")
        if not broadcaster_id:
            return {"ok": False, "error": "'broadcaster_id' is required"}

        query_params = {"broadcaster_id": broadcaster_id}

        if params.get("moderator_id"):
            query_params["moderator_id"] = params["moderator_id"]

        return _api_call(client_id, oauth_token, "/chat/settings", params=query_params)
    except Exception as e:
        logger.exception("get_chat_settings failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "get_users": get_users,
    "get_streams": get_streams,
    "get_channel": get_channel,
    "search_channels": search_channels,
    "get_videos": get_videos,
    "get_clips": get_clips,
    "get_games": get_games,
    "get_chat_settings": get_chat_settings,
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

    logger.info(f"Executing twitch.{profile}.{action}")
    return ACTIONS[action](profile, params)
