"""
Zoom Controller for TinyHive

A controller for the Zoom REST API supporting meeting management,
recordings, and user administration.

Method IDs:
  controller.zoom.{profile}.list_meetings
  controller.zoom.{profile}.create_meeting
  controller.zoom.{profile}.get_meeting
  controller.zoom.{profile}.update_meeting
  controller.zoom.{profile}.delete_meeting
  controller.zoom.{profile}.list_recordings
  controller.zoom.{profile}.get_meeting_participants
  controller.zoom.{profile}.list_users

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "token_env": "ZOOM_ACCESS_TOKEN",
    "default_user_id": "me"
}

The token_env specifies the environment variable containing the Zoom OAuth
access token. If not specified, defaults to ZOOM_ACCESS_TOKEN.

Required OAuth Scopes per Action:
  - list_meetings: meeting:read:list_meetings
  - create_meeting: meeting:write:meeting
  - get_meeting: meeting:read:meeting
  - update_meeting: meeting:update:meeting
  - delete_meeting: meeting:delete:meeting
  - list_recordings: cloud_recording:read:list_user_recordings
  - get_meeting_participants: meeting:read:participant
  - list_users: user:read:list_users

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

logger = logging.getLogger("tinyhive.controller.zoom")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Zoom API base URL
ZOOM_API_BASE = "https://api.zoom.us/v2"

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


def _get_access_token(profile: Dict[str, Any]) -> str:
    """Get the Zoom access token from environment variable."""
    env_var = profile.get("token_env", "ZOOM_ACCESS_TOKEN")
    token = os.environ.get(env_var)
    if not token:
        raise ValueError(
            f"Environment variable '{env_var}' not set. "
            "Obtain a Zoom OAuth access token and set it in the environment."
        )
    return token


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Zoom API call."""
    url = f"{ZOOM_API_BASE}{endpoint}"

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
            return {"ok": True, "data": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_body[:500])
            error_code = error_data.get("code", e.code)
        except json.JSONDecodeError:
            error_message = error_body[:500]
            error_code = e.code
        logger.error("Zoom API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}", "error_code": error_code}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Zoom API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Meeting Actions
# =============================================================================

