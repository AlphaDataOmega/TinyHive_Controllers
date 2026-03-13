"""Example: Telegram controller — Bot integration.

This is an example of how to build a Telegram controller.
Copy to controllers/controller_telegram/ and customize.

Method IDs:
  controller.telegram.{profile}.send_message
  controller.telegram.{profile}.send_photo
  controller.telegram.{profile}.get_updates
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List
from urllib.request import Request, urlopen
from urllib.error import HTTPError

log = logging.getLogger("tinyhive.controller.telegram")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'")
    return json.loads(path.read_text())


def _get_bot_token(profile: Dict[str, Any]) -> str:
    """Get bot token from environment variable."""
    env_var = profile.get("token_env", "TELEGRAM_BOT_TOKEN")
    token = os.environ.get(env_var, "")
    if not token:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return token


def _api_call(token: str, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Make a Telegram Bot API call."""
    url = f"{TELEGRAM_API_BASE}{token}/{method}"
    data = json.dumps(params).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    try:
        req = Request(url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {body[:500]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def send_message(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Send a text message to a chat.

    Params:
        - chat_id: Target chat ID (required)
        - text: Message text (required)
        - parse_mode: "HTML" or "Markdown" (optional)
    """
    profile = load_profile(profile_name)
    token = _get_bot_token(profile)

    chat_id = params.get("chat_id", profile.get("default_chat_id"))
    text = params.get("text", "")

    if not chat_id:
        return {"ok": False, "error": "chat_id required"}
    if not text:
        return {"ok": False, "error": "text required"}

    api_params = {
        "chat_id": chat_id,
        "text": text,
    }
    if params.get("parse_mode"):
        api_params["parse_mode"] = params["parse_mode"]

    return _api_call(token, "sendMessage", api_params)


def send_photo(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Send a photo to a chat.

    Params:
        - chat_id: Target chat ID (required)
        - photo: Photo URL or file_id (required)
        - caption: Optional caption
    """
    profile = load_profile(profile_name)
    token = _get_bot_token(profile)

    chat_id = params.get("chat_id", profile.get("default_chat_id"))
    photo = params.get("photo", "")

    if not chat_id:
        return {"ok": False, "error": "chat_id required"}
    if not photo:
        return {"ok": False, "error": "photo required"}

    api_params = {
        "chat_id": chat_id,
        "photo": photo,
    }
    if params.get("caption"):
        api_params["caption"] = params["caption"]

    return _api_call(token, "sendPhoto", api_params)


def get_updates(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get recent messages (updates) for the bot.

    Params:
        - offset: Update offset for pagination
        - limit: Max updates to return (default: 10)
    """
    profile = load_profile(profile_name)
    token = _get_bot_token(profile)

    api_params = {
        "limit": params.get("limit", 10),
    }
    if params.get("offset"):
        api_params["offset"] = params["offset"]

    return _api_call(token, "getUpdates", api_params)


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

ACTIONS = {
    "send_message": send_message,
    "send_photo": send_photo,
    "get_updates": get_updates,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """Dispatch an action by name with a profile."""
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action '{action}'"}
    return ACTIONS[action](profile, params)
