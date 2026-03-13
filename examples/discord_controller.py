"""
Discord Controller for TinyHive

A Discord bot controller using the Discord REST API v10.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "token_env": "DISCORD_BOT_TOKEN",  // Environment variable with bot token
    "default_guild_id": "123456789"    // Optional default guild ID
}

Required Bot Permissions:
------------------------
- send_message: Send Messages, Embed Links
- send_dm: (No guild permission needed)
- create_thread: Create Public Threads, Create Private Threads
- add_reaction: Add Reactions
- list_channels: View Channels
- list_members: Server Members Intent (privileged)
- add_role/remove_role: Manage Roles
- create_webhook: Manage Webhooks

Method IDs:
-----------
  controller.discord.{profile}.send_message
  controller.discord.{profile}.send_dm
  controller.discord.{profile}.create_thread
  controller.discord.{profile}.add_reaction
  controller.discord.{profile}.list_channels
  controller.discord.{profile}.list_members
  controller.discord.{profile}.add_role
  controller.discord.{profile}.remove_role
  controller.discord.{profile}.create_webhook

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
from urllib.parse import quote

logger = logging.getLogger("tinyhive.controller.discord")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Discord API base URL
DISCORD_API_BASE = "https://discord.com/api/v10"

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
    """Get the bot token from environment variable."""
    token_env = profile.get("token_env", "DISCORD_BOT_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(f"Environment variable '{token_env}' not set")
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
    """Make an authenticated Discord API call."""
    url = f"{DISCORD_API_BASE}{endpoint}"

    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "TinyHive-Discord-Controller/1.0"
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
            error_message = error_data.get("message", error_body[:500])
            error_code = error_data.get("code", e.code)
        except json.JSONDecodeError:
            error_message = error_body[:500]
            error_code = e.code
        logger.error("Discord API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}", "error_code": error_code}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Discord API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def send_message(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a message to a channel.

    Params:
        channel_id (str): The channel ID to send to (required)
        content (str): Message text content (optional if embeds provided)
        embeds (list): List of embed objects (optional)
        tts (bool): Text-to-speech (default: false)
        allowed_mentions (dict): Allowed mentions object (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    channel_id = params.get("channel_id")
    if not channel_id:
        return {"ok": False, "error": "channel_id is required"}

    content = params.get("content")
    embeds = params.get("embeds")

    if not content and not embeds:
        return {"ok": False, "error": "Either content or embeds is required"}

    payload: Dict[str, Any] = {}
    if content:
        payload["content"] = content
    if embeds:
        payload["embeds"] = embeds
    if params.get("tts"):
        payload["tts"] = True
    if params.get("allowed_mentions"):
        payload["allowed_mentions"] = params["allowed_mentions"]

    result = _api_call(token, f"/channels/{channel_id}/messages", method="POST", data=payload)

    if result.get("ok") and "data" in result:
        msg = result["data"]
        return {
            "ok": True,
            "data": {
                "message_id": msg.get("id"),
                "channel_id": msg.get("channel_id"),
                "content": msg.get("content"),
                "timestamp": msg.get("timestamp"),
                "author": msg.get("author", {}).get("username")
            }
        }
    return result


def send_dm(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a direct message to a user.

    Params:
        user_id (str): The user ID to send DM to (required)
        content (str): Message text content (required)
        embeds (list): List of embed objects (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    user_id = params.get("user_id")
    if not user_id:
        return {"ok": False, "error": "user_id is required"}

    content = params.get("content")
    embeds = params.get("embeds")

    if not content and not embeds:
        return {"ok": False, "error": "Either content or embeds is required"}

    # First, create a DM channel with the user
    dm_result = _api_call(token, "/users/@me/channels", method="POST", data={"recipient_id": user_id})

    if not dm_result.get("ok"):
        return {"ok": False, "error": f"Failed to create DM channel: {dm_result.get('error')}"}

    channel_id = dm_result["data"].get("id")
    if not channel_id:
        return {"ok": False, "error": "Failed to get DM channel ID"}

    # Send the message to the DM channel
    payload: Dict[str, Any] = {}
    if content:
        payload["content"] = content
    if embeds:
        payload["embeds"] = embeds

    result = _api_call(token, f"/channels/{channel_id}/messages", method="POST", data=payload)

    if result.get("ok") and "data" in result:
        msg = result["data"]
        return {
            "ok": True,
            "data": {
                "message_id": msg.get("id"),
                "channel_id": channel_id,
                "content": msg.get("content"),
                "timestamp": msg.get("timestamp"),
                "recipient_id": user_id
            }
        }
    return result


def create_thread(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a thread in a channel.

    Params:
        channel_id (str): The channel ID to create thread in (required)
        name (str): Name of the thread (required, 1-100 characters)
        message_id (str): Message ID to start thread from (optional)
        auto_archive_duration (int): Minutes until auto-archive: 60, 1440, 4320, 10080 (optional)
        type (int): Thread type: 10=announcement, 11=public, 12=private (default: 11)
        invitable (bool): Whether non-moderators can add users (private threads only)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    channel_id = params.get("channel_id")
    name = params.get("name")

    if not channel_id:
        return {"ok": False, "error": "channel_id is required"}
    if not name:
        return {"ok": False, "error": "name is required"}

    message_id = params.get("message_id")

    payload: Dict[str, Any] = {"name": name}

    if params.get("auto_archive_duration"):
        payload["auto_archive_duration"] = params["auto_archive_duration"]
    if params.get("invitable") is not None:
        payload["invitable"] = params["invitable"]

    if message_id:
        # Create thread from existing message
        endpoint = f"/channels/{channel_id}/messages/{message_id}/threads"
    else:
        # Create thread without a message (need to specify type)
        endpoint = f"/channels/{channel_id}/threads"
        payload["type"] = params.get("type", 11)  # Default to public thread

    result = _api_call(token, endpoint, method="POST", data=payload)

    if result.get("ok") and "data" in result:
        thread = result["data"]
        return {
            "ok": True,
            "data": {
                "thread_id": thread.get("id"),
                "name": thread.get("name"),
                "parent_id": thread.get("parent_id"),
                "owner_id": thread.get("owner_id"),
                "type": thread.get("type")
            }
        }
    return result


def add_reaction(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a reaction to a message.

    Params:
        channel_id (str): The channel ID (required)
        message_id (str): The message ID (required)
        emoji (str): The emoji to react with (required)
            - Unicode emoji: "👍"
            - Custom emoji: "name:id" format, e.g., "myemoji:123456789"
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    channel_id = params.get("channel_id")
    message_id = params.get("message_id")
    emoji = params.get("emoji")

    if not channel_id:
        return {"ok": False, "error": "channel_id is required"}
    if not message_id:
        return {"ok": False, "error": "message_id is required"}
    if not emoji:
        return {"ok": False, "error": "emoji is required"}

    # URL-encode the emoji
    encoded_emoji = quote(emoji, safe="")

    endpoint = f"/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
    result = _api_call(token, endpoint, method="PUT")

    # Discord returns 204 No Content on success
    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "channel_id": channel_id,
                "message_id": message_id,
                "emoji": emoji
            }
        }
    return result


def list_channels(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List channels in a guild.

    Params:
        guild_id (str): The guild ID (required, or uses default_guild_id from profile)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    guild_id = params.get("guild_id") or profile.get("default_guild_id")
    if not guild_id:
        return {"ok": False, "error": "guild_id is required"}

    result = _api_call(token, f"/guilds/{guild_id}/channels")

    if result.get("ok") and "data" in result:
        channels = result["data"]
        return {
            "ok": True,
            "data": {
                "channels": [
                    {
                        "id": ch.get("id"),
                        "name": ch.get("name"),
                        "type": ch.get("type"),
                        "position": ch.get("position"),
                        "parent_id": ch.get("parent_id"),
                        "topic": ch.get("topic")
                    }
                    for ch in channels
                ],
                "count": len(channels)
            }
        }
    return result


def list_members(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List members in a guild.

    Params:
        guild_id (str): The guild ID (required, or uses default_guild_id from profile)
        limit (int): Max number of members to return, 1-1000 (default: 100)
        after (str): Get members after this user ID (for pagination)

    Note: Requires Server Members Intent (privileged) to be enabled.
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    guild_id = params.get("guild_id") or profile.get("default_guild_id")
    if not guild_id:
        return {"ok": False, "error": "guild_id is required"}

    limit = min(params.get("limit", 100), 1000)

    endpoint = f"/guilds/{guild_id}/members?limit={limit}"
    if params.get("after"):
        endpoint += f"&after={params['after']}"

    result = _api_call(token, endpoint)

    if result.get("ok") and "data" in result:
        members = result["data"]
        return {
            "ok": True,
            "data": {
                "members": [
                    {
                        "user_id": m.get("user", {}).get("id"),
                        "username": m.get("user", {}).get("username"),
                        "discriminator": m.get("user", {}).get("discriminator"),
                        "nick": m.get("nick"),
                        "roles": m.get("roles", []),
                        "joined_at": m.get("joined_at"),
                        "avatar": m.get("user", {}).get("avatar")
                    }
                    for m in members
                ],
                "count": len(members)
            }
        }
    return result


def add_role(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a role to a guild member.

    Params:
        guild_id (str): The guild ID (required, or uses default_guild_id from profile)
        user_id (str): The user ID (required)
        role_id (str): The role ID to add (required)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    guild_id = params.get("guild_id") or profile.get("default_guild_id")
    user_id = params.get("user_id")
    role_id = params.get("role_id")

    if not guild_id:
        return {"ok": False, "error": "guild_id is required"}
    if not user_id:
        return {"ok": False, "error": "user_id is required"}
    if not role_id:
        return {"ok": False, "error": "role_id is required"}

    endpoint = f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}"
    result = _api_call(token, endpoint, method="PUT")

    # Discord returns 204 No Content on success
    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "guild_id": guild_id,
                "user_id": user_id,
                "role_id": role_id,
                "action": "added"
            }
        }
    return result


def remove_role(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove a role from a guild member.

    Params:
        guild_id (str): The guild ID (required, or uses default_guild_id from profile)
        user_id (str): The user ID (required)
        role_id (str): The role ID to remove (required)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    guild_id = params.get("guild_id") or profile.get("default_guild_id")
    user_id = params.get("user_id")
    role_id = params.get("role_id")

    if not guild_id:
        return {"ok": False, "error": "guild_id is required"}
    if not user_id:
        return {"ok": False, "error": "user_id is required"}
    if not role_id:
        return {"ok": False, "error": "role_id is required"}

    endpoint = f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}"
    result = _api_call(token, endpoint, method="DELETE")

    # Discord returns 204 No Content on success
    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "guild_id": guild_id,
                "user_id": user_id,
                "role_id": role_id,
                "action": "removed"
            }
        }
    return result


def create_webhook(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a webhook in a channel.

    Params:
        channel_id (str): The channel ID (required)
        name (str): Name of the webhook (required, 1-80 characters)
        avatar (str): Avatar image data URI (optional, base64 encoded)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    channel_id = params.get("channel_id")
    name = params.get("name")

    if not channel_id:
        return {"ok": False, "error": "channel_id is required"}
    if not name:
        return {"ok": False, "error": "name is required"}

    payload: Dict[str, Any] = {"name": name}
    if params.get("avatar"):
        payload["avatar"] = params["avatar"]

    result = _api_call(token, f"/channels/{channel_id}/webhooks", method="POST", data=payload)

    if result.get("ok") and "data" in result:
        webhook = result["data"]
        return {
            "ok": True,
            "data": {
                "webhook_id": webhook.get("id"),
                "name": webhook.get("name"),
                "channel_id": webhook.get("channel_id"),
                "guild_id": webhook.get("guild_id"),
                "token": webhook.get("token"),
                "url": webhook.get("url") or f"https://discord.com/api/webhooks/{webhook.get('id')}/{webhook.get('token')}"
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "send_message": send_message,
    "send_dm": send_dm,
    "create_thread": create_thread,
    "add_reaction": add_reaction,
    "list_channels": list_channels,
    "list_members": list_members,
    "add_role": add_role,
    "remove_role": remove_role,
    "create_webhook": create_webhook,
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

    logger.info(f"Executing discord.{profile}.{action}")

    try:
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
