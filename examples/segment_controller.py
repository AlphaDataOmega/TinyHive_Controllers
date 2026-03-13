"""
Segment Controller for TinyHive

A controller for Segment Analytics HTTP Tracking API.
Supports user identification, event tracking, page/screen views,
group associations, aliasing, batch operations, and user deletion.

Method IDs:
  controller.segment.{profile}.identify
  controller.segment.{profile}.track
  controller.segment.{profile}.page
  controller.segment.{profile}.screen
  controller.segment.{profile}.group
  controller.segment.{profile}.alias
  controller.segment.{profile}.batch
  controller.segment.{profile}.delete

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Basic profile:
{
    "write_key_env": "SEGMENT_WRITE_KEY"
}

With custom settings:
{
    "write_key_env": "MY_SEGMENT_KEY",
    "timeout": 30
}

For Privacy API (delete action):
{
    "write_key_env": "SEGMENT_WRITE_KEY",
    "workspace_slug": "my-workspace",
    "access_token_env": "SEGMENT_ACCESS_TOKEN"
}

Required Permissions:
--------------------
- Track/Identify: Write Key with source access
- Delete: Access Token with Privacy API access

Dependencies:
------------
None (standard library only)
"""

import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger("tinyhive.controller.segment")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Segment API endpoints
SEGMENT_API_BASE = "https://api.segment.io/v1"
SEGMENT_PRIVACY_API = "https://platform.segmentapis.com"

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


def _get_write_key(profile: Dict[str, Any]) -> str:
    """Get write key from environment variable specified in profile."""
    env_var = profile.get("write_key_env", "SEGMENT_WRITE_KEY")
    write_key = os.environ.get(env_var)
    if not write_key:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return write_key


def _get_access_token(profile: Dict[str, Any]) -> str:
    """Get access token for Privacy API from environment variable."""
    env_var = profile.get("access_token_env", "SEGMENT_ACCESS_TOKEN")
    token = os.environ.get(env_var)
    if not token:
        raise ValueError(f"Environment variable '{env_var}' not set (required for Privacy API)")
    return token


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    write_key: str,
    endpoint: str,
    payload: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated Segment API call.

    Uses Basic Auth with write_key as username and empty password.
    """
    url = f"{SEGMENT_API_BASE}/{endpoint}"

    # Basic auth: write_key as username, empty password
    auth_string = f"{write_key}:"
    auth_bytes = base64.b64encode(auth_string.encode("utf-8")).decode("ascii")

    headers = {
        "Authorization": f"Basic {auth_bytes}",
        "Content-Type": "application/json",
    }

    data = json.dumps(payload).encode("utf-8")

    try:
        req = Request(url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {"success": True}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Segment API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Segment API call")
        return {"ok": False, "error": str(e)}


def _privacy_api_call(
    access_token: str,
    workspace_slug: str,
    endpoint: str,
    payload: Dict[str, Any],
    method: str = "POST",
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated Segment Privacy API call.

    Uses Bearer token authentication.
    """
    url = f"{SEGMENT_PRIVACY_API}/v1beta/workspaces/{workspace_slug}/{endpoint}"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    data = json.dumps(payload).encode("utf-8") if payload else None

    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {"success": True}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Segment Privacy API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Segment Privacy API call")
        return {"ok": False, "error": str(e)}


def _generate_message_id() -> str:
    """Generate a unique message ID."""
    return str(uuid.uuid4())


def _get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# Actions
# =============================================================================