def list_meetings(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List meetings for a user.

    Required OAuth Scope: meeting:read:list_meetings

    Params:
        user_id (str): User ID or 'me' for authenticated user (default: from profile or 'me')
        type (str): Meeting type filter: scheduled, live, upcoming, upcoming_meetings,
                    previous_meetings (default: scheduled)
        page_size (int): Number of results per page (default: 30, max: 300)
        next_page_token (str): Token for pagination (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    user_id = params.get("user_id", profile.get("default_user_id", "me"))
    meeting_type = params.get("type", "scheduled")
    page_size = params.get("page_size", 30)
    next_page_token = params.get("next_page_token")

    query_params = {
        "type": meeting_type,
        "page_size": page_size,
    }
    if next_page_token:
        query_params["next_page_token"] = next_page_token

    result = _api_call(
        token,
        f"/users/{user_id}/meetings",
        params=query_params
    )

    if result.get("ok") and "data" in result:
        data = result["data"]
        return {
            "ok": True,
            "data": {
                "meetings": data.get("meetings", []),
                "page_count": data.get("page_count", 0),
                "page_size": data.get("page_size", 0),
                "total_records": data.get("total_records", 0),
                "next_page_token": data.get("next_page_token"),
            }
        }
    return result


def create_meeting(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new meeting.

    Required OAuth Scope: meeting:write:meeting

    Params:
        user_id (str): User ID or 'me' for authenticated user (default: from profile or 'me')
        topic (str): Meeting topic (required)
        type (int): Meeting type: 1=instant, 2=scheduled, 3=recurring no fixed time,
                    8=recurring fixed time (default: 2)
        start_time (str): Meeting start time in UTC (ISO 8601 format, e.g., 2024-01-15T10:00:00Z)
        duration (int): Meeting duration in minutes (default: 60)
        timezone (str): Timezone for start_time (e.g., America/New_York)
        agenda (str): Meeting agenda/description (optional)
        password (str): Meeting password (optional, auto-generated if not provided)
        settings (dict): Meeting settings (optional)
            - host_video (bool): Start video when host joins
            - participant_video (bool): Start video when participants join
            - join_before_host (bool): Allow joining before host
            - mute_upon_entry (bool): Mute participants upon entry
            - waiting_room (bool): Enable waiting room
            - auto_recording (str): 'local', 'cloud', or 'none'
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    user_id = params.get("user_id", profile.get("default_user_id", "me"))
    topic = params.get("topic")

    if not topic:
        return {"ok": False, "error": "topic is required"}

    meeting_data: Dict[str, Any] = {
        "topic": topic,
        "type": params.get("type", 2),
    }

    if params.get("start_time"):
        meeting_data["start_time"] = params["start_time"]
    if params.get("duration"):
        meeting_data["duration"] = params["duration"]
    if params.get("timezone"):
        meeting_data["timezone"] = params["timezone"]
    if params.get("agenda"):
        meeting_data["agenda"] = params["agenda"]
    if params.get("password"):
        meeting_data["password"] = params["password"]
    if params.get("settings"):
        meeting_data["settings"] = params["settings"]

    result = _api_call(
        token,
        f"/users/{user_id}/meetings",
        method="POST",
        data=meeting_data
    )

    if result.get("ok") and "data" in result:
        data = result["data"]
        return {
            "ok": True,
            "data": {
                "id": data.get("id"),
                "uuid": data.get("uuid"),
                "topic": data.get("topic"),
                "type": data.get("type"),
                "start_time": data.get("start_time"),
                "duration": data.get("duration"),
                "timezone": data.get("timezone"),
                "join_url": data.get("join_url"),
                "start_url": data.get("start_url"),
                "password": data.get("password"),
                "h323_password": data.get("h323_password"),
                "pstn_password": data.get("pstn_password"),
            }
        }
    return result


def get_meeting(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get meeting details.

    Required OAuth Scope: meeting:read:meeting

    Params:
        meeting_id (str|int): Meeting ID (required)
        occurrence_id (str): Occurrence ID for recurring meetings (optional)
        show_previous_occurrences (bool): Include previous occurrences (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    meeting_id = params.get("meeting_id")
    if not meeting_id:
        return {"ok": False, "error": "meeting_id is required"}

    query_params = {}
    if params.get("occurrence_id"):
        query_params["occurrence_id"] = params["occurrence_id"]
    if params.get("show_previous_occurrences"):
        query_params["show_previous_occurrences"] = str(params["show_previous_occurrences"]).lower()

    result = _api_call(
        token,
        f"/meetings/{meeting_id}",
        params=query_params if query_params else None
    )

    if result.get("ok") and "data" in result:
        data = result["data"]
        return {
            "ok": True,
            "data": {
                "id": data.get("id"),
                "uuid": data.get("uuid"),
                "topic": data.get("topic"),
                "type": data.get("type"),
                "status": data.get("status"),
                "start_time": data.get("start_time"),
                "duration": data.get("duration"),
                "timezone": data.get("timezone"),
                "agenda": data.get("agenda"),
                "created_at": data.get("created_at"),
                "join_url": data.get("join_url"),
                "start_url": data.get("start_url"),
                "password": data.get("password"),
                "host_id": data.get("host_id"),
                "host_email": data.get("host_email"),
                "settings": data.get("settings"),
                "occurrences": data.get("occurrences"),
            }
        }
    return result


def update_meeting(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update a meeting.

    Required OAuth Scope: meeting:update:meeting

    Params:
        meeting_id (str|int): Meeting ID (required)
        occurrence_id (str): Occurrence ID for recurring meetings (optional)
        topic (str): Meeting topic (optional)
        type (int): Meeting type (optional)
        start_time (str): Meeting start time in UTC (ISO 8601 format)
        duration (int): Meeting duration in minutes
        timezone (str): Timezone for start_time
        agenda (str): Meeting agenda/description
        password (str): Meeting password
        settings (dict): Meeting settings
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    meeting_id = params.get("meeting_id")
    if not meeting_id:
        return {"ok": False, "error": "meeting_id is required"}

    query_params = {}
    if params.get("occurrence_id"):
        query_params["occurrence_id"] = params["occurrence_id"]

    update_data: Dict[str, Any] = {}

    update_fields = ["topic", "type", "start_time", "duration", "timezone", "agenda", "password", "settings"]
    for field in update_fields:
        if field in params and params[field] is not None:
            update_data[field] = params[field]

    if not update_data:
        return {"ok": False, "error": "No fields to update provided"}

    result = _api_call(
        token,
        f"/meetings/{meeting_id}",
        method="PATCH",
        data=update_data,
        params=query_params if query_params else None
    )

    # Zoom returns 204 No Content on successful update
    if result.get("ok"):
        return {"ok": True, "data": {"meeting_id": meeting_id, "updated": True}}
    return result


def delete_meeting(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a meeting.

    Required OAuth Scope: meeting:delete:meeting

    Params:
        meeting_id (str|int): Meeting ID (required)
        occurrence_id (str): Occurrence ID for recurring meetings (optional)
        schedule_for_reminder (bool): Send cancellation email to registrants (optional)
        cancel_meeting_reminder (bool): Send cancellation email to host (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    meeting_id = params.get("meeting_id")
    if not meeting_id:
        return {"ok": False, "error": "meeting_id is required"}

    query_params = {}
    if params.get("occurrence_id"):
        query_params["occurrence_id"] = params["occurrence_id"]
    if params.get("schedule_for_reminder") is not None:
        query_params["schedule_for_reminder"] = str(params["schedule_for_reminder"]).lower()
    if params.get("cancel_meeting_reminder") is not None:
        query_params["cancel_meeting_reminder"] = str(params["cancel_meeting_reminder"]).lower()

    result = _api_call(
        token,
        f"/meetings/{meeting_id}",
        method="DELETE",
        params=query_params if query_params else None
    )

    # Zoom returns 204 No Content on successful delete
    if result.get("ok"):
        return {"ok": True, "data": {"meeting_id": meeting_id, "deleted": True}}
    return result


# =============================================================================
# Recording Actions
# =============================================================================

def list_recordings(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List cloud recordings for a user.

    Required OAuth Scope: cloud_recording:read:list_user_recordings

    Params:
        user_id (str): User ID or 'me' for authenticated user (default: from profile or 'me')
        from (str): Start date in YYYY-MM-DD format (required)
        to (str): End date in YYYY-MM-DD format (required)
        page_size (int): Number of results per page (default: 30, max: 300)
        next_page_token (str): Token for pagination (optional)
        trash (bool): List recordings from trash (optional)
        trash_type (str): Trash type: meeting_recordings or recording_file (optional)
        mc (str): Query multiple values (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    user_id = params.get("user_id", profile.get("default_user_id", "me"))
    from_date = params.get("from")
    to_date = params.get("to")

    if not from_date:
        return {"ok": False, "error": "'from' date is required (YYYY-MM-DD format)"}
    if not to_date:
        return {"ok": False, "error": "'to' date is required (YYYY-MM-DD format)"}

    query_params: Dict[str, Any] = {
        "from": from_date,
        "to": to_date,
        "page_size": params.get("page_size", 30),
    }

    if params.get("next_page_token"):
        query_params["next_page_token"] = params["next_page_token"]
    if params.get("trash") is not None:
        query_params["trash"] = str(params["trash"]).lower()
    if params.get("trash_type"):
        query_params["trash_type"] = params["trash_type"]
    if params.get("mc"):
        query_params["mc"] = params["mc"]

    result = _api_call(
        token,
        f"/users/{user_id}/recordings",
        params=query_params
    )

    if result.get("ok") and "data" in result:
        data = result["data"]
        return {
            "ok": True,
            "data": {
                "meetings": data.get("meetings", []),
                "from": data.get("from"),
                "to": data.get("to"),
                "page_count": data.get("page_count", 0),
                "page_size": data.get("page_size", 0),
                "total_records": data.get("total_records", 0),
                "next_page_token": data.get("next_page_token"),
            }
        }
    return result


# =============================================================================
# Participant Actions
# =============================================================================

def get_meeting_participants(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get meeting participants.

    Required OAuth Scope: meeting:read:participant

    Note: This endpoint returns participants for past meetings only.

    Params:
        meeting_id (str|int): Meeting ID (required)
        page_size (int): Number of results per page (default: 30, max: 300)
        next_page_token (str): Token for pagination (optional)
        include_fields (str): Include additional fields: registrant_id (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    meeting_id = params.get("meeting_id")
    if not meeting_id:
        return {"ok": False, "error": "meeting_id is required"}

    query_params: Dict[str, Any] = {
        "page_size": params.get("page_size", 30),
    }

    if params.get("next_page_token"):
        query_params["next_page_token"] = params["next_page_token"]
    if params.get("include_fields"):
        query_params["include_fields"] = params["include_fields"]

    result = _api_call(
        token,
        f"/past_meetings/{meeting_id}/participants",
        params=query_params
    )

    if result.get("ok") and "data" in result:
        data = result["data"]
        return {
            "ok": True,
            "data": {
                "participants": data.get("participants", []),
                "page_count": data.get("page_count", 0),
                "page_size": data.get("page_size", 0),
                "total_records": data.get("total_records", 0),
                "next_page_token": data.get("next_page_token"),
            }
        }
    return result


# =============================================================================
# User Actions
# =============================================================================

def list_users(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List users in the account.

    Required OAuth Scope: user:read:list_users

    Params:
        status (str): User status: active, inactive, pending (default: active)
        page_size (int): Number of results per page (default: 30, max: 300)
        role_id (str): Filter by role ID (optional)
        page_number (int): Page number (deprecated, use next_page_token)
        next_page_token (str): Token for pagination (optional)
        include_fields (str): Include additional fields: custom_attributes, host_key (optional)
        license (str): Filter by license type (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    status = params.get("status", "active")
    page_size = params.get("page_size", 30)

    query_params: Dict[str, Any] = {
        "status": status,
        "page_size": page_size,
    }

    if params.get("role_id"):
        query_params["role_id"] = params["role_id"]
    if params.get("page_number"):
        query_params["page_number"] = params["page_number"]
    if params.get("next_page_token"):
        query_params["next_page_token"] = params["next_page_token"]
    if params.get("include_fields"):
        query_params["include_fields"] = params["include_fields"]
    if params.get("license"):
        query_params["license"] = params["license"]

    result = _api_call(
        token,
        "/users",
        params=query_params
    )

    if result.get("ok") and "data" in result:
        data = result["data"]
        return {
            "ok": True,
            "data": {
                "users": data.get("users", []),
                "page_count": data.get("page_count", 0),
                "page_size": data.get("page_size", 0),
                "total_records": data.get("total_records", 0),
                "next_page_token": data.get("next_page_token"),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_meetings": list_meetings,
    "create_meeting": create_meeting,
    "get_meeting": get_meeting,
    "update_meeting": update_meeting,
    "delete_meeting": delete_meeting,
    "list_recordings": list_recordings,
    "get_meeting_participants": get_meeting_participants,
    "list_users": list_users,
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
        logger.info(f"Executing zoom.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
