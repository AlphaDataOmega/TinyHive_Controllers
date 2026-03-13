"""PostHog Controller — PostHog Product Analytics integration via REST APIs.

This controller provides integration with PostHog for event tracking,
user identification, feature flags, and analytics querying.

Method IDs:
  controller.posthog.{profile}.capture
  controller.posthog.{profile}.identify
  controller.posthog.{profile}.batch
  controller.posthog.{profile}.get_persons
  controller.posthog.{profile}.get_events
  controller.posthog.{profile}.list_feature_flags
  controller.posthog.{profile}.get_feature_flag
  controller.posthog.{profile}.list_insights

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:

    {
      "api_key_env": "POSTHOG_API_KEY",
      "host": "https://app.posthog.com",
      "project_id": "12345"
    }

  - api_key_env: Environment variable containing the PostHog API key (required)
  - host: PostHog instance URL (default: https://app.posthog.com)
  - project_id: PostHog project ID (required for query APIs)

API Endpoints:
  - Capture API: POST /capture
  - Batch API: POST /batch
  - Query APIs: /api/projects/{project_id}/...

Dependencies:
  - None (standard library only)
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.posthog")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# Default PostHog cloud URL
DEFAULT_HOST = "https://app.posthog.com"

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with PostHog configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available PostHog profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# Authentication Helpers
# =============================================================================

def _get_api_key(profile: Dict[str, Any]) -> str:
    """Get API key from environment variable."""
    api_key_env = profile.get("api_key_env", "POSTHOG_API_KEY")
    api_key = os.environ.get(api_key_env, "")

    if not api_key:
        raise ValueError(
            f"PostHog API key not found. "
            f"Set environment variable: {api_key_env}"
        )
    return api_key


def _get_host(profile: Dict[str, Any]) -> str:
    """Get PostHog host URL from profile."""
    host = profile.get("host", DEFAULT_HOST)
    # Remove trailing slash if present
    return host.rstrip("/")


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
    """Make a PostHog API call."""
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
            error_message = error_data.get("detail", error_data.get("error", error_body[:500]))
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("PostHog API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in PostHog API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Event Capture Actions
# =============================================================================

def capture(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Capture a single event.

    Params:
        distinct_id (str): User identifier (required)
        event (str): Event name (required)
        properties (dict): Additional event properties (optional)
        timestamp (str): ISO 8601 timestamp (optional, defaults to now)

    Returns:
        ok (bool): Success status
        result (dict): Confirmation of event capture
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    host = _get_host(profile)

    distinct_id = params.get("distinct_id", "")
    event = params.get("event", "")
    properties = params.get("properties", {})
    timestamp = params.get("timestamp")

    if not distinct_id:
        return {"ok": False, "error": "distinct_id is required"}
    if not event:
        return {"ok": False, "error": "event is required"}

    # Build event payload
    payload = {
        "api_key": api_key,
        "event": event,
        "distinct_id": distinct_id,
        "properties": properties,
    }

    if timestamp:
        payload["timestamp"] = timestamp

    url = f"{host}/capture/"
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    result = _api_call(url, method="POST", data=data, headers=headers)

    if result.get("ok"):
        response_data = result.get("data", {})
        # PostHog returns {"status": 1} for success
        if isinstance(response_data, dict) and response_data.get("status") == 1:
            return {"ok": True, "result": {"captured": True, "event": event, "distinct_id": distinct_id}}
        elif response_data == 1:
            return {"ok": True, "result": {"captured": True, "event": event, "distinct_id": distinct_id}}
        else:
            return {"ok": True, "result": {"captured": True, "event": event, "distinct_id": distinct_id, "response": response_data}}
    return result


def identify(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Identify a user and set their properties.

    Params:
        distinct_id (str): User identifier (required)
        properties (dict): User properties to set (optional)
            Use $set for properties to set
            Use $set_once for properties to set only if not already set

    Returns:
        ok (bool): Success status
        result (dict): Confirmation of identify call
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    host = _get_host(profile)

    distinct_id = params.get("distinct_id", "")
    properties = params.get("properties", {})

    if not distinct_id:
        return {"ok": False, "error": "distinct_id is required"}

    # Build identify payload using $identify event
    payload = {
        "api_key": api_key,
        "event": "$identify",
        "distinct_id": distinct_id,
        "properties": {
            "$set": properties
        },
    }

    url = f"{host}/capture/"
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    result = _api_call(url, method="POST", data=data, headers=headers)

    if result.get("ok"):
        response_data = result.get("data", {})
        if isinstance(response_data, dict) and response_data.get("status") == 1:
            return {"ok": True, "result": {"identified": True, "distinct_id": distinct_id}}
        elif response_data == 1:
            return {"ok": True, "result": {"identified": True, "distinct_id": distinct_id}}
        else:
            return {"ok": True, "result": {"identified": True, "distinct_id": distinct_id, "response": response_data}}
    return result


def batch(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a batch of events in a single request.

    Params:
        batch (list): List of event objects, each containing:
            - event (str): Event name (required)
            - distinct_id (str): User identifier (required)
            - properties (dict): Event properties (optional)
            - timestamp (str): ISO 8601 timestamp (optional)

    Returns:
        ok (bool): Success status
        result (dict): Confirmation of batch capture
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    host = _get_host(profile)

    events = params.get("batch", [])
    if not events:
        return {"ok": False, "error": "batch list is required"}
    if not isinstance(events, list):
        return {"ok": False, "error": "batch must be a list"}

    # Validate and build batch payload
    batch_data = []
    for i, event_obj in enumerate(events):
        event_name = event_obj.get("event", "")
        distinct_id = event_obj.get("distinct_id", "")

        if not event_name:
            return {"ok": False, "error": f"event name required for event at index {i}"}
        if not distinct_id:
            return {"ok": False, "error": f"distinct_id required for event at index {i}"}

        event_payload = {
            "event": event_name,
            "distinct_id": distinct_id,
            "properties": event_obj.get("properties", {}),
        }

        if event_obj.get("timestamp"):
            event_payload["timestamp"] = event_obj["timestamp"]

        batch_data.append(event_payload)

    # Build batch request
    payload = {
        "api_key": api_key,
        "batch": batch_data,
    }

    url = f"{host}/batch/"
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    result = _api_call(url, method="POST", data=data, headers=headers)

    if result.get("ok"):
        response_data = result.get("data", {})
        if isinstance(response_data, dict) and response_data.get("status") == 1:
            return {"ok": True, "result": {"captured": True, "count": len(batch_data)}}
        elif response_data == 1:
            return {"ok": True, "result": {"captured": True, "count": len(batch_data)}}
        else:
            return {"ok": True, "result": {"captured": True, "count": len(batch_data), "response": response_data}}
    return result


# =============================================================================
# Query Actions (API Key Auth)
# =============================================================================

def get_persons(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List persons (users) in PostHog.

    Params:
        search (str): Search query for persons (optional)
        properties (dict): Filter by person properties (optional)
        limit (int): Maximum number of results (default: 100)
        offset (int): Pagination offset (default: 0)
        project_id (str): PostHog project ID (optional, uses profile default)

    Returns:
        ok (bool): Success status
        data (dict): List of persons with pagination info
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    host = _get_host(profile)
    project_id = _get_project_id(profile, params)

    search = params.get("search")
    properties = params.get("properties")
    limit = params.get("limit", 100)
    offset = params.get("offset", 0)

    # Build query parameters
    query_params = {
        "limit": limit,
        "offset": offset,
    }
    if search:
        query_params["search"] = search
    if properties:
        query_params["properties"] = json.dumps(properties)

    url = f"{host}/api/projects/{project_id}/persons/?{urlencode(query_params)}"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    result = _api_call(url, method="GET", headers=headers)

    if result.get("ok"):
        data = result.get("data", {})
        persons = data.get("results", [])
        return {
            "ok": True,
            "data": {
                "persons": persons,
                "count": len(persons),
                "next": data.get("next"),
                "previous": data.get("previous"),
            }
        }
    return result


def get_events(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Query events from PostHog.

    Params:
        event (str): Filter by event name (optional)
        date_from (str): Start date in YYYY-MM-DD or ISO 8601 format (optional)
        date_to (str): End date in YYYY-MM-DD or ISO 8601 format (optional)
        person_id (str): Filter by person ID (optional)
        distinct_id (str): Filter by distinct ID (optional)
        limit (int): Maximum number of results (default: 100)
        project_id (str): PostHog project ID (optional, uses profile default)

    Returns:
        ok (bool): Success status
        data (dict): List of events with pagination info
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    host = _get_host(profile)
    project_id = _get_project_id(profile, params)

    event = params.get("event")
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    person_id = params.get("person_id")
    distinct_id = params.get("distinct_id")
    limit = params.get("limit", 100)

    # Build query parameters
    query_params = {
        "limit": limit,
    }
    if event:
        query_params["event"] = event
    if date_from:
        query_params["after"] = date_from
    if date_to:
        query_params["before"] = date_to
    if person_id:
        query_params["person_id"] = person_id
    if distinct_id:
        query_params["distinct_id"] = distinct_id

    url = f"{host}/api/projects/{project_id}/events/?{urlencode(query_params)}"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    result = _api_call(url, method="GET", headers=headers)

    if result.get("ok"):
        data = result.get("data", {})
        events = data.get("results", [])
        return {
            "ok": True,
            "data": {
                "events": events,
                "count": len(events),
                "next": data.get("next"),
                "previous": data.get("previous"),
            }
        }
    return result


# =============================================================================
# Feature Flags Actions
# =============================================================================

def list_feature_flags(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all feature flags in the project.

    Params:
        active (bool): Filter by active status (optional)
        limit (int): Maximum number of results (default: 100)
        project_id (str): PostHog project ID (optional, uses profile default)

    Returns:
        ok (bool): Success status
        data (dict): List of feature flags
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    host = _get_host(profile)
    project_id = _get_project_id(profile, params)

    active = params.get("active")
    limit = params.get("limit", 100)

    # Build query parameters
    query_params = {
        "limit": limit,
    }
    if active is not None:
        query_params["active"] = str(active).lower()

    url = f"{host}/api/projects/{project_id}/feature_flags/?{urlencode(query_params)}"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    result = _api_call(url, method="GET", headers=headers)

    if result.get("ok"):
        data = result.get("data", {})
        flags = data.get("results", [])
        formatted_flags = []
        for flag in flags:
            formatted_flags.append({
                "id": flag.get("id"),
                "key": flag.get("key"),
                "name": flag.get("name"),
                "active": flag.get("active"),
                "rollout_percentage": flag.get("rollout_percentage"),
                "filters": flag.get("filters"),
                "created_at": flag.get("created_at"),
            })
        return {
            "ok": True,
            "data": {
                "feature_flags": formatted_flags,
                "count": len(formatted_flags),
            }
        }
    return result


def get_feature_flag(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate a feature flag for a specific user.

    Params:
        key (str): Feature flag key (required)
        distinct_id (str): User identifier to evaluate for (required)
        person_properties (dict): Person properties for evaluation (optional)
        group_properties (dict): Group properties for evaluation (optional)
        project_id (str): PostHog project ID (optional, uses profile default)

    Returns:
        ok (bool): Success status
        data (dict): Feature flag value and evaluation details
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    host = _get_host(profile)

    key = params.get("key", "")
    distinct_id = params.get("distinct_id", "")
    person_properties = params.get("person_properties", {})
    group_properties = params.get("group_properties", {})

    if not key:
        return {"ok": False, "error": "key is required"}
    if not distinct_id:
        return {"ok": False, "error": "distinct_id is required"}

    # Use the decide endpoint for feature flag evaluation
    payload = {
        "api_key": api_key,
        "distinct_id": distinct_id,
    }

    if person_properties:
        payload["person_properties"] = person_properties
    if group_properties:
        payload["group_properties"] = group_properties

    url = f"{host}/decide/?v=3"
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    result = _api_call(url, method="POST", data=data, headers=headers)

    if result.get("ok"):
        response_data = result.get("data", {})
        feature_flags = response_data.get("featureFlags", {})
        flag_value = feature_flags.get(key)

        # Get feature flag payloads if available
        flag_payloads = response_data.get("featureFlagPayloads", {})
        flag_payload = flag_payloads.get(key)

        return {
            "ok": True,
            "data": {
                "key": key,
                "distinct_id": distinct_id,
                "value": flag_value,
                "payload": flag_payload,
                "enabled": flag_value is not None and flag_value is not False,
            }
        }
    return result


# =============================================================================
# Insights Actions
# =============================================================================

def list_insights(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List saved insights in the project.

    Params:
        saved (bool): Filter to only saved insights (default: True)
        limit (int): Maximum number of results (default: 100)
        project_id (str): PostHog project ID (optional, uses profile default)

    Returns:
        ok (bool): Success status
        data (dict): List of insights
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    host = _get_host(profile)
    project_id = _get_project_id(profile, params)

    saved = params.get("saved", True)
    limit = params.get("limit", 100)

    # Build query parameters
    query_params = {
        "limit": limit,
        "saved": str(saved).lower(),
    }

    url = f"{host}/api/projects/{project_id}/insights/?{urlencode(query_params)}"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    result = _api_call(url, method="GET", headers=headers)

    if result.get("ok"):
        data = result.get("data", {})
        insights = data.get("results", [])
        formatted_insights = []
        for insight in insights:
            formatted_insights.append({
                "id": insight.get("id"),
                "short_id": insight.get("short_id"),
                "name": insight.get("name"),
                "description": insight.get("description"),
                "filters": insight.get("filters"),
                "query": insight.get("query"),
                "created_at": insight.get("created_at"),
                "last_modified_at": insight.get("last_modified_at"),
                "created_by": insight.get("created_by"),
            })
        return {
            "ok": True,
            "data": {
                "insights": formatted_insights,
                "count": len(formatted_insights),
                "next": data.get("next"),
                "previous": data.get("previous"),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "capture": capture,
    "identify": identify,
    "batch": batch,
    "get_persons": get_persons,
    "get_events": get_events,
    "list_feature_flags": list_feature_flags,
    "get_feature_flag": get_feature_flag,
    "list_insights": list_insights,
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
        logger.info(f"Executing posthog.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
