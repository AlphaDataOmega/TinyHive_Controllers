"""
Slack Controller for TinyHive

A controller for integrating with Slack Web API.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Slack profile:
{
    "token_env": "SLACK_BOT_TOKEN",
    "default_channel": "#general"
}

Required Bot Token Scopes:
-------------------------
- chat:write          - For send_message, send_dm
- files:write         - For upload_file
- channels:read       - For list_channels
- reactions:write     - For add_reaction
- channels:manage     - For create_channel, set_topic
- users:read          - For list_users
- im:write            - For send_dm (opening DM channels)

Dependencies:
------------
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

logger = logging.getLogger("tinyhive.controller.slack")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Slack API base URL
SLACK_API_BASE = "https://slack.com/api"

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
    """Get the Slack bot token from environment variable."""
    token_env = profile.get("token_env", "SLACK_BOT_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(
            f"Environment variable '{token_env}' not set. "
            "Set your Slack bot token in this environment variable."
        )
    return token


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    token: str,
    method: str,
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    content_type: str = "application/json"
) -> Dict[str, Any]:
    """
    Make an authenticated Slack API call.

    Args:
        token: Slack bot token
        method: Slack API method (e.g., 'chat.postMessage')
        data: Request payload
        timeout: Request timeout in seconds
        content_type: Content type header

    Returns:
        Response dict with 'ok' field and result/error
    """
    url = f"{SLACK_API_BASE}/{method}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
    }

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            result = json.loads(response_body)

            # Slack API returns ok: true/false in the response body
            if result.get("ok"):
                return {"ok": True, "data": result}
            else:
                error = result.get("error", "Unknown error")
                logger.error("Slack API error: %s", error)
                return {"ok": False, "error": error}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error("Slack HTTP error %d: %s", e.code, error_body[:500])
        return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Slack API call")
        return {"ok": False, "error": str(e)}


def _api_call_multipart(
    token: str,
    method: str,
    fields: Dict[str, Any],
    file_content: bytes,
    filename: str,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make a multipart/form-data Slack API call for file uploads.

    Args:
        token: Slack bot token
        method: Slack API method
        fields: Form fields
        file_content: File content as bytes
        filename: Name of the file
        timeout: Request timeout in seconds

    Returns:
        Response dict with 'ok' field and result/error
    """
    url = f"{SLACK_API_BASE}/{method}"

    # Build multipart form data
    boundary = "----TinyHiveSlackBoundary"
    body_parts = []

    # Add form fields
    for key, value in fields.items():
        if value is not None:
            body_parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                f"{value}\r\n"
            )

    # Add file
    body_parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    )

    # Combine parts
    body_prefix = "".join(body_parts).encode("utf-8")
    body_suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = body_prefix + file_content + body_suffix

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }

    try:
        req = Request(url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            result = json.loads(response_body)

            if result.get("ok"):
                return {"ok": True, "data": result}
            else:
                error = result.get("error", "Unknown error")
                logger.error("Slack API error: %s", error)
                return {"ok": False, "error": error}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error("Slack HTTP error %d: %s", e.code, error_body[:500])
        return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Slack API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def send_message(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post a message to a Slack channel.

    Params:
        channel (str): Channel ID or name (e.g., '#general' or 'C1234567890') (required)
        text (str): Message text (required, or provide blocks)
        blocks (list): Block Kit blocks for rich formatting (optional)
        thread_ts (str): Thread timestamp to reply to (optional)
        mrkdwn (bool): Enable markdown formatting (default: true)

    Returns:
        ok (bool): Success status
        data (dict): Response including channel, ts (timestamp), message
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        channel = params.get("channel")
        text = params.get("text")
        blocks = params.get("blocks")

        if not channel:
            return {"ok": False, "error": "channel is required"}
        if not text and not blocks:
            return {"ok": False, "error": "text or blocks is required"}

        payload: Dict[str, Any] = {"channel": channel}

        if text:
            payload["text"] = text
        if blocks:
            payload["blocks"] = blocks
        if params.get("thread_ts"):
            payload["thread_ts"] = params["thread_ts"]
        if "mrkdwn" in params:
            payload["mrkdwn"] = params["mrkdwn"]

        return _api_call(token, "chat.postMessage", payload)

    except Exception as e:
        logger.exception("send_message failed")
        return {"ok": False, "error": str(e)}


def send_dm(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a direct message to a user.

    Params:
        user_id (str): User ID to send DM to (e.g., 'U1234567890') (required)
        text (str): Message text (required)
        blocks (list): Block Kit blocks for rich formatting (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response including channel (DM channel ID), ts, message
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        user_id = params.get("user_id")
        text = params.get("text")
        blocks = params.get("blocks")

        if not user_id:
            return {"ok": False, "error": "user_id is required"}
        if not text and not blocks:
            return {"ok": False, "error": "text or blocks is required"}

        # First, open a DM channel with the user
        open_result = _api_call(token, "conversations.open", {"users": user_id})
        if not open_result.get("ok"):
            return open_result

        channel_id = open_result["data"]["channel"]["id"]

        # Now send the message to the DM channel
        payload: Dict[str, Any] = {"channel": channel_id}

        if text:
            payload["text"] = text
        if blocks:
            payload["blocks"] = blocks

        return _api_call(token, "chat.postMessage", payload)

    except Exception as e:
        logger.exception("send_dm failed")
        return {"ok": False, "error": str(e)}


def upload_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upload a file to Slack channel(s).

    Params:
        channels (str): Comma-separated channel IDs or names (required)
        file_content (str): File content as string (required)
        filename (str): Name of the file (required)
        title (str): Title of the file (optional)
        initial_comment (str): Message to post with the file (optional)
        filetype (str): File type identifier (optional, auto-detected)

    Returns:
        ok (bool): Success status
        data (dict): Response including file object with id, name, url, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        channels = params.get("channels")
        file_content = params.get("file_content")
        filename = params.get("filename")

        if not channels:
            return {"ok": False, "error": "channels is required"}
        if not file_content:
            return {"ok": False, "error": "file_content is required"}
        if not filename:
            return {"ok": False, "error": "filename is required"}

        # Convert string content to bytes
        if isinstance(file_content, str):
            file_bytes = file_content.encode("utf-8")
        else:
            file_bytes = file_content

        fields = {
            "channels": channels,
            "filename": filename,
        }

        if params.get("title"):
            fields["title"] = params["title"]
        if params.get("initial_comment"):
            fields["initial_comment"] = params["initial_comment"]
        if params.get("filetype"):
            fields["filetype"] = params["filetype"]

        return _api_call_multipart(token, "files.upload", fields, file_bytes, filename)

    except Exception as e:
        logger.exception("upload_file failed")
        return {"ok": False, "error": str(e)}


def list_channels(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List available Slack channels.

    Params:
        types (str): Comma-separated channel types: public_channel, private_channel,
                     mpim, im (default: 'public_channel')
        limit (int): Maximum channels to return (default: 100, max: 1000)
        exclude_archived (bool): Exclude archived channels (default: true)
        cursor (str): Pagination cursor for next page (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response including channels list and response_metadata for pagination
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        payload: Dict[str, Any] = {}

        types = params.get("types", "public_channel")
        payload["types"] = types

        limit = params.get("limit", 100)
        payload["limit"] = min(limit, 1000)

        if params.get("exclude_archived", True):
            payload["exclude_archived"] = True

        if params.get("cursor"):
            payload["cursor"] = params["cursor"]

        return _api_call(token, "conversations.list", payload)

    except Exception as e:
        logger.exception("list_channels failed")
        return {"ok": False, "error": str(e)}


def add_reaction(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add an emoji reaction to a message.

    Params:
        channel (str): Channel ID containing the message (required)
        timestamp (str): Message timestamp (ts) to react to (required)
        emoji (str): Emoji name without colons (e.g., 'thumbsup') (required)

    Returns:
        ok (bool): Success status
        data (dict): Response confirming reaction was added
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        channel = params.get("channel")
        timestamp = params.get("timestamp")
        emoji = params.get("emoji")

        if not channel:
            return {"ok": False, "error": "channel is required"}
        if not timestamp:
            return {"ok": False, "error": "timestamp is required"}
        if not emoji:
            return {"ok": False, "error": "emoji is required"}

        # Remove colons if provided
        emoji = emoji.strip(":")

        payload = {
            "channel": channel,
            "timestamp": timestamp,
            "name": emoji,
        }

        return _api_call(token, "reactions.add", payload)

    except Exception as e:
        logger.exception("add_reaction failed")
        return {"ok": False, "error": str(e)}


def create_channel(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new Slack channel.

    Params:
        name (str): Channel name (required, will be lowercased, no spaces)
        is_private (bool): Create as private channel (default: false)

    Returns:
        ok (bool): Success status
        data (dict): Response including channel object with id, name, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        name = params.get("name")
        is_private = params.get("is_private", False)

        if not name:
            return {"ok": False, "error": "name is required"}

        payload = {
            "name": name,
            "is_private": is_private,
        }

        return _api_call(token, "conversations.create", payload)

    except Exception as e:
        logger.exception("create_channel failed")
        return {"ok": False, "error": str(e)}


def set_topic(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Set the topic of a Slack channel.

    Params:
        channel (str): Channel ID (required)
        topic (str): New topic text (required, max 250 characters)

    Returns:
        ok (bool): Success status
        data (dict): Response including updated topic
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        channel = params.get("channel")
        topic = params.get("topic")

        if not channel:
            return {"ok": False, "error": "channel is required"}
        if topic is None:
            return {"ok": False, "error": "topic is required"}

        # Truncate to max length
        if len(topic) > 250:
            topic = topic[:250]

        payload = {
            "channel": channel,
            "topic": topic,
        }

        return _api_call(token, "conversations.setTopic", payload)

    except Exception as e:
        logger.exception("set_topic failed")
        return {"ok": False, "error": str(e)}


def list_users(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List users in the Slack workspace.

    Params:
        limit (int): Maximum users to return per page (default: 100, max: 1000)
        cursor (str): Pagination cursor for next page (optional)
        include_locale (bool): Include user locale info (default: false)

    Returns:
        ok (bool): Success status
        data (dict): Response including members list and response_metadata for pagination
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        payload: Dict[str, Any] = {}

        limit = params.get("limit", 100)
        payload["limit"] = min(limit, 1000)

        if params.get("cursor"):
            payload["cursor"] = params["cursor"]

        if params.get("include_locale"):
            payload["include_locale"] = True

        return _api_call(token, "users.list", payload)

    except Exception as e:
        logger.exception("list_users failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "send_message": send_message,
    "send_dm": send_dm,
    "upload_file": upload_file,
    "list_channels": list_channels,
    "add_reaction": add_reaction,
    "create_channel": create_channel,
    "set_topic": set_topic,
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

    logger.info(f"Executing slack.{profile}.{action}")
    return ACTIONS[action](profile, params)