def identify(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Identify a user with traits.

    Links user actions to a recognizable user ID and records traits about them.

    Params:
        user_id (str): Unique identifier for the user (required unless anonymous_id provided)
        anonymous_id (str): Anonymous identifier (required if user_id not provided)
        traits (dict): Free-form dictionary of user traits (optional)
        context (dict): Context about the event (optional)
        timestamp (str): ISO timestamp when the identify occurred (optional)
        integrations (dict): Dictionary to enable/disable integrations (optional)

    Returns:
        {"ok": True, "result": {"success": True}}
    """
    try:
        profile = load_profile(profile_name)
        write_key = _get_write_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        user_id = params.get("user_id")
        anonymous_id = params.get("anonymous_id")

        if not user_id and not anonymous_id:
            return {"ok": False, "error": "Either user_id or anonymous_id is required"}

        payload: Dict[str, Any] = {
            "messageId": _generate_message_id(),
            "timestamp": params.get("timestamp", _get_timestamp()),
        }

        if user_id:
            payload["userId"] = user_id
        if anonymous_id:
            payload["anonymousId"] = anonymous_id
        if params.get("traits"):
            payload["traits"] = params["traits"]
        if params.get("context"):
            payload["context"] = params["context"]
        if params.get("integrations"):
            payload["integrations"] = params["integrations"]

        return _api_call(write_key, "identify", payload, timeout)

    except Exception as e:
        logger.exception("identify failed")
        return {"ok": False, "error": str(e)}


def track(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Track an event performed by a user.

    Records an action that a user performs, along with properties that describe the action.

    Params:
        user_id (str): Unique identifier for the user (required unless anonymous_id provided)
        anonymous_id (str): Anonymous identifier (required if user_id not provided)
        event (str): Name of the event (required)
        properties (dict): Free-form dictionary of event properties (optional)
        context (dict): Context about the event (optional)
        timestamp (str): ISO timestamp when the event occurred (optional)
        integrations (dict): Dictionary to enable/disable integrations (optional)

    Returns:
        {"ok": True, "result": {"success": True}}
    """
    try:
        profile = load_profile(profile_name)
        write_key = _get_write_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        user_id = params.get("user_id")
        anonymous_id = params.get("anonymous_id")
        event = params.get("event")

        if not user_id and not anonymous_id:
            return {"ok": False, "error": "Either user_id or anonymous_id is required"}
        if not event:
            return {"ok": False, "error": "event is required"}

        payload: Dict[str, Any] = {
            "messageId": _generate_message_id(),
            "timestamp": params.get("timestamp", _get_timestamp()),
            "event": event,
        }

        if user_id:
            payload["userId"] = user_id
        if anonymous_id:
            payload["anonymousId"] = anonymous_id
        if params.get("properties"):
            payload["properties"] = params["properties"]
        if params.get("context"):
            payload["context"] = params["context"]
        if params.get("integrations"):
            payload["integrations"] = params["integrations"]

        return _api_call(write_key, "track", payload, timeout)

    except Exception as e:
        logger.exception("track failed")
        return {"ok": False, "error": str(e)}


def page(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Track a page view.

    Records whenever a user views a page on your website, along with optional properties.

    Params:
        user_id (str): Unique identifier for the user (required unless anonymous_id provided)
        anonymous_id (str): Anonymous identifier (required if user_id not provided)
        name (str): Name of the page (optional)
        category (str): Category of the page (optional)
        properties (dict): Free-form dictionary of page properties (optional)
        context (dict): Context about the event (optional)
        timestamp (str): ISO timestamp when the page view occurred (optional)
        integrations (dict): Dictionary to enable/disable integrations (optional)

    Returns:
        {"ok": True, "result": {"success": True}}
    """
    try:
        profile = load_profile(profile_name)
        write_key = _get_write_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        user_id = params.get("user_id")
        anonymous_id = params.get("anonymous_id")

        if not user_id and not anonymous_id:
            return {"ok": False, "error": "Either user_id or anonymous_id is required"}

        payload: Dict[str, Any] = {
            "messageId": _generate_message_id(),
            "timestamp": params.get("timestamp", _get_timestamp()),
        }

        if user_id:
            payload["userId"] = user_id
        if anonymous_id:
            payload["anonymousId"] = anonymous_id
        if params.get("name"):
            payload["name"] = params["name"]
        if params.get("category"):
            payload["category"] = params["category"]
        if params.get("properties"):
            payload["properties"] = params["properties"]
        if params.get("context"):
            payload["context"] = params["context"]
        if params.get("integrations"):
            payload["integrations"] = params["integrations"]

        return _api_call(write_key, "page", payload, timeout)

    except Exception as e:
        logger.exception("page failed")
        return {"ok": False, "error": str(e)}


def screen(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Track a screen view.

    Records whenever a user views a screen in your mobile app, along with optional properties.

    Params:
        user_id (str): Unique identifier for the user (required unless anonymous_id provided)
        anonymous_id (str): Anonymous identifier (required if user_id not provided)
        name (str): Name of the screen (optional)
        properties (dict): Free-form dictionary of screen properties (optional)
        context (dict): Context about the event (optional)
        timestamp (str): ISO timestamp when the screen view occurred (optional)
        integrations (dict): Dictionary to enable/disable integrations (optional)

    Returns:
        {"ok": True, "result": {"success": True}}
    """
    try:
        profile = load_profile(profile_name)
        write_key = _get_write_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        user_id = params.get("user_id")
        anonymous_id = params.get("anonymous_id")

        if not user_id and not anonymous_id:
            return {"ok": False, "error": "Either user_id or anonymous_id is required"}

        payload: Dict[str, Any] = {
            "messageId": _generate_message_id(),
            "timestamp": params.get("timestamp", _get_timestamp()),
        }

        if user_id:
            payload["userId"] = user_id
        if anonymous_id:
            payload["anonymousId"] = anonymous_id
        if params.get("name"):
            payload["name"] = params["name"]
        if params.get("properties"):
            payload["properties"] = params["properties"]
        if params.get("context"):
            payload["context"] = params["context"]
        if params.get("integrations"):
            payload["integrations"] = params["integrations"]

        return _api_call(write_key, "screen", payload, timeout)

    except Exception as e:
        logger.exception("screen failed")
        return {"ok": False, "error": str(e)}


def group(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Associate a user with a group.

    Associates an identified user with a company, organization, project, or other group.

    Params:
        user_id (str): Unique identifier for the user (required unless anonymous_id provided)
        anonymous_id (str): Anonymous identifier (required if user_id not provided)
        group_id (str): Unique identifier for the group (required)
        traits (dict): Free-form dictionary of group traits (optional)
        context (dict): Context about the event (optional)
        timestamp (str): ISO timestamp when the group association occurred (optional)
        integrations (dict): Dictionary to enable/disable integrations (optional)

    Returns:
        {"ok": True, "result": {"success": True}}
    """
    try:
        profile = load_profile(profile_name)
        write_key = _get_write_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        user_id = params.get("user_id")
        anonymous_id = params.get("anonymous_id")
        group_id = params.get("group_id")

        if not user_id and not anonymous_id:
            return {"ok": False, "error": "Either user_id or anonymous_id is required"}
        if not group_id:
            return {"ok": False, "error": "group_id is required"}

        payload: Dict[str, Any] = {
            "messageId": _generate_message_id(),
            "timestamp": params.get("timestamp", _get_timestamp()),
            "groupId": group_id,
        }

        if user_id:
            payload["userId"] = user_id
        if anonymous_id:
            payload["anonymousId"] = anonymous_id
        if params.get("traits"):
            payload["traits"] = params["traits"]
        if params.get("context"):
            payload["context"] = params["context"]
        if params.get("integrations"):
            payload["integrations"] = params["integrations"]

        return _api_call(write_key, "group", payload, timeout)

    except Exception as e:
        logger.exception("group failed")
        return {"ok": False, "error": str(e)}


def alias(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Alias two user IDs together.

    Merges two user identities, linking previous_id to user_id.

    Params:
        previous_id (str): The previous user identifier (required)
        user_id (str): The new user identifier (required)
        context (dict): Context about the event (optional)
        timestamp (str): ISO timestamp when the alias occurred (optional)
        integrations (dict): Dictionary to enable/disable integrations (optional)

    Returns:
        {"ok": True, "result": {"success": True}}
    """
    try:
        profile = load_profile(profile_name)
        write_key = _get_write_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        previous_id = params.get("previous_id")
        user_id = params.get("user_id")

        if not previous_id:
            return {"ok": False, "error": "previous_id is required"}
        if not user_id:
            return {"ok": False, "error": "user_id is required"}

        payload: Dict[str, Any] = {
            "messageId": _generate_message_id(),
            "timestamp": params.get("timestamp", _get_timestamp()),
            "previousId": previous_id,
            "userId": user_id,
        }

        if params.get("context"):
            payload["context"] = params["context"]
        if params.get("integrations"):
            payload["integrations"] = params["integrations"]

        return _api_call(write_key, "alias", payload, timeout)

    except Exception as e:
        logger.exception("alias failed")
        return {"ok": False, "error": str(e)}


def batch(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a batch of events.

    Sends multiple events in a single API call for efficiency.
    Each event in the batch should have a 'type' field (identify, track, page, screen, group, alias).

    Params:
        batch (list): Array of event objects (required)
            Each event should contain:
            - type (str): Event type (identify, track, page, screen, group, alias)
            - Plus the fields appropriate for that event type
        context (dict): Shared context for all events (optional)

    Returns:
        {"ok": True, "result": {"success": True}}

    Example batch:
        [
            {"type": "identify", "userId": "user123", "traits": {"name": "John"}},
            {"type": "track", "userId": "user123", "event": "Signed Up"}
        ]
    """
    try:
        profile = load_profile(profile_name)
        write_key = _get_write_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        batch_events = params.get("batch")

        if not batch_events:
            return {"ok": False, "error": "batch is required"}
        if not isinstance(batch_events, list):
            return {"ok": False, "error": "batch must be a list"}
        if len(batch_events) == 0:
            return {"ok": False, "error": "batch cannot be empty"}
        if len(batch_events) > 500:
            return {"ok": False, "error": "batch cannot contain more than 500 events"}

        # Process each event in the batch
        processed_events: List[Dict[str, Any]] = []
        shared_context = params.get("context", {})

        for i, event in enumerate(batch_events):
            if not isinstance(event, dict):
                return {"ok": False, "error": f"batch[{i}] must be a dict"}

            event_type = event.get("type")
            if not event_type:
                return {"ok": False, "error": f"batch[{i}] missing 'type' field"}
            if event_type not in ["identify", "track", "page", "screen", "group", "alias"]:
                return {"ok": False, "error": f"batch[{i}] has invalid type '{event_type}'"}

            # Add required fields if not present
            processed_event = dict(event)
            if "messageId" not in processed_event:
                processed_event["messageId"] = _generate_message_id()
            if "timestamp" not in processed_event:
                processed_event["timestamp"] = _get_timestamp()

            # Merge shared context
            if shared_context:
                event_context = processed_event.get("context", {})
                processed_event["context"] = {**shared_context, **event_context}

            processed_events.append(processed_event)

        payload = {
            "batch": processed_events,
        }

        return _api_call(write_key, "batch", payload, timeout)

    except Exception as e:
        logger.exception("batch failed")
        return {"ok": False, "error": str(e)}


def delete(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete user data via Privacy API.

    Submits a deletion request for a user's data according to GDPR/CCPA regulations.
    Requires Privacy API access token (access_token_env in profile).

    Params:
        user_id (str): User ID to delete (required)
        regulation_type (str): GDPR, CCPA, or SUPPRESS_ONLY (default: SUPPRESS_ONLY)

    Profile requirements:
        workspace_slug (str): Segment workspace slug (required)
        access_token_env (str): Environment variable containing access token (required)

    Returns:
        {"ok": True, "result": {"regulation_status": ...}}

    Note:
        This is an asynchronous operation. The deletion may take time to complete.
    """
    try:
        profile = load_profile(profile_name)
        access_token = _get_access_token(profile)
        workspace_slug = profile.get("workspace_slug")
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        if not workspace_slug:
            return {"ok": False, "error": "workspace_slug is required in profile for delete action"}

        user_id = params.get("user_id")
        regulation_type = params.get("regulation_type", "SUPPRESS_ONLY")

        if not user_id:
            return {"ok": False, "error": "user_id is required"}
        if regulation_type not in ["GDPR", "CCPA", "SUPPRESS_ONLY"]:
            return {"ok": False, "error": "regulation_type must be GDPR, CCPA, or SUPPRESS_ONLY"}

        payload = {
            "regulationType": regulation_type,
            "subjectType": "USER_ID",
            "subjectIds": [user_id],
        }

        return _privacy_api_call(
            access_token,
            workspace_slug,
            "regulations",
            payload,
            timeout=timeout
        )

    except Exception as e:
        logger.exception("delete failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "identify": identify,
    "track": track,
    "page": page,
    "screen": screen,
    "group": group,
    "alias": alias,
    "batch": batch,
    "delete": delete,
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

    logger.info(f"Executing segment.{profile}.{action}")
    return ACTIONS[action](profile, params)
