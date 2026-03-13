"""Example: Google controller — Gmail, Calendar, Drive integration.

This is an example skeleton for a Google Workspace controller.
OAuth setup required before use.

Method IDs:
  controller.google.{profile}.list_messages
  controller.google.{profile}.send_email
  controller.google.{profile}.list_events
  controller.google.{profile}.create_event
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List
from urllib.request import Request, urlopen
from urllib.error import HTTPError

log = logging.getLogger("tinyhive.controller.google")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'")
    return json.loads(path.read_text())


def _get_access_token(profile: Dict[str, Any]) -> str:
    """Get OAuth access token.

    In production, this would refresh the token if expired.
    """
    env_var = profile.get("token_env", "GOOGLE_ACCESS_TOKEN")
    token = os.environ.get(env_var, "")
    if not token:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return token


def _api_call(
    token: str,
    url: str,
    method: str = "GET",
    data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Make a Google API call."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    body = json.dumps(data).encode("utf-8") if data else None

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=30) as response:
            return {"ok": True, "data": json.loads(response.read().decode("utf-8"))}
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {body[:500]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Gmail Actions
# ---------------------------------------------------------------------------

def list_messages(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List Gmail messages.

    Params:
        - query: Gmail search query (e.g., "is:unread")
        - max_results: Max messages to return (default: 10)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    query = params.get("query", "is:unread")
    max_results = params.get("max_results", 10)

    url = (
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages"
        f"?q={query}&maxResults={max_results}"
    )

    return _api_call(token, url)


def send_email(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Send an email.

    Params:
        - to: Recipient email (required)
        - subject: Email subject (required)
        - body: Email body (required)

    Note: This action requires SPINE approval.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    to = params.get("to", "")
    subject = params.get("subject", "")
    body = params.get("body", "")

    if not to or not subject or not body:
        return {"ok": False, "error": "to, subject, and body are required"}

    # Build RFC 2822 message
    import base64
    message = f"To: {to}\nSubject: {subject}\n\n{body}"
    raw = base64.urlsafe_b64encode(message.encode("utf-8")).decode("utf-8")

    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    return _api_call(token, url, method="POST", data={"raw": raw})


# ---------------------------------------------------------------------------
# Calendar Actions
# ---------------------------------------------------------------------------

def list_events(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List upcoming calendar events.

    Params:
        - calendar_id: Calendar ID (default: "primary")
        - max_results: Max events to return (default: 10)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    calendar_id = params.get("calendar_id", "primary")
    max_results = params.get("max_results", 10)

    url = (
        f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
        f"?maxResults={max_results}&orderBy=startTime&singleEvents=true"
    )

    return _api_call(token, url)


def create_event(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a calendar event.

    Params:
        - summary: Event title (required)
        - start: Start time ISO format (required)
        - end: End time ISO format (required)
        - calendar_id: Calendar ID (default: "primary")

    Note: External invites require SPINE approval.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    summary = params.get("summary", "")
    start = params.get("start", "")
    end = params.get("end", "")
    calendar_id = params.get("calendar_id", "primary")

    if not summary or not start or not end:
        return {"ok": False, "error": "summary, start, and end are required"}

    event_data = {
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }

    url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
    return _api_call(token, url, method="POST", data=event_data)


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

ACTIONS = {
    "list_messages": list_messages,
    "send_email": send_email,
    "list_events": list_events,
    "create_event": create_event,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """Dispatch an action by name with a profile."""
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action '{action}'"}
    return ACTIONS[action](profile, params)
