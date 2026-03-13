"""
Spotify Controller for TinyHive

A controller for the Spotify Web API providing access to music catalog,
user profiles, playlists, and recommendations.

Method IDs:
  controller.spotify.{profile}.search
  controller.spotify.{profile}.get_track
  controller.spotify.{profile}.get_album
  controller.spotify.{profile}.get_artist
  controller.spotify.{profile}.get_playlist
  controller.spotify.{profile}.get_user_playlists
  controller.spotify.{profile}.get_current_user
  controller.spotify.{profile}.get_recommendations

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "token_env": "SPOTIFY_ACCESS_TOKEN",
    "default_market": "US"
}

Required Scopes (depending on action):
- user-read-private (get_current_user)
- user-read-email (get_current_user)
- playlist-read-private (get_playlist, get_user_playlists)
- playlist-read-collaborative (get_playlist, get_user_playlists)

Authentication:
--------------
OAuth2 Bearer token obtained from Spotify Authorization flow.
Set the access token in the environment variable specified by token_env.

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
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.spotify")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Spotify API base URL
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

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


def _get_access_token(profile: Dict[str, Any]) -> str:
    """Get OAuth2 access token from environment variable."""
    token_env = profile.get("token_env", "SPOTIFY_ACCESS_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(
            f"Environment variable '{token_env}' not set. "
            "Obtain a token from Spotify OAuth2 authorization flow."
        )
    return token


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    token: str,
    endpoint: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Spotify API call."""
    url = f"{SPOTIFY_API_BASE}{endpoint}"

    # Add query parameters if provided
    if params:
        # Filter out None values
        filtered_params = {k: v for k, v in params.items() if v is not None}
        if filtered_params:
            url += "?" + urlencode(filtered_params)

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
                return {"ok": True, "data": json.loads(response_body)}
            return {"ok": True, "data": {}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("error", {}).get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Spotify API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Spotify API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def search(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for items in the Spotify catalog.

    Params:
        q (str): Search query (required)
        type (str): Comma-separated list of types to search: album, artist, playlist, track, show, episode (required)
        limit (int): Maximum number of results per type (default: 20, max: 50)
        market (str): ISO 3166-1 alpha-2 country code (default: from profile)
        offset (int): Index of first result to return (default: 0)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    q = params.get("q")
    item_type = params.get("type")

    if not q:
        return {"ok": False, "error": "q (search query) is required"}
    if not item_type:
        return {"ok": False, "error": "type is required (e.g., 'track', 'artist', 'album')"}

    query_params = {
        "q": q,
        "type": item_type,
        "limit": params.get("limit", 20),
        "market": params.get("market", profile.get("default_market")),
        "offset": params.get("offset"),
    }

    return _api_call(token, "/search", params=query_params)


def get_track(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get Spotify catalog information for a single track.

    Params:
        track_id (str): Spotify track ID (required)
        market (str): ISO 3166-1 alpha-2 country code (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    track_id = params.get("track_id")
    if not track_id:
        return {"ok": False, "error": "track_id is required"}

    query_params = {
        "market": params.get("market", profile.get("default_market")),
    }

    return _api_call(token, f"/tracks/{quote(track_id)}", params=query_params)


def get_album(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get Spotify catalog information for a single album.

    Params:
        album_id (str): Spotify album ID (required)
        market (str): ISO 3166-1 alpha-2 country code (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    album_id = params.get("album_id")
    if not album_id:
        return {"ok": False, "error": "album_id is required"}

    query_params = {
        "market": params.get("market", profile.get("default_market")),
    }

    return _api_call(token, f"/albums/{quote(album_id)}", params=query_params)


def get_artist(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get Spotify catalog information for a single artist.

    Params:
        artist_id (str): Spotify artist ID (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    artist_id = params.get("artist_id")
    if not artist_id:
        return {"ok": False, "error": "artist_id is required"}

    return _api_call(token, f"/artists/{quote(artist_id)}")


def get_playlist(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a playlist owned by a Spotify user.

    Params:
        playlist_id (str): Spotify playlist ID (required)
        market (str): ISO 3166-1 alpha-2 country code (optional)
        fields (str): Filters for the query (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    playlist_id = params.get("playlist_id")
    if not playlist_id:
        return {"ok": False, "error": "playlist_id is required"}

    query_params = {
        "market": params.get("market", profile.get("default_market")),
        "fields": params.get("fields"),
    }

    return _api_call(token, f"/playlists/{quote(playlist_id)}", params=query_params)


def get_user_playlists(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a list of playlists owned or followed by a Spotify user.

    Params:
        user_id (str): Spotify user ID (required)
        limit (int): Maximum number of playlists to return (default: 20, max: 50)
        offset (int): Index of first playlist to return (default: 0)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    user_id = params.get("user_id")
    if not user_id:
        return {"ok": False, "error": "user_id is required"}

    query_params = {
        "limit": params.get("limit", 20),
        "offset": params.get("offset"),
    }

    return _api_call(token, f"/users/{quote(user_id)}/playlists", params=query_params)


def get_current_user(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get detailed profile information about the current user.

    Requires scope: user-read-private, user-read-email

    Params:
        None required
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    return _api_call(token, "/me")


def get_recommendations(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get track recommendations based on seed artists, tracks, and genres.

    Params:
        seed_artists (str): Comma-separated list of Spotify artist IDs (optional)
        seed_tracks (str): Comma-separated list of Spotify track IDs (optional)
        seed_genres (str): Comma-separated list of genres (optional)
        limit (int): Number of tracks to return (default: 20, max: 100)
        market (str): ISO 3166-1 alpha-2 country code (optional)

    Note: At least one of seed_artists, seed_tracks, or seed_genres is required.
          Up to 5 seed values total across all seed types.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    seed_artists = params.get("seed_artists")
    seed_tracks = params.get("seed_tracks")
    seed_genres = params.get("seed_genres")

    if not seed_artists and not seed_tracks and not seed_genres:
        return {
            "ok": False,
            "error": "At least one of seed_artists, seed_tracks, or seed_genres is required"
        }

    query_params = {
        "seed_artists": seed_artists,
        "seed_tracks": seed_tracks,
        "seed_genres": seed_genres,
        "limit": params.get("limit", 20),
        "market": params.get("market", profile.get("default_market")),
    }

    return _api_call(token, "/recommendations", params=query_params)


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "search": search,
    "get_track": get_track,
    "get_album": get_album,
    "get_artist": get_artist,
    "get_playlist": get_playlist,
    "get_user_playlists": get_user_playlists,
    "get_current_user": get_current_user,
    "get_recommendations": get_recommendations,
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
        logger.info(f"Executing spotify.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
