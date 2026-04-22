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


# Per-profile in-process token cache: {access_env_name: {"access_token": ..., "expires_at": ...}}
# Keying by access_env_name means each profile (webwidgetjames, sterlingtuttle, etc.)
# gets its own cache slot and refreshes don't clobber each other.
_TOKEN_CACHE: Dict[str, Dict[str, Any]] = {}
_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _refresh_access_token(profile: Dict[str, Any]) -> str:
    """Exchange the profile's refresh token for a fresh access token.

    Uses the profile's ``refresh_env`` / ``token_env`` if declared, so each
    Google account (default, webwidgetjames, sterlingtuttle, ...) refreshes
    into its own env slot instead of contaminating the global one. Falls
    back to ``GOOGLE_REFRESH_TOKEN`` / ``GOOGLE_ACCESS_TOKEN`` when the
    profile doesn't declare per-profile names (backward-compat).

    Client credentials (CLIENT_ID / CLIENT_SECRET) are shared across
    profiles — they come from the single OAuth app registered in Google
    Cloud Console — so those remain global.

    Uses stdlib urllib — no pip deps. Caches the minted token in-process
    until ~60 s before expiry, keyed by the profile's access-env name.
    """
    import time
    from urllib.parse import urlencode

    access_env = profile.get("token_env", "GOOGLE_ACCESS_TOKEN")
    refresh_env = profile.get("refresh_env", "GOOGLE_REFRESH_TOKEN")

    refresh_token = os.environ.get(refresh_env, "")
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    missing = [k for k, v in [
        (refresh_env, refresh_token),
        ("GOOGLE_CLIENT_ID", client_id),
        ("GOOGLE_CLIENT_SECRET", client_secret),
    ] if not v]
    if missing:
        raise ValueError(
            f"Cannot refresh access token for profile '{profile.get('name','?')}' — "
            f"missing env vars: {', '.join(missing)}. "
            f"Complete OAuth for this profile via the marketplace first."
        )

    body = urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")

    req = Request(
        _TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise ValueError(
            f"Google token refresh failed for '{profile.get('name','?')}' "
            f"(HTTP {e.code}): {detail[:300]}"
        )

    access_token = payload.get("access_token", "")
    expires_in = int(payload.get("expires_in", 3600))
    if not access_token:
        raise ValueError(f"Token endpoint returned no access_token: {payload}")

    _TOKEN_CACHE[access_env] = {
        "access_token": access_token,
        "expires_at": time.time() + max(expires_in - 60, 60),
    }
    # Write the fresh token to this profile's env slot so subsequent reads
    # (including from other modules) see it.
    os.environ[access_env] = access_token
    return access_token


def _get_access_token(profile: Dict[str, Any]) -> str:
    """Get OAuth access token for a profile.

    Order of precedence:
    1. Env var named by the profile (``token_env``, default GOOGLE_ACCESS_TOKEN).
    2. Per-profile in-process cache (keyed by the access-env name).
    3. Refresh from the profile's refresh token.
    """
    import time

    env_var = profile.get("token_env", "GOOGLE_ACCESS_TOKEN")
    token = os.environ.get(env_var, "")
    if token:
        return token

    cached = _TOKEN_CACHE.get(env_var) or {}
    if cached.get("access_token") and cached.get("expires_at", 0) > time.time():
        return cached["access_token"]

    return _refresh_access_token(profile)


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
