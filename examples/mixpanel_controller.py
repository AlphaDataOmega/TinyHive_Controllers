"""Mixpanel Controller — Mixpanel Analytics integration via REST APIs.

This controller provides integration with Mixpanel for event tracking,
user profile management, and data querying using service account authentication.

Method IDs:
  controller.mixpanel.{profile}.track
  controller.mixpanel.{profile}.track_batch
  controller.mixpanel.{profile}.set_profile
  controller.mixpanel.{profile}.update_profile
  controller.mixpanel.{profile}.query_events
  controller.mixpanel.{profile}.query_funnels
  controller.mixpanel.{profile}.export_events
  controller.mixpanel.{profile}.list_cohorts

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:

    {
      "project_id": "12345678",
      "project_token": "your_project_token",
      "service_account_username_env": "MIXPANEL_SERVICE_ACCOUNT_USERNAME",
      "service_account_secret_env": "MIXPANEL_SERVICE_ACCOUNT_SECRET"
    }

  - project_id: Mixpanel project ID (required for queries)
  - project_token: Token for ingestion API (track/profile operations)
  - service_account_username_env: Environment variable for service account username
  - service_account_secret_env: Environment variable for service account secret

API Endpoints:
  - Ingestion API: https://api.mixpanel.com
  - Query/Data API: https://data.mixpanel.com/api/2.0

Dependencies:
  - None (standard library only)
"""

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.mixpanel")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# Mixpanel API endpoints
INGESTION_API_BASE = "https://api.mixpanel.com"
DATA_API_BASE = "https://data.mixpanel.com/api/2.0"

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with Mixpanel configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available Mixpanel profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# Authentication Helpers
# =============================================================================

def _get_service_account_auth(profile: Dict[str, Any]) -> str:
    """Get Basic Auth header value for service account authentication."""
    username_env = profile.get("service_account_username_env", "MIXPANEL_SERVICE_ACCOUNT_USERNAME")
    secret_env = profile.get("service_account_secret_env", "MIXPANEL_SERVICE_ACCOUNT_SECRET")

    username = os.environ.get(username_env, "")
    secret = os.environ.get(secret_env, "")

    if not username or not secret:
        raise ValueError(
            f"Service account credentials not found. "
            f"Set environment variables: {username_env} and {secret_env}"
        )

    credentials = f"{username}:{secret}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


def _get_project_token(profile: Dict[str, Any]) -> str:
    """Get project token for ingestion API."""
    token = profile.get("project_token", "")
    if not token:
        raise ValueError("project_token required in profile for ingestion operations")
    return token


def _get_project_id(profile: Dict[str, Any], params: Dict[str, Any]) -> str:
    """Get project ID from params or profile."""
    project_id = params.get("project_id", profile.get("project_id", ""))
    if not project_id:
        raise ValueError("project_id required (in profile or params)")
    return str(project_id)


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make a Mixpanel API call."""
    request_headers = {
        "Accept": "application/json",
    }
    if headers:
        request_headers.update(headers)

    if data and "Content-Type" not in request_headers:
        request_headers["Content-Type"] = "application/json"

    try:
        req = Request(url, data=data, headers=request_headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                try:
                    return {"ok": True, "data": json.loads(response_body)}
                except json.JSONDecodeError:
                    return {"ok": True, "data": response_body}
            return {"ok": True, "data": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("error", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Mixpanel API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Mixpanel API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Event Tracking Actions
# =============================================================================

def track(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Track a single event.

    Params:
        event (str): Event name (required)
        distinct_id (str): User identifier (required)
        properties (dict): Additional event properties (optional)
        time (int): Unix timestamp in seconds (optional, defaults to now)
    """
    profile = load_profile(profile_name)
    token = _get_project_token(profile)

    event_name = params.get("event", "")
    distinct_id = params.get("distinct_id", "")
    properties = params.get("properties", {})
    event_time = params.get("time", int(time.time()))

    if not event_name:
        return {"ok": False, "error": "event is required"}
    if not distinct_id:
        return {"ok": False, "error": "distinct_id is required"}

    # Build event payload
    event_data = {
        "event": event_name,
        "properties": {
            "token": token,
            "distinct_id": distinct_id,
            "time": event_time,
            **properties
        }
    }

    url = f"{INGESTION_API_BASE}/track"
    data = json.dumps([event_data]).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    result = _api_call(url, method="POST", data=data, headers=headers)

    if result.get("ok"):
        # Mixpanel returns 1 for success, 0 for failure
        response_data = result.get("data")
        if response_data == 1 or response_data == "1":
            return {"ok": True, "result": {"tracked": True, "event": event_name}}
        else:
            return {"ok": False, "error": f"Tracking failed: {response_data}"}
    return result


