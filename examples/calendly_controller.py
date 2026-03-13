"""Calendly Controller for TinyHive

A controller for integrating with the Calendly API v2.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Calendly profile:
{
    "token_env": "CALENDLY_TOKEN"
}

Required OAuth Scopes:
---------------------
- Read access for user info, events, event types, invitees
- Write access for canceling events
- Webhook subscriptions management (if using webhooks)

Dependencies:
------------
- None (standard library only)

Method IDs:
  controller.calendly.{profile}.get_current_user
  controller.calendly.{profile}.list_event_types
  controller.calendly.{profile}.list_events
  controller.calendly.{profile}.get_event
  controller.calendly.{profile}.cancel_event
  controller.calendly.{profile}.list_invitees
  controller.calendly.{profile}.get_invitee
  controller.calendly.{profile}.list_webhooks
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.calendly")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Calendly API base URL
CALENDLY_API_BASE = "https://api.calendly.com"

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
    """Get the Calendly access token from environment variable."""
    token_env = profile.get("token_env", "CALENDLY_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(
            f"Environment variable '{token_env}' not set. "
            "Set your Calendly access token in this environment variable."
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
    """
    Make an authenticated Calendly API call.

    Args:
        token: Calendly access token
        endpoint: API endpoint (e.g., 'users/me')
        method: HTTP method (GET, POST, DELETE)
        data: Request payload for POST requests
        query_params: URL query parameters
        timeout: Request timeout in seconds

    Returns:
        Response dict with 'ok' field and result/error
    """
    url = f"{CALENDLY_API_BASE}/{endpoint}"

    # Add query parameters if provided
    if query_params:
        # Filter out None values
        filtered_params = {k: v for k, v in query_params.items() if v is not None}
        if filtered_params:
            url = f"{url}?{urlencode(filtered_params)}"

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
            else:
                result = {}
            return {"ok": True, "result": result}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("message", error_json.get("title", error_body[:500]))
        except json.JSONDecodeError:
            error_msg = error_body[:500]
        logger.error("Calendly HTTP error %d: %s", e.code, error_msg)
        return {"ok": False, "error": f"HTTP {e.code}: {error_msg}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Calendly API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def get_current_user(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the currently authenticated user's information.

    Params:
        None required

    Returns:
        ok (bool): Success status
        result (dict): User resource including uri, name, email, scheduling_url, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        return _api_call(token, "users/me")

    except Exception as e:
        logger.exception("get_current_user failed")
        return {"ok": False, "error": str(e)}


def list_event_types(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List event types for a user.

    Params:
        user_uri (str): User URI to list event types for (required)
        active (bool): Filter by active status (optional)
        count (int): Number of results per page (default: 20, max: 100) (optional)
        page_token (str): Token for pagination (optional)
        sort (str): Sort order, e.g., 'name:asc' or 'name:desc' (optional)

    Returns:
        ok (bool): Success status
        result (dict): Collection of event types with pagination info
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        user_uri = params.get("user_uri")
        if not user_uri:
            return {"ok": False, "error": "user_uri is required"}

        query_params = {
            "user": user_uri,
        }

        if params.get("active") is not None:
            query_params["active"] = str(params["active"]).lower()

        if params.get("count"):
            query_params["count"] = min(int(params["count"]), 100)

        if params.get("page_token"):
            query_params["page_token"] = params["page_token"]

        if params.get("sort"):
            query_params["sort"] = params["sort"]

        return _api_call(token, "event_types", query_params=query_params)

    except Exception as e:
        logger.exception("list_event_types failed")
        return {"ok": False, "error": str(e)}


def list_events(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List scheduled events for a user.

    Params:
        user_uri (str): User URI to list events for (required)
        min_start_time (str): Lower bound for event start time (ISO 8601 format) (optional)
        max_start_time (str): Upper bound for event start time (ISO 8601 format) (optional)
        status (str): Filter by status: 'active' or 'canceled' (optional)
        count (int): Number of results per page (default: 20, max: 100) (optional)
        page_token (str): Token for pagination (optional)
        sort (str): Sort order, e.g., 'start_time:asc' or 'start_time:desc' (optional)
        invitee_email (str): Filter by invitee email (optional)

    Returns:
        ok (bool): Success status
        result (dict): Collection of scheduled events with pagination info
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        user_uri = params.get("user_uri")
        if not user_uri:
            return {"ok": False, "error": "user_uri is required"}

        query_params = {
            "user": user_uri,
        }

        if params.get("min_start_time"):
            query_params["min_start_time"] = params["min_start_time"]

        if params.get("max_start_time"):
            query_params["max_start_time"] = params["max_start_time"]

        if params.get("status"):
            query_params["status"] = params["status"]

        if params.get("count"):
            query_params["count"] = min(int(params["count"]), 100)

        if params.get("page_token"):
            query_params["page_token"] = params["page_token"]

        if params.get("sort"):
            query_params["sort"] = params["sort"]

        if params.get("invitee_email"):
            query_params["invitee_email"] = params["invitee_email"]

        return _api_call(token, "scheduled_events", query_params=query_params)

    except Exception as e:
        logger.exception("list_events failed")
        return {"ok": False, "error": str(e)}


def get_event(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific scheduled event.

    Params:
        event_uuid (str): UUID of the scheduled event (required)

    Returns:
        ok (bool): Success status
        result (dict): Event resource with details
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        event_uuid = params.get("event_uuid")
        if not event_uuid:
            return {"ok": False, "error": "event_uuid is required"}

        return _api_call(token, f"scheduled_events/{event_uuid}")

    except Exception as e:
        logger.exception("get_event failed")
        return {"ok": False, "error": str(e)}


def cancel_event(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cancel a scheduled event.

    Params:
        event_uuid (str): UUID of the scheduled event to cancel (required)
        reason (str): Cancellation reason (optional)

    Returns:
        ok (bool): Success status
        result (dict): Cancellation details
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        event_uuid = params.get("event_uuid")
        if not event_uuid:
            return {"ok": False, "error": "event_uuid is required"}

        data = {}
        if params.get("reason"):
            data["reason"] = params["reason"]

        return _api_call(
            token,
            f"scheduled_events/{event_uuid}/cancellation",
            method="POST",
            data=data
        )

    except Exception as e:
        logger.exception("cancel_event failed")
        return {"ok": False, "error": str(e)}


def list_invitees(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List invitees for a scheduled event.

    Params:
        event_uuid (str): UUID of the scheduled event (required)
        count (int): Number of results per page (default: 20, max: 100) (optional)
        page_token (str): Token for pagination (optional)
        sort (str): Sort order, e.g., 'created_at:asc' or 'created_at:desc' (optional)
        status (str): Filter by status: 'active' or 'canceled' (optional)
        email (str): Filter by invitee email (optional)

    Returns:
        ok (bool): Success status
        result (dict): Collection of invitees with pagination info
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        event_uuid = params.get("event_uuid")
        if not event_uuid:
            return {"ok": False, "error": "event_uuid is required"}

        query_params = {}

        if params.get("count"):
            query_params["count"] = min(int(params["count"]), 100)

        if params.get("page_token"):
            query_params["page_token"] = params["page_token"]

        if params.get("sort"):
            query_params["sort"] = params["sort"]

        if params.get("status"):
            query_params["status"] = params["status"]

        if params.get("email"):
            query_params["email"] = params["email"]

        return _api_call(
            token,
            f"scheduled_events/{event_uuid}/invitees",
            query_params=query_params if query_params else None
        )

    except Exception as e:
        logger.exception("list_invitees failed")
        return {"ok": False, "error": str(e)}


def get_invitee(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific invitee.

    Params:
        invitee_uuid (str): UUID of the invitee (required)

    Returns:
        ok (bool): Success status
        result (dict): Invitee resource with details
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        invitee_uuid = params.get("invitee_uuid")
        if not invitee_uuid:
            return {"ok": False, "error": "invitee_uuid is required"}

        return _api_call(token, f"invitees/{invitee_uuid}")

    except Exception as e:
        logger.exception("get_invitee failed")
        return {"ok": False, "error": str(e)}


def list_webhooks(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List webhook subscriptions.

    Params:
        organization_uri (str): Organization URI to list webhooks for (required)
        scope (str): Scope of webhooks: 'organization' or 'user' (required)
        user_uri (str): User URI (required if scope is 'user') (optional)
        count (int): Number of results per page (default: 20, max: 100) (optional)
        page_token (str): Token for pagination (optional)
        sort (str): Sort order, e.g., 'created_at:asc' or 'created_at:desc' (optional)

    Returns:
        ok (bool): Success status
        result (dict): Collection of webhook subscriptions with pagination info
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        organization_uri = params.get("organization_uri")
        scope = params.get("scope")

        if not organization_uri:
            return {"ok": False, "error": "organization_uri is required"}
        if not scope:
            return {"ok": False, "error": "scope is required"}
        if scope not in ("organization", "user"):
            return {"ok": False, "error": "scope must be 'organization' or 'user'"}

        query_params = {
            "organization": organization_uri,
            "scope": scope,
        }

        if scope == "user":
            user_uri = params.get("user_uri")
            if not user_uri:
                return {"ok": False, "error": "user_uri is required when scope is 'user'"}
            query_params["user"] = user_uri

        if params.get("count"):
            query_params["count"] = min(int(params["count"]), 100)

        if params.get("page_token"):
            query_params["page_token"] = params["page_token"]

        if params.get("sort"):
            query_params["sort"] = params["sort"]

        return _api_call(token, "webhook_subscriptions", query_params=query_params)

    except Exception as e:
        logger.exception("list_webhooks failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "get_current_user": get_current_user,
    "list_event_types": list_event_types,
    "list_events": list_events,
    "get_event": get_event,
    "cancel_event": cancel_event,
    "list_invitees": list_invitees,
    "get_invitee": get_invitee,
    "list_webhooks": list_webhooks,
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

    logger.info(f"Executing calendly.{profile}.{action}")
    return ACTIONS[action](profile, params)
