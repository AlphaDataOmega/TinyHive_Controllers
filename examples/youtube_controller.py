"""
YouTube Controller for TinyHive

A controller for the YouTube Data API v3, providing read-only access to
videos, channels, playlists, comments, and captions.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "api_key_env": "YOUTUBE_API_KEY",
    "default_max_results": 25,
    "default_parts": ["snippet", "contentDetails", "statistics"]
}

Required Permissions:
--------------------
- YouTube Data API v3 must be enabled in Google Cloud Console
- API key with YouTube Data API v3 access

Dependencies:
------------
- None (standard library only)

Method IDs:
  controller.youtube.{profile}.search
  controller.youtube.{profile}.get_video
  controller.youtube.{profile}.list_videos
  controller.youtube.{profile}.get_channel
  controller.youtube.{profile}.list_playlists
  controller.youtube.{profile}.get_playlist_items
  controller.youtube.{profile}.list_comments
  controller.youtube.{profile}.get_captions
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.youtube")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# YouTube Data API v3 base URL
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

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


def _get_api_key(profile: Dict[str, Any]) -> str:
    """Get the API key from environment variable specified in profile."""
    env_var = profile.get("api_key_env", "YOUTUBE_API_KEY")
    api_key = os.environ.get(env_var)
    if not api_key:
        raise ValueError(f"Environment variable '{env_var}' not set. "
                         "Set it to your YouTube Data API v3 key.")
    return api_key


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    api_key: str,
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make a YouTube Data API v3 call.

    Args:
        api_key: YouTube API key
        endpoint: API endpoint (e.g., 'search', 'videos', 'channels')
        params: Query parameters (key will be added automatically)
        timeout: Request timeout in seconds

    Returns:
        Dict with 'ok', 'result'/'data', and optionally 'error'
    """
    params = params or {}
    params["key"] = api_key

    # Build URL with query parameters
    query_string = urlencode(params, doseq=True)
    url = f"{YOUTUBE_API_BASE}/{endpoint}?{query_string}"

    headers = {
        "Accept": "application/json",
    }

    try:
        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            data = json.loads(response_body)
            return {"ok": True, "data": data}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("error", {}).get("message", error_body[:500])
            error_reason = error_data.get("error", {}).get("errors", [{}])[0].get("reason", "unknown")
        except json.JSONDecodeError:
            error_message = error_body[:500]
            error_reason = "unknown"
        logger.error("YouTube API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}", "reason": error_reason}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in YouTube API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def search(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for YouTube videos, channels, or playlists.

    Params:
        q (str): Search query (required)
        type (str): Resource type - 'video', 'channel', 'playlist' (default: 'video')
        max_results (int): Maximum results to return, 1-50 (default: 25)
        order (str): Sort order - 'date', 'rating', 'relevance', 'title',
                     'videoCount', 'viewCount' (default: 'relevance')
        channel_id (str): Limit search to a specific channel (optional)
        page_token (str): Token for pagination (optional)

    Returns:
        Dict with 'ok', 'data' containing search results and pagination info
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    query = params.get("q")
    if not query:
        return {"ok": False, "error": "q (search query) is required"}

    default_max = profile.get("default_max_results", 25)
    max_results = min(params.get("max_results", default_max), 50)

    api_params = {
        "part": "snippet",
        "q": query,
        "type": params.get("type", "video"),
        "maxResults": max_results,
        "order": params.get("order", "relevance"),
    }

    if params.get("channel_id"):
        api_params["channelId"] = params["channel_id"]

    if params.get("page_token"):
        api_params["pageToken"] = params["page_token"]

    result = _api_call(api_key, "search", api_params)

    if result.get("ok"):
        data = result["data"]
        items = []
        for item in data.get("items", []):
            item_info = {
                "kind": item.get("id", {}).get("kind", "").replace("youtube#", ""),
                "id": (item.get("id", {}).get("videoId") or
                       item.get("id", {}).get("channelId") or
                       item.get("id", {}).get("playlistId")),
                "title": item.get("snippet", {}).get("title"),
                "description": item.get("snippet", {}).get("description"),
                "channel_id": item.get("snippet", {}).get("channelId"),
                "channel_title": item.get("snippet", {}).get("channelTitle"),
                "published_at": item.get("snippet", {}).get("publishedAt"),
                "thumbnail": item.get("snippet", {}).get("thumbnails", {}).get("default", {}).get("url"),
            }
            items.append(item_info)

        return {
            "ok": True,
            "data": {
                "items": items,
                "total_results": data.get("pageInfo", {}).get("totalResults", 0),
                "results_per_page": data.get("pageInfo", {}).get("resultsPerPage", 0),
                "next_page_token": data.get("nextPageToken"),
                "prev_page_token": data.get("prevPageToken"),
            }
        }

    return result


def get_video(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a single video.

    Params:
        video_id (str): YouTube video ID (required)
        parts (list): Parts to include - 'snippet', 'contentDetails', 'statistics',
                      'status', 'player', 'topicDetails', 'recordingDetails',
                      'liveStreamingDetails' (default: from profile or ['snippet', 'contentDetails', 'statistics'])

    Returns:
        Dict with 'ok', 'data' containing video details
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    video_id = params.get("video_id")
    if not video_id:
        return {"ok": False, "error": "video_id is required"}

    default_parts = profile.get("default_parts", ["snippet", "contentDetails", "statistics"])
    parts = params.get("parts", default_parts)
    if isinstance(parts, list):
        parts = ",".join(parts)

    api_params = {
        "part": parts,
        "id": video_id,
    }

    result = _api_call(api_key, "videos", api_params)

    if result.get("ok"):
        items = result["data"].get("items", [])
        if not items:
            return {"ok": False, "error": f"Video not found: {video_id}"}

        video = items[0]
        return {
            "ok": True,
            "data": _format_video(video)
        }

    return result


def list_videos(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for multiple videos.

    Params:
        video_ids (list): List of YouTube video IDs (required, max 50)
        parts (list): Parts to include (default: from profile)

    Returns:
        Dict with 'ok', 'data' containing list of video details
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    video_ids = params.get("video_ids")
    if not video_ids:
        return {"ok": False, "error": "video_ids is required"}

    if isinstance(video_ids, list):
        video_ids = ",".join(video_ids[:50])  # API limit

    default_parts = profile.get("default_parts", ["snippet", "contentDetails", "statistics"])
    parts = params.get("parts", default_parts)
    if isinstance(parts, list):
        parts = ",".join(parts)

    api_params = {
        "part": parts,
        "id": video_ids,
    }

    result = _api_call(api_key, "videos", api_params)

    if result.get("ok"):
        items = result["data"].get("items", [])
        videos = [_format_video(v) for v in items]
        return {
            "ok": True,
            "data": {
                "videos": videos,
                "count": len(videos)
            }
        }

    return result


def _format_video(video: Dict[str, Any]) -> Dict[str, Any]:
    """Format a video response into a cleaner structure."""
    snippet = video.get("snippet", {})
    content_details = video.get("contentDetails", {})
    statistics = video.get("statistics", {})
    status = video.get("status", {})

    return {
        "id": video.get("id"),
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "channel_id": snippet.get("channelId"),
        "channel_title": snippet.get("channelTitle"),
        "published_at": snippet.get("publishedAt"),
        "tags": snippet.get("tags", []),
        "category_id": snippet.get("categoryId"),
        "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
        "duration": content_details.get("duration"),
        "dimension": content_details.get("dimension"),
        "definition": content_details.get("definition"),
        "caption": content_details.get("caption"),
        "licensed_content": content_details.get("licensedContent"),
        "view_count": int(statistics.get("viewCount", 0)) if statistics.get("viewCount") else None,
        "like_count": int(statistics.get("likeCount", 0)) if statistics.get("likeCount") else None,
        "comment_count": int(statistics.get("commentCount", 0)) if statistics.get("commentCount") else None,
        "privacy_status": status.get("privacyStatus"),
        "embeddable": status.get("embeddable"),
    }


def get_channel(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get channel information.

    Params:
        channel_id (str): YouTube channel ID (required)
        parts (list): Parts to include - 'snippet', 'contentDetails', 'statistics',
                      'brandingSettings', 'topicDetails', 'status'
                      (default: ['snippet', 'contentDetails', 'statistics'])

    Returns:
        Dict with 'ok', 'data' containing channel details
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    channel_id = params.get("channel_id")
    if not channel_id:
        return {"ok": False, "error": "channel_id is required"}

    parts = params.get("parts", ["snippet", "contentDetails", "statistics"])
    if isinstance(parts, list):
        parts = ",".join(parts)

    api_params = {
        "part": parts,
        "id": channel_id,
    }

    result = _api_call(api_key, "channels", api_params)

    if result.get("ok"):
        items = result["data"].get("items", [])
        if not items:
            return {"ok": False, "error": f"Channel not found: {channel_id}"}

        channel = items[0]
        snippet = channel.get("snippet", {})
        content_details = channel.get("contentDetails", {})
        statistics = channel.get("statistics", {})

        return {
            "ok": True,
            "data": {
                "id": channel.get("id"),
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "custom_url": snippet.get("customUrl"),
                "published_at": snippet.get("publishedAt"),
                "country": snippet.get("country"),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                "uploads_playlist": content_details.get("relatedPlaylists", {}).get("uploads"),
                "view_count": int(statistics.get("viewCount", 0)) if statistics.get("viewCount") else None,
                "subscriber_count": int(statistics.get("subscriberCount", 0)) if statistics.get("subscriberCount") else None,
                "hidden_subscriber_count": statistics.get("hiddenSubscriberCount", False),
                "video_count": int(statistics.get("videoCount", 0)) if statistics.get("videoCount") else None,
            }
        }

    return result


def list_playlists(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List playlists for a channel.

    Params:
        channel_id (str): YouTube channel ID (required)
        max_results (int): Maximum results to return, 1-50 (default: 25)
        page_token (str): Token for pagination (optional)

    Returns:
        Dict with 'ok', 'data' containing list of playlists
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    channel_id = params.get("channel_id")
    if not channel_id:
        return {"ok": False, "error": "channel_id is required"}

    default_max = profile.get("default_max_results", 25)
    max_results = min(params.get("max_results", default_max), 50)

    api_params = {
        "part": "snippet,contentDetails",
        "channelId": channel_id,
        "maxResults": max_results,
    }

    if params.get("page_token"):
        api_params["pageToken"] = params["page_token"]

    result = _api_call(api_key, "playlists", api_params)

    if result.get("ok"):
        data = result["data"]
        playlists = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            content_details = item.get("contentDetails", {})
            playlists.append({
                "id": item.get("id"),
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "channel_id": snippet.get("channelId"),
                "channel_title": snippet.get("channelTitle"),
                "published_at": snippet.get("publishedAt"),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                "item_count": content_details.get("itemCount", 0),
            })

        return {
            "ok": True,
            "data": {
                "playlists": playlists,
                "total_results": data.get("pageInfo", {}).get("totalResults", 0),
                "next_page_token": data.get("nextPageToken"),
                "prev_page_token": data.get("prevPageToken"),
            }
        }

    return result


def get_playlist_items(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get videos in a playlist.

    Params:
        playlist_id (str): YouTube playlist ID (required)
        max_results (int): Maximum results to return, 1-50 (default: 25)
        page_token (str): Token for pagination (optional)

    Returns:
        Dict with 'ok', 'data' containing playlist items
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    playlist_id = params.get("playlist_id")
    if not playlist_id:
        return {"ok": False, "error": "playlist_id is required"}

    default_max = profile.get("default_max_results", 25)
    max_results = min(params.get("max_results", default_max), 50)

    api_params = {
        "part": "snippet,contentDetails",
        "playlistId": playlist_id,
        "maxResults": max_results,
    }

    if params.get("page_token"):
        api_params["pageToken"] = params["page_token"]

    result = _api_call(api_key, "playlistItems", api_params)

    if result.get("ok"):
        data = result["data"]
        items = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            content_details = item.get("contentDetails", {})
            resource_id = snippet.get("resourceId", {})
            items.append({
                "id": item.get("id"),
                "video_id": resource_id.get("videoId"),
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "channel_id": snippet.get("channelId"),
                "channel_title": snippet.get("channelTitle"),
                "position": snippet.get("position"),
                "published_at": snippet.get("publishedAt"),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                "video_published_at": content_details.get("videoPublishedAt"),
            })

        return {
            "ok": True,
            "data": {
                "items": items,
                "playlist_id": playlist_id,
                "total_results": data.get("pageInfo", {}).get("totalResults", 0),
                "next_page_token": data.get("nextPageToken"),
                "prev_page_token": data.get("prevPageToken"),
            }
        }

    return result


def list_comments(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List top-level comments on a video.

    Params:
        video_id (str): YouTube video ID (required)
        max_results (int): Maximum results to return, 1-100 (default: 25)
        order (str): Sort order - 'time', 'relevance' (default: 'relevance')
        page_token (str): Token for pagination (optional)

    Returns:
        Dict with 'ok', 'data' containing comment threads
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    video_id = params.get("video_id")
    if not video_id:
        return {"ok": False, "error": "video_id is required"}

    default_max = profile.get("default_max_results", 25)
    max_results = min(params.get("max_results", default_max), 100)

    api_params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": max_results,
        "order": params.get("order", "relevance"),
    }

    if params.get("page_token"):
        api_params["pageToken"] = params["page_token"]

    result = _api_call(api_key, "commentThreads", api_params)

    if result.get("ok"):
        data = result["data"]
        comments = []
        for item in data.get("items", []):
            top_comment = item.get("snippet", {}).get("topLevelComment", {})
            comment_snippet = top_comment.get("snippet", {})
            comments.append({
                "id": item.get("id"),
                "comment_id": top_comment.get("id"),
                "author_name": comment_snippet.get("authorDisplayName"),
                "author_channel_id": comment_snippet.get("authorChannelId", {}).get("value"),
                "author_profile_image": comment_snippet.get("authorProfileImageUrl"),
                "text": comment_snippet.get("textDisplay"),
                "text_original": comment_snippet.get("textOriginal"),
                "like_count": comment_snippet.get("likeCount", 0),
                "published_at": comment_snippet.get("publishedAt"),
                "updated_at": comment_snippet.get("updatedAt"),
                "reply_count": item.get("snippet", {}).get("totalReplyCount", 0),
            })

        return {
            "ok": True,
            "data": {
                "comments": comments,
                "video_id": video_id,
                "total_results": data.get("pageInfo", {}).get("totalResults", 0),
                "next_page_token": data.get("nextPageToken"),
            }
        }

    return result


def get_captions(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List available captions/subtitles for a video.

    Note: This only lists caption tracks, not the actual caption content.
    Downloading caption content requires OAuth authentication.

    Params:
        video_id (str): YouTube video ID (required)

    Returns:
        Dict with 'ok', 'data' containing list of available caption tracks
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    video_id = params.get("video_id")
    if not video_id:
        return {"ok": False, "error": "video_id is required"}

    api_params = {
        "part": "snippet",
        "videoId": video_id,
    }

    result = _api_call(api_key, "captions", api_params)

    if result.get("ok"):
        data = result["data"]
        captions = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            captions.append({
                "id": item.get("id"),
                "video_id": snippet.get("videoId"),
                "language": snippet.get("language"),
                "name": snippet.get("name"),
                "audio_track_type": snippet.get("audioTrackType"),
                "is_cc": snippet.get("isCC", False),
                "is_auto_synced": snippet.get("isAutoSynced", False),
                "is_draft": snippet.get("isDraft", False),
                "track_kind": snippet.get("trackKind"),
                "last_updated": snippet.get("lastUpdated"),
            })

        return {
            "ok": True,
            "data": {
                "captions": captions,
                "video_id": video_id,
                "count": len(captions)
            }
        }

    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "search": search,
    "get_video": get_video,
    "list_videos": list_videos,
    "get_channel": get_channel,
    "list_playlists": list_playlists,
    "get_playlist_items": get_playlist_items,
    "list_comments": list_comments,
    "get_captions": get_captions,
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
        logger.info(f"Executing youtube.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