def track_batch(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Track multiple events in a single request.

    Params:
        events (list): List of event objects, each containing:
            - event (str): Event name (required)
            - distinct_id (str): User identifier (required)
            - properties (dict): Additional event properties (optional)
            - time (int): Unix timestamp (optional)
    """
    profile = load_profile(profile_name)
    token = _get_project_token(profile)

    events = params.get("events", [])
    if not events:
        return {"ok": False, "error": "events list is required"}
    if not isinstance(events, list):
        return {"ok": False, "error": "events must be a list"}

    # Build batch payload
    batch_data = []
    current_time = int(time.time())

    for i, event in enumerate(events):
        event_name = event.get("event", "")
        distinct_id = event.get("distinct_id", "")

        if not event_name:
            return {"ok": False, "error": f"event name required for event at index {i}"}
        if not distinct_id:
            return {"ok": False, "error": f"distinct_id required for event at index {i}"}

        properties = event.get("properties", {})
        event_time = event.get("time", current_time)

        batch_data.append({
            "event": event_name,
            "properties": {
                "token": token,
                "distinct_id": distinct_id,
                "time": event_time,
                **properties
            }
        })

    url = f"{INGESTION_API_BASE}/track"
    data = json.dumps(batch_data).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    result = _api_call(url, method="POST", data=data, headers=headers)

    if result.get("ok"):
        response_data = result.get("data")
        if response_data == 1 or response_data == "1":
            return {"ok": True, "result": {"tracked": True, "count": len(batch_data)}}
        else:
            return {"ok": False, "error": f"Batch tracking failed: {response_data}"}
    return result


# =============================================================================
# Profile Management Actions
# =============================================================================

def set_profile(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Set user profile properties (overwrites existing values).

    Params:
        distinct_id (str): User identifier (required)
        properties (dict): Profile properties to set (required)
    """
    profile = load_profile(profile_name)
    token = _get_project_token(profile)

    distinct_id = params.get("distinct_id", "")
    properties = params.get("properties", {})

    if not distinct_id:
        return {"ok": False, "error": "distinct_id is required"}
    if not properties:
        return {"ok": False, "error": "properties is required"}

    # Build profile update payload
    profile_data = {
        "$token": token,
        "$distinct_id": distinct_id,
        "$set": properties
    }

    url = f"{INGESTION_API_BASE}/engage"
    data = json.dumps([profile_data]).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    result = _api_call(url, method="POST", data=data, headers=headers)

    if result.get("ok"):
        response_data = result.get("data")
        if response_data == 1 or response_data == "1":
            return {"ok": True, "result": {"updated": True, "distinct_id": distinct_id}}
        else:
            return {"ok": False, "error": f"Profile update failed: {response_data}"}
    return result


def update_profile(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update user profile with a specific operation.

    Params:
        distinct_id (str): User identifier (required)
        operation (str): Update operation (required). One of:
            - $set: Set properties (overwrite)
            - $set_once: Set only if not exists
            - $add: Increment numeric properties
            - $append: Append to list properties
            - $union: Add to list without duplicates
            - $remove: Remove from list properties
            - $unset: Remove properties
            - $delete: Delete the profile
        properties (dict): Properties for the operation (required unless $delete)
    """
    profile = load_profile(profile_name)
    token = _get_project_token(profile)

    distinct_id = params.get("distinct_id", "")
    operation = params.get("operation", "")
    properties = params.get("properties", {})

    if not distinct_id:
        return {"ok": False, "error": "distinct_id is required"}
    if not operation:
        return {"ok": False, "error": "operation is required"}

    valid_operations = ["$set", "$set_once", "$add", "$append", "$union", "$remove", "$unset", "$delete"]
    if operation not in valid_operations:
        return {"ok": False, "error": f"Invalid operation. Must be one of: {valid_operations}"}

    if operation != "$delete" and not properties:
        return {"ok": False, "error": "properties is required for this operation"}

    # Build profile update payload
    profile_data = {
        "$token": token,
        "$distinct_id": distinct_id,
    }

    if operation == "$delete":
        profile_data["$delete"] = ""
    elif operation == "$unset":
        # $unset expects a list of property names
        profile_data["$unset"] = list(properties.keys()) if isinstance(properties, dict) else properties
    else:
        profile_data[operation] = properties

    url = f"{INGESTION_API_BASE}/engage"
    data = json.dumps([profile_data]).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    result = _api_call(url, method="POST", data=data, headers=headers)

    if result.get("ok"):
        response_data = result.get("data")
        if response_data == 1 or response_data == "1":
            return {"ok": True, "result": {"updated": True, "distinct_id": distinct_id, "operation": operation}}
        else:
            return {"ok": False, "error": f"Profile update failed: {response_data}"}
    return result


# =============================================================================
# Query Actions (Service Account Auth)
# =============================================================================

def query_events(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Query event data using Insights API.

    Requires service account authentication.

    Params:
        from_date (str): Start date in YYYY-MM-DD format (required)
        to_date (str): End date in YYYY-MM-DD format (required)
        event (str): Event name to query (optional, queries all if not specified)
        project_id (str): Mixpanel project ID (optional, uses profile default)
    """
    profile = load_profile(profile_name)
    auth_header = _get_service_account_auth(profile)
    project_id = _get_project_id(profile, params)

    from_date = params.get("from_date", "")
    to_date = params.get("to_date", "")
    event = params.get("event")

    if not from_date:
        return {"ok": False, "error": "from_date is required (YYYY-MM-DD)"}
    if not to_date:
        return {"ok": False, "error": "to_date is required (YYYY-MM-DD)"}

    # Build query parameters
    query_params = {
        "project_id": project_id,
        "from_date": from_date,
        "to_date": to_date,
    }
    if event:
        query_params["event"] = json.dumps([event])

    url = f"{DATA_API_BASE}/insights?{urlencode(query_params)}"
    headers = {"Authorization": auth_header}

    result = _api_call(url, method="GET", headers=headers)

    if result.get("ok"):
        return {"ok": True, "data": result.get("data", {})}
    return result


def query_funnels(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Query funnel data.

    Requires service account authentication.

    Params:
        funnel_id (int): Funnel ID to query (required)
        from_date (str): Start date in YYYY-MM-DD format (required)
        to_date (str): End date in YYYY-MM-DD format (required)
        project_id (str): Mixpanel project ID (optional, uses profile default)
        unit (str): Time unit for breakdown (optional: day, week, month)
    """
    profile = load_profile(profile_name)
    auth_header = _get_service_account_auth(profile)
    project_id = _get_project_id(profile, params)

    funnel_id = params.get("funnel_id")
    from_date = params.get("from_date", "")
    to_date = params.get("to_date", "")
    unit = params.get("unit")

    if not funnel_id:
        return {"ok": False, "error": "funnel_id is required"}
    if not from_date:
        return {"ok": False, "error": "from_date is required (YYYY-MM-DD)"}
    if not to_date:
        return {"ok": False, "error": "to_date is required (YYYY-MM-DD)"}

    # Build query parameters
    query_params = {
        "project_id": project_id,
        "funnel_id": funnel_id,
        "from_date": from_date,
        "to_date": to_date,
    }
    if unit:
        query_params["unit"] = unit

    url = f"{DATA_API_BASE}/funnels?{urlencode(query_params)}"
    headers = {"Authorization": auth_header}

    result = _api_call(url, method="GET", headers=headers)

    if result.get("ok"):
        return {"ok": True, "data": result.get("data", {})}
    return result


def export_events(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Export raw event data.

    Requires service account authentication.
    Returns JSONL (newline-delimited JSON) data.

    Params:
        from_date (str): Start date in YYYY-MM-DD format (required)
        to_date (str): End date in YYYY-MM-DD format (required)
        event (str): Event name to export (optional, exports all if not specified)
        project_id (str): Mixpanel project ID (optional, uses profile default)
        limit (int): Maximum number of events to return (optional)
    """
    profile = load_profile(profile_name)
    auth_header = _get_service_account_auth(profile)
    project_id = _get_project_id(profile, params)

    from_date = params.get("from_date", "")
    to_date = params.get("to_date", "")
    event = params.get("event")
    limit = params.get("limit")

    if not from_date:
        return {"ok": False, "error": "from_date is required (YYYY-MM-DD)"}
    if not to_date:
        return {"ok": False, "error": "to_date is required (YYYY-MM-DD)"}

    # Build query parameters
    query_params = {
        "project_id": project_id,
        "from_date": from_date,
        "to_date": to_date,
    }
    if event:
        query_params["event"] = json.dumps([event])
    if limit:
        query_params["limit"] = limit

    url = f"{DATA_API_BASE}/export?{urlencode(query_params)}"
    headers = {"Authorization": auth_header}

    try:
        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            response_body = response.read().decode("utf-8")

            # Parse JSONL response
            events = []
            for line in response_body.strip().split("\n"):
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            return {"ok": True, "data": {"events": events, "count": len(events)}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error("Export error %d: %s", e.code, error_body[:500])
        return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Export failed")
        return {"ok": False, "error": str(e)}


def list_cohorts(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all cohorts in the project.

    Requires service account authentication.

    Params:
        project_id (str): Mixpanel project ID (optional, uses profile default)
    """
    profile = load_profile(profile_name)
    auth_header = _get_service_account_auth(profile)
    project_id = _get_project_id(profile, params)

    url = f"{DATA_API_BASE}/cohorts/list?project_id={project_id}"
    headers = {"Authorization": auth_header}

    result = _api_call(url, method="GET", headers=headers)

    if result.get("ok"):
        cohorts_data = result.get("data", [])
        # Format cohort data
        cohorts = []
        if isinstance(cohorts_data, list):
            for cohort in cohorts_data:
                cohorts.append({
                    "id": cohort.get("id"),
                    "name": cohort.get("name"),
                    "description": cohort.get("description", ""),
                    "count": cohort.get("count"),
                    "created": cohort.get("created"),
                })
        return {"ok": True, "data": {"cohorts": cohorts, "count": len(cohorts)}}
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "track": track,
    "track_batch": track_batch,
    "set_profile": set_profile,
    "update_profile": update_profile,
    "query_events": query_events,
    "query_funnels": query_funnels,
    "export_events": export_events,
    "list_cohorts": list_cohorts,
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
        return {"ok": False, "error": f"Unknown action '{action}'. Available: {list(ACTIONS.keys())}"}

    try:
        logger.info(f"Executing mixpanel.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
