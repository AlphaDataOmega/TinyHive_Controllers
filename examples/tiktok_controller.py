"""TikTok Controller for TinyHive

A controller for interacting with the TikTok API v2.

Method IDs:
  controller.tiktok.{profile}.get_user_info
  controller.tiktok.{profile}.list_videos
  controller.tiktok.{profile}.get_video_info
  controller.tiktok.{profile}.query_videos
  controller.tiktok.{profile}.get_video_comments
  controller.tiktok.{profile}.search_videos
  controller.tiktok.{profile}.get_user_followers
  controller.tiktok.{profile}.get_user_following

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:

  {
    "access_token_env": "TIKTOK_ACCESS_TOKEN",
    "default_fields": ["id", "title", "create_time", "cover_image_url", "share_url"]
  }

Required Scopes per Action:
  - get_user_info: user.info.basic
  - list_videos: video.list
  - get_video_info: video.list
  - query_videos: video.list
  - get_video_comments: video.list
  - search_videos: research.data.basic
  - get_user_followers: user.info.stats
  - get_user_following: user.info.stats

Dependencies:
  - None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.tiktok")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# TikTok API base URL
TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"

DEFAULT_TIMEOUT = 30


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with TikTok configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available TikTok profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


def _get_access_token(profile: Dict[str, Any]) -> str:
    """Get access token from environment variable specified in profile."""
    env_var = profile.get("access_token_env", "TIKTOK_ACCESS_TOKEN")
    token = os.environ.get(env_var, "")
    if not token:
        raise ValueError(
            f"Environment variable '{env_var}' not set. "
            "Obtain an access token from TikTok Developer Portal."
        )
    return token


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    token: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    query_params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated TikTok API call."""
    url = f"{TIKTOK_API_BASE}{endpoint}"

    if query_params:
        url = f"{url}?{urlencode(query_params)}"

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
                # TikTok API returns error in response body with error code
                if result.get("error", {}).get("code"):
                    error_info = result["error"]
                    return {
                        "ok": False,
                        "error": f"{error_info.get('code')}: {error_info.get('message', 'Unknown error')}"
                    }
                return {"ok": True, "data": result.get("data", result)}
            return {"ok": True, "data": {}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_info = error_data.get("error", {})
            error_message = f"{error_info.get('code', 'unknown')}: {error_info.get('message', error_body[:500])}"
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("TikTok API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in TikTok API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def get_user_info(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get authenticated user's profile information.

    Required Scope: user.info.basic

    Params:
        fields (list): Fields to retrieve (default: from profile or basic fields)
            Available: open_id, union_id, avatar_url, avatar_url_100,
                      avatar_large_url, display_name, bio_description,
                      profile_deep_link, is_verified, follower_count,
                      following_count, likes_count, video_count
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    default_fields = profile.get("default_user_fields", [
        "open_id", "display_name", "avatar_url", "bio_description"
    ])
    fields = params.get("fields", default_fields)

    query_params = {"fields": ",".join(fields)}

    result = _api_call(token, "/user/info/", method="GET", query_params=query_params)

    if result.get("ok") and "data" in result:
        user_data = result["data"].get("user", result["data"])
        return {"ok": True, "data": {"user": user_data}}
    return result


def list_videos(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List authenticated user's videos.

    Required Scope: video.list

    Params:
        cursor (int): Pagination cursor (default: 0)
        max_count (int): Maximum videos to return (default: 20, max: 20)
        fields (list): Video fields to retrieve
            Available: id, title, video_description, duration, cover_image_url,
                      embed_link, embed_html, share_url, like_count, comment_count,
                      share_count, view_count, create_time
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    cursor = params.get("cursor", 0)
    max_count = min(params.get("max_count", 20), 20)

    default_fields = profile.get("default_video_fields", [
        "id", "title", "create_time", "cover_image_url", "share_url"
    ])
    fields = params.get("fields", default_fields)

    query_params = {"fields": ",".join(fields)}

    request_body = {
        "cursor": cursor,
        "max_count": max_count
    }

    result = _api_call(token, "/video/list/", method="POST", data=request_body, query_params=query_params)

    if result.get("ok") and "data" in result:
        data = result["data"]
        return {
            "ok": True,
            "data": {
                "videos": data.get("videos", []),
                "cursor": data.get("cursor", 0),
                "has_more": data.get("has_more", False)
            }
        }
    return result


def get_video_info(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a specific video.

    Required Scope: video.list

    Params:
        video_id (str): The video ID to retrieve (required)
        fields (list): Video fields to retrieve
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    video_id = params.get("video_id")
    if not video_id:
        return {"ok": False, "error": "video_id is required"}

    default_fields = profile.get("default_video_fields", [
        "id", "title", "video_description", "duration", "cover_image_url",
        "share_url", "like_count", "comment_count", "share_count", "view_count", "create_time"
    ])
    fields = params.get("fields", default_fields)

    query_params = {"fields": ",".join(fields)}

    request_body = {
        "filters": {
            "video_ids": [video_id]
        }
    }

    result = _api_call(token, "/video/query/", method="POST", data=request_body, query_params=query_params)

    if result.get("ok") and "data" in result:
        videos = result["data"].get("videos", [])
        if videos:
            return {"ok": True, "data": {"video": videos[0]}}
        return {"ok": False, "error": "Video not found"}
    return result


def query_videos(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Query multiple videos by their IDs.

    Required Scope: video.list

    Params:
        video_ids (list): List of video IDs to retrieve (required, max 20)
        fields (list): Video fields to retrieve
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    video_ids = params.get("video_ids", [])
    if not video_ids:
        return {"ok": False, "error": "video_ids is required"}
    if len(video_ids) > 20:
        return {"ok": False, "error": "Maximum 20 video_ids allowed per request"}

    default_fields = profile.get("default_video_fields", [
        "id", "title", "video_description", "duration", "cover_image_url",
        "share_url", "like_count", "comment_count", "share_count", "view_count", "create_time"
    ])
    fields = params.get("fields", default_fields)

    query_params = {"fields": ",".join(fields)}

    request_body = {
        "filters": {
            "video_ids": video_ids
        }
    }

    result = _api_call(token, "/video/query/", method="POST", data=request_body, query_params=query_params)

    if result.get("ok") and "data" in result:
        return {
            "ok": True,
            "data": {
                "videos": result["data"].get("videos", [])
            }
        }
    return result


def get_video_comments(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List comments on a video.

    Required Scope: video.list

    Params:
        video_id (str): The video ID to get comments for (required)
        cursor (int): Pagination cursor (default: 0)
        max_count (int): Maximum comments to return (default: 20, max: 50)
        fields (list): Comment fields to retrieve
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    video_id = params.get("video_id")
    if not video_id:
        return {"ok": False, "error": "video_id is required"}

    cursor = params.get("cursor", 0)
    max_count = min(params.get("max_count", 20), 50)

    default_fields = ["id", "text", "create_time", "like_count"]
    fields = params.get("fields", default_fields)

    query_params = {"fields": ",".join(fields)}

    request_body = {
        "video_id": video_id,
        "cursor": cursor,
        "max_count": max_count
    }

    result = _api_call(token, "/video/comment/list/", method="POST", data=request_body, query_params=query_params)

    if result.get("ok") and "data" in result:
        data = result["data"]
        return {
            "ok": True,
            "data": {
                "comments": data.get("comments", []),
                "cursor": data.get("cursor", 0),
                "has_more": data.get("has_more", False)
            }
        }
    return result


def search_videos(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for videos by keyword.

    Required Scope: research.data.basic

    Params:
        keyword (str): Search keyword (required)
        cursor (int): Pagination cursor (default: 0)
        max_count (int): Maximum videos to return (default: 20, max: 100)
        start_date (str): Start date filter YYYYMMDD format (optional)
        end_date (str): End date filter YYYYMMDD format (optional)
        region_code (str): Region code filter e.g. 'US' (optional)
        fields (list): Video fields to retrieve
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    keyword = params.get("keyword")
    if not keyword:
        return {"ok": False, "error": "keyword is required"}

    cursor = params.get("cursor", 0)
    max_count = min(params.get("max_count", 20), 100)

    default_fields = profile.get("default_video_fields", [
        "id", "title", "video_description", "create_time", "share_url",
        "like_count", "comment_count", "share_count", "view_count"
    ])
    fields = params.get("fields", default_fields)

    query_params = {"fields": ",".join(fields)}

    request_body = {
        "query": {
            "and": [
                {"operation": "IN", "field_name": "keyword", "field_values": [keyword]}
            ]
        },
        "cursor": cursor,
        "max_count": max_count
    }

    # Add optional filters
    if params.get("start_date"):
        request_body["start_date"] = params["start_date"]
    if params.get("end_date"):
        request_body["end_date"] = params["end_date"]
    if params.get("region_code"):
        request_body["query"]["and"].append({
            "operation": "EQ",
            "field_name": "region_code",
            "field_values": [params["region_code"]]
        })

    result = _api_call(token, "/research/video/query/", method="POST", data=request_body, query_params=query_params)

    if result.get("ok") and "data" in result:
        data = result["data"]
        return {
            "ok": True,
            "data": {
                "videos": data.get("videos", []),
                "cursor": data.get("cursor", 0),
                "has_more": data.get("has_more", False),
                "search_id": data.get("search_id")
            }
        }
    return result


def get_user_followers(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the authenticated user's follower count.

    Required Scope: user.info.stats

    Params:
        None
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    query_params = {"fields": "follower_count"}

    result = _api_call(token, "/user/info/", method="GET", query_params=query_params)

    if result.get("ok") and "data" in result:
        user_data = result["data"].get("user", result["data"])
        return {
            "ok": True,
            "data": {
                "follower_count": user_data.get("follower_count", 0)
            }
        }
    return result


def get_user_following(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the authenticated user's following count.

    Required Scope: user.info.stats

    Params:
        None
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    query_params = {"fields": "following_count"}

    result = _api_call(token, "/user/info/", method="GET", query_params=query_params)

    if result.get("ok") and "data" in result:
        user_data = result["data"].get("user", result["data"])
        return {
            "ok": True,
            "data": {
                "following_count": user_data.get("following_count", 0)
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "get_user_info": get_user_info,
    "list_videos": list_videos,
    "get_video_info": get_video_info,
    "query_videos": query_videos,
    "get_video_comments": get_video_comments,
    "search_videos": search_videos,
    "get_user_followers": get_user_followers,
    "get_user_following": get_user_following,
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
        logger.info(f"Executing tiktok.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
