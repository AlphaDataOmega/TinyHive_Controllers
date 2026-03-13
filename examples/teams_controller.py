"""
Microsoft Teams Controller for TinyHive

A controller for integrating with Microsoft Teams via Microsoft Graph API.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "token_env": "TEAMS_ACCESS_TOKEN",  // Environment variable with access token
    "default_team_id": "...",           // Optional default team ID
    "timezone": "UTC"                   // Optional timezone for meetings
}

Required Microsoft Graph API Permissions:
-----------------------------------------
- send_message: ChannelMessage.Send
- send_chat: Chat.ReadWrite, ChatMessage.Send
- list_teams: Team.ReadBasic.All, TeamMember.Read.All
- list_channels: Channel.ReadBasic.All
- create_channel: Channel.Create
- list_chats: Chat.ReadBasic, Chat.Read
- create_meeting: OnlineMeetings.ReadWrite
- list_members: TeamMember.Read.All

Method IDs:
-----------
  controller.teams.{profile}.send_message
  controller.teams.{profile}.send_chat
  controller.teams.{profile}.list_teams
  controller.teams.{profile}.list_channels
  controller.teams.{profile}.create_channel
  controller.teams.{profile}.list_chats
  controller.teams.{profile}.create_meeting
  controller.teams.{profile}.list_members

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

logger = logging.getLogger("tinyhive.controller.teams")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Microsoft Graph API base URL
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"

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
    """Get the access token from environment variable."""
    token_env = profile.get("token_env", "TEAMS_ACCESS_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(
            f"Environment variable '{token_env}' not set. "
            "Set your Microsoft Graph access token in this environment variable."
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
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated Microsoft Graph API call.

    Args:
        token: Microsoft Graph access token
        endpoint: API endpoint (e.g., '/me/joinedTeams')
        method: HTTP method (GET, POST, PATCH, DELETE)
        data: Request payload
        timeout: Request timeout in seconds

    Returns:
        Response dict with 'ok' field and result/error
    """
    url = f"{GRAPH_API_BASE}{endpoint}"

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
            error_code = error_data.get("error", {}).get("code", str(e.code))
        except json.JSONDecodeError:
            error_message = error_body[:500]
            error_code = str(e.code)
        logger.error("Graph API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}", "error_code": error_code}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Graph API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def send_message(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a message to a Teams channel.

    Params:
        team_id (str): The team ID (required)
        channel_id (str): The channel ID (required)
        content (str): Message content in HTML format (required)
        content_type (str): Content type: 'text' or 'html' (default: 'html')

    Returns:
        ok (bool): Success status
        data (dict): Response including message id, created datetime, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        team_id = params.get("team_id")
        channel_id = params.get("channel_id")
        content = params.get("content")

        if not team_id:
            return {"ok": False, "error": "team_id is required"}
        if not channel_id:
            return {"ok": False, "error": "channel_id is required"}
        if not content:
            return {"ok": False, "error": "content is required"}

        content_type = params.get("content_type", "html")

        payload = {
            "body": {
                "contentType": content_type,
                "content": content
            }
        }

        endpoint = f"/teams/{team_id}/channels/{channel_id}/messages"
        result = _api_call(token, endpoint, method="POST", data=payload)

        if result.get("ok") and "data" in result:
            msg = result["data"]
            return {
                "ok": True,
                "data": {
                    "message_id": msg.get("id"),
                    "team_id": team_id,
                    "channel_id": channel_id,
                    "created_datetime": msg.get("createdDateTime"),
                    "web_url": msg.get("webUrl")
                }
            }
        return result

    except Exception as e:
        logger.exception("send_message failed")
        return {"ok": False, "error": str(e)}


def send_chat(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a message to a 1:1 or group chat.

    Params:
        chat_id (str): The chat ID (required)
        content (str): Message content (required)
        content_type (str): Content type: 'text' or 'html' (default: 'html')

    Returns:
        ok (bool): Success status
        data (dict): Response including message id, created datetime, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        chat_id = params.get("chat_id")
        content = params.get("content")

        if not chat_id:
            return {"ok": False, "error": "chat_id is required"}
        if not content:
            return {"ok": False, "error": "content is required"}

        content_type = params.get("content_type", "html")

        payload = {
            "body": {
                "contentType": content_type,
                "content": content
            }
        }

        endpoint = f"/chats/{chat_id}/messages"
        result = _api_call(token, endpoint, method="POST", data=payload)

        if result.get("ok") and "data" in result:
            msg = result["data"]
            return {
                "ok": True,
                "data": {
                    "message_id": msg.get("id"),
                    "chat_id": chat_id,
                    "created_datetime": msg.get("createdDateTime"),
                    "web_url": msg.get("webUrl")
                }
            }
        return result

    except Exception as e:
        logger.exception("send_chat failed")
        return {"ok": False, "error": str(e)}


def list_teams(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List teams the user has joined.

    Params:
        filter (str): OData filter expression (optional)
        top (int): Number of teams to return (optional, default: 100)

    Returns:
        ok (bool): Success status
        data (dict): Response including list of teams with id, displayName, description
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        endpoint = "/me/joinedTeams"

        # Build query parameters
        query_params = []
        if params.get("filter"):
            query_params.append(f"$filter={params['filter']}")
        if params.get("top"):
            query_params.append(f"$top={params['top']}")

        if query_params:
            endpoint += "?" + "&".join(query_params)

        result = _api_call(token, endpoint)

        if result.get("ok") and "data" in result:
            teams_data = result["data"]
            teams = teams_data.get("value", [])
            return {
                "ok": True,
                "data": {
                    "teams": [
                        {
                            "id": t.get("id"),
                            "display_name": t.get("displayName"),
                            "description": t.get("description"),
                            "visibility": t.get("visibility"),
                            "web_url": t.get("webUrl")
                        }
                        for t in teams
                    ],
                    "count": len(teams)
                }
            }
        return result

    except Exception as e:
        logger.exception("list_teams failed")
        return {"ok": False, "error": str(e)}


def list_channels(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List channels in a team.

    Params:
        team_id (str): The team ID (required, or uses default_team_id from profile)
        filter (str): OData filter expression (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response including list of channels with id, displayName, description
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        team_id = params.get("team_id") or profile.get("default_team_id")
        if not team_id:
            return {"ok": False, "error": "team_id is required"}

        endpoint = f"/teams/{team_id}/channels"

        if params.get("filter"):
            endpoint += f"?$filter={params['filter']}"

        result = _api_call(token, endpoint)

        if result.get("ok") and "data" in result:
            channels_data = result["data"]
            channels = channels_data.get("value", [])
            return {
                "ok": True,
                "data": {
                    "channels": [
                        {
                            "id": ch.get("id"),
                            "display_name": ch.get("displayName"),
                            "description": ch.get("description"),
                            "membership_type": ch.get("membershipType"),
                            "web_url": ch.get("webUrl")
                        }
                        for ch in channels
                    ],
                    "count": len(channels)
                }
            }
        return result

    except Exception as e:
        logger.exception("list_channels failed")
        return {"ok": False, "error": str(e)}


def create_channel(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new channel in a team.

    Params:
        team_id (str): The team ID (required, or uses default_team_id from profile)
        display_name (str): Name of the channel (required)
        description (str): Description of the channel (optional)
        membership_type (str): 'standard', 'private', or 'shared' (default: 'standard')

    Returns:
        ok (bool): Success status
        data (dict): Response including channel id, displayName, webUrl
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        team_id = params.get("team_id") or profile.get("default_team_id")
        display_name = params.get("display_name")

        if not team_id:
            return {"ok": False, "error": "team_id is required"}
        if not display_name:
            return {"ok": False, "error": "display_name is required"}

        payload: Dict[str, Any] = {
            "displayName": display_name,
            "membershipType": params.get("membership_type", "standard")
        }

        if params.get("description"):
            payload["description"] = params["description"]

        endpoint = f"/teams/{team_id}/channels"
        result = _api_call(token, endpoint, method="POST", data=payload)

        if result.get("ok") and "data" in result:
            channel = result["data"]
            return {
                "ok": True,
                "data": {
                    "channel_id": channel.get("id"),
                    "display_name": channel.get("displayName"),
                    "description": channel.get("description"),
                    "membership_type": channel.get("membershipType"),
                    "web_url": channel.get("webUrl")
                }
            }
        return result

    except Exception as e:
        logger.exception("create_channel failed")
        return {"ok": False, "error": str(e)}


def list_chats(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List the user's chats (1:1 and group chats).

    Params:
        top (int): Number of chats to return (optional, default: 50)
        filter (str): OData filter expression (optional)
        expand (str): Properties to expand (optional, e.g., 'members')

    Returns:
        ok (bool): Success status
        data (dict): Response including list of chats with id, topic, chatType
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        endpoint = "/me/chats"

        # Build query parameters
        query_params = []
        if params.get("top"):
            query_params.append(f"$top={params['top']}")
        if params.get("filter"):
            query_params.append(f"$filter={params['filter']}")
        if params.get("expand"):
            query_params.append(f"$expand={params['expand']}")

        if query_params:
            endpoint += "?" + "&".join(query_params)

        result = _api_call(token, endpoint)

        if result.get("ok") and "data" in result:
            chats_data = result["data"]
            chats = chats_data.get("value", [])
            return {
                "ok": True,
                "data": {
                    "chats": [
                        {
                            "id": c.get("id"),
                            "topic": c.get("topic"),
                            "chat_type": c.get("chatType"),
                            "created_datetime": c.get("createdDateTime"),
                            "last_updated_datetime": c.get("lastUpdatedDateTime"),
                            "web_url": c.get("webUrl")
                        }
                        for c in chats
                    ],
                    "count": len(chats)
                }
            }
        return result

    except Exception as e:
        logger.exception("list_chats failed")
        return {"ok": False, "error": str(e)}


def create_meeting(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an online meeting.

    Params:
        subject (str): Subject/title of the meeting (required)
        start_time (str): Start time in ISO 8601 format (required, e.g., '2024-01-15T10:00:00')
        end_time (str): End time in ISO 8601 format (required, e.g., '2024-01-15T11:00:00')
        attendees (list): List of attendee email addresses (optional)
        lobby_bypass (str): Who can bypass lobby: 'everyone', 'organization',
                           'organizationAndFederated', 'organizer' (optional)
        auto_admit (str): Auto-admit users: 'everyone', 'everyoneInCompany',
                         'everyoneInSameAndFederatedCompany', 'organizer' (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response including meeting id, join URL, dial-in info
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        subject = params.get("subject")
        start_time = params.get("start_time")
        end_time = params.get("end_time")

        if not subject:
            return {"ok": False, "error": "subject is required"}
        if not start_time:
            return {"ok": False, "error": "start_time is required"}
        if not end_time:
            return {"ok": False, "error": "end_time is required"}

        timezone = profile.get("timezone", "UTC")

        payload: Dict[str, Any] = {
            "subject": subject,
            "startDateTime": start_time,
            "endDateTime": end_time,
        }

        # Add attendees if provided
        attendees = params.get("attendees", [])
        if attendees:
            payload["participants"] = {
                "attendees": [
                    {
                        "upn": email,
                        "role": "attendee"
                    }
                    for email in attendees
                ]
            }

        # Add lobby settings if provided
        lobby_settings = {}
        if params.get("lobby_bypass"):
            lobby_settings["lobbyBypassSettings"] = {
                "scope": params["lobby_bypass"]
            }
        if params.get("auto_admit"):
            lobby_settings["autoAdmittedUsers"] = params["auto_admit"]

        if lobby_settings:
            payload["lobbyBypassSettings"] = lobby_settings

        endpoint = "/me/onlineMeetings"
        result = _api_call(token, endpoint, method="POST", data=payload)

        if result.get("ok") and "data" in result:
            meeting = result["data"]
            return {
                "ok": True,
                "data": {
                    "meeting_id": meeting.get("id"),
                    "subject": meeting.get("subject"),
                    "start_datetime": meeting.get("startDateTime"),
                    "end_datetime": meeting.get("endDateTime"),
                    "join_url": meeting.get("joinUrl") or meeting.get("joinWebUrl"),
                    "video_teleconference_id": meeting.get("videoTeleconferenceId"),
                    "dial_in": meeting.get("audioConferencing", {})
                }
            }
        return result

    except Exception as e:
        logger.exception("create_meeting failed")
        return {"ok": False, "error": str(e)}


def list_members(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List members of a team.

    Params:
        team_id (str): The team ID (required, or uses default_team_id from profile)
        filter (str): OData filter expression (optional)
        top (int): Number of members to return (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response including list of members with id, displayName, roles
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        team_id = params.get("team_id") or profile.get("default_team_id")
        if not team_id:
            return {"ok": False, "error": "team_id is required"}

        endpoint = f"/teams/{team_id}/members"

        # Build query parameters
        query_params = []
        if params.get("filter"):
            query_params.append(f"$filter={params['filter']}")
        if params.get("top"):
            query_params.append(f"$top={params['top']}")

        if query_params:
            endpoint += "?" + "&".join(query_params)

        result = _api_call(token, endpoint)

        if result.get("ok") and "data" in result:
            members_data = result["data"]
            members = members_data.get("value", [])
            return {
                "ok": True,
                "data": {
                    "members": [
                        {
                            "id": m.get("id"),
                            "user_id": m.get("userId"),
                            "display_name": m.get("displayName"),
                            "email": m.get("email"),
                            "roles": m.get("roles", []),
                            "visible_history_start_datetime": m.get("visibleHistoryStartDateTime")
                        }
                        for m in members
                    ],
                    "count": len(members)
                }
            }
        return result

    except Exception as e:
        logger.exception("list_members failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "send_message": send_message,
    "send_chat": send_chat,
    "list_teams": list_teams,
    "list_channels": list_channels,
    "create_channel": create_channel,
    "list_chats": list_chats,
    "create_meeting": create_meeting,
    "list_members": list_members,
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

    logger.info(f"Executing teams.{profile}.{action}")

    try:
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
