"""
PagerDuty Controller for TinyHive

A controller for interacting with the PagerDuty API to manage incidents,
services, on-call schedules, and events.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "token_env": "PAGERDUTY_TOKEN",  // Environment variable containing API token
    "default_from_email": "user@example.com",  // Required for incident creation
    "default_service_id": "PXXXXXX"  // Optional default service
}

Required Permissions:
--------------------
- create_incident: Requires write access to incidents
- list_incidents: Requires read access to incidents
- get_incident: Requires read access to incidents
- update_incident: Requires write access to incidents
- list_services: Requires read access to services
- list_oncalls: Requires read access to schedules
- create_event: Uses Events API v2 (routing key required)
- list_users: Requires read access to users

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
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.pagerduty")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# PagerDuty API endpoints
PAGERDUTY_API_BASE = "https://api.pagerduty.com"
PAGERDUTY_EVENTS_API = "https://events.pagerduty.com/v2/enqueue"

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
    """Get API token from environment variable specified in profile."""
    token_env = profile.get("token_env", "PAGERDUTY_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(f"Environment variable '{token_env}' not set")
    return token


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    extra_headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Make an authenticated PagerDuty API call."""
    url = f"{PAGERDUTY_API_BASE}{endpoint}"

    if params:
        # Filter out None values and build query string
        filtered_params = {k: v for k, v in params.items() if v is not None}
        if filtered_params:
            url += "?" + urlencode(filtered_params, doseq=True)

    headers = {
        "Authorization": f"Token token={token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.pagerduty+json;version=2",
    }
    if extra_headers:
        headers.update(extra_headers)

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
            errors = error_data.get("error", {}).get("errors", [])
            if errors:
                error_message = f"{error_message}: {', '.join(errors)}"
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("PagerDuty API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in PagerDuty API call")
        return {"ok": False, "error": str(e)}


def _events_api_call(
    routing_key: str,
    payload: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make a PagerDuty Events API v2 call."""
    headers = {
        "Content-Type": "application/json",
    }

    body = json.dumps(payload).encode("utf-8")

    try:
        req = Request(PAGERDUTY_EVENTS_API, data=body, headers=headers, method="POST")
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
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("PagerDuty Events API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in PagerDuty Events API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Incident Actions
# =============================================================================

def create_incident(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new incident.

    Params:
        title (str): Incident title (required)
        service_id (str): Service ID to create incident on (required, or use profile default)
        urgency (str): 'high' or 'low' (default: 'high')
        body (str): Incident body/details (optional)
        from_email (str): Email of user creating incident (required, or use profile default)
        escalation_policy_id (str): Escalation policy ID (optional)
        incident_key (str): Deduplication key (optional)
        priority_id (str): Priority ID (optional)
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        title = params.get("title")
        if not title:
            return {"ok": False, "error": "title is required"}

        service_id = params.get("service_id", profile.get("default_service_id"))
        if not service_id:
            return {"ok": False, "error": "service_id is required (in params or profile default)"}

        from_email = params.get("from_email", profile.get("default_from_email"))
        if not from_email:
            return {"ok": False, "error": "from_email is required (in params or profile default)"}

        incident_data: Dict[str, Any] = {
            "type": "incident",
            "title": title,
            "service": {
                "id": service_id,
                "type": "service_reference"
            },
            "urgency": params.get("urgency", "high"),
        }

        if params.get("body"):
            incident_data["body"] = {
                "type": "incident_body",
                "details": params["body"]
            }

        if params.get("escalation_policy_id"):
            incident_data["escalation_policy"] = {
                "id": params["escalation_policy_id"],
                "type": "escalation_policy_reference"
            }

        if params.get("incident_key"):
            incident_data["incident_key"] = params["incident_key"]

        if params.get("priority_id"):
            incident_data["priority"] = {
                "id": params["priority_id"],
                "type": "priority_reference"
            }

        result = _api_call(
            token,
            "/incidents",
            method="POST",
            data={"incident": incident_data},
            extra_headers={"From": from_email}
        )

        if result.get("ok") and "data" in result:
            incident = result["data"].get("incident", {})
            return {
                "ok": True,
                "result": {
                    "id": incident.get("id"),
                    "incident_number": incident.get("incident_number"),
                    "title": incident.get("title"),
                    "status": incident.get("status"),
                    "urgency": incident.get("urgency"),
                    "html_url": incident.get("html_url"),
                    "created_at": incident.get("created_at"),
                }
            }
        return result
    except Exception as e:
        logger.exception("create_incident failed")
        return {"ok": False, "error": str(e)}


def list_incidents(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List incidents.

    Params:
        statuses (list): Filter by statuses: 'triggered', 'acknowledged', 'resolved' (optional)
        urgencies (list): Filter by urgencies: 'high', 'low' (optional)
        since (str): Start date/time ISO8601 (optional)
        until (str): End date/time ISO8601 (optional)
        service_ids (list): Filter by service IDs (optional)
        user_ids (list): Filter by user IDs (optional)
        time_zone (str): Time zone for dates (default: 'UTC')
        sort_by (str): Sort field (default: 'created_at')
        limit (int): Max results (default: 25, max: 100)
        offset (int): Pagination offset (default: 0)
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        query_params: Dict[str, Any] = {}

        if params.get("statuses"):
            query_params["statuses[]"] = params["statuses"]
        if params.get("urgencies"):
            query_params["urgencies[]"] = params["urgencies"]
        if params.get("since"):
            query_params["since"] = params["since"]
        if params.get("until"):
            query_params["until"] = params["until"]
        if params.get("service_ids"):
            query_params["service_ids[]"] = params["service_ids"]
        if params.get("user_ids"):
            query_params["user_ids[]"] = params["user_ids"]
        if params.get("time_zone"):
            query_params["time_zone"] = params["time_zone"]
        if params.get("sort_by"):
            query_params["sort_by"] = params["sort_by"]

        query_params["limit"] = params.get("limit", 25)
        query_params["offset"] = params.get("offset", 0)

        result = _api_call(token, "/incidents", params=query_params)

        if result.get("ok") and "data" in result:
            incidents = result["data"].get("incidents", [])
            return {
                "ok": True,
                "result": {
                    "incidents": [
                        {
                            "id": inc.get("id"),
                            "incident_number": inc.get("incident_number"),
                            "title": inc.get("title"),
                            "status": inc.get("status"),
                            "urgency": inc.get("urgency"),
                            "html_url": inc.get("html_url"),
                            "created_at": inc.get("created_at"),
                            "service": {
                                "id": inc.get("service", {}).get("id"),
                                "summary": inc.get("service", {}).get("summary"),
                            },
                            "assignments": [
                                {
                                    "assignee_id": a.get("assignee", {}).get("id"),
                                    "assignee_name": a.get("assignee", {}).get("summary"),
                                }
                                for a in inc.get("assignments", [])
                            ],
                        }
                        for inc in incidents
                    ],
                    "total": result["data"].get("total", len(incidents)),
                    "more": result["data"].get("more", False),
                }
            }
        return result
    except Exception as e:
        logger.exception("list_incidents failed")
        return {"ok": False, "error": str(e)}


def get_incident(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get incident details.

    Params:
        incident_id (str): Incident ID (required)
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        incident_id = params.get("incident_id")
        if not incident_id:
            return {"ok": False, "error": "incident_id is required"}

        result = _api_call(token, f"/incidents/{incident_id}")

        if result.get("ok") and "data" in result:
            inc = result["data"].get("incident", {})
            return {
                "ok": True,
                "result": {
                    "id": inc.get("id"),
                    "incident_number": inc.get("incident_number"),
                    "title": inc.get("title"),
                    "description": inc.get("description"),
                    "status": inc.get("status"),
                    "urgency": inc.get("urgency"),
                    "priority": inc.get("priority"),
                    "html_url": inc.get("html_url"),
                    "created_at": inc.get("created_at"),
                    "last_status_change_at": inc.get("last_status_change_at"),
                    "resolved_at": inc.get("resolved_at"),
                    "service": {
                        "id": inc.get("service", {}).get("id"),
                        "summary": inc.get("service", {}).get("summary"),
                    },
                    "escalation_policy": {
                        "id": inc.get("escalation_policy", {}).get("id"),
                        "summary": inc.get("escalation_policy", {}).get("summary"),
                    },
                    "assignments": [
                        {
                            "assignee_id": a.get("assignee", {}).get("id"),
                            "assignee_name": a.get("assignee", {}).get("summary"),
                            "at": a.get("at"),
                        }
                        for a in inc.get("assignments", [])
                    ],
                    "acknowledgements": [
                        {
                            "acknowledger_id": a.get("acknowledger", {}).get("id"),
                            "acknowledger_name": a.get("acknowledger", {}).get("summary"),
                            "at": a.get("at"),
                        }
                        for a in inc.get("acknowledgements", [])
                    ],
                    "body": inc.get("body", {}).get("details"),
                    "incident_key": inc.get("incident_key"),
                }
            }
        return result
    except Exception as e:
        logger.exception("get_incident failed")
        return {"ok": False, "error": str(e)}


def update_incident(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an incident (e.g., acknowledge, resolve).

    Params:
        incident_id (str): Incident ID (required)
        status (str): New status: 'acknowledged' or 'resolved' (required)
        resolution (str): Resolution notes (optional, for resolved status)
        from_email (str): Email of user making update (required, or use profile default)
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        incident_id = params.get("incident_id")
        if not incident_id:
            return {"ok": False, "error": "incident_id is required"}

        status = params.get("status")
        if not status:
            return {"ok": False, "error": "status is required"}
        if status not in ("acknowledged", "resolved"):
            return {"ok": False, "error": "status must be 'acknowledged' or 'resolved'"}

        from_email = params.get("from_email", profile.get("default_from_email"))
        if not from_email:
            return {"ok": False, "error": "from_email is required (in params or profile default)"}

        incident_data: Dict[str, Any] = {
            "id": incident_id,
            "type": "incident_reference",
            "status": status,
        }

        if params.get("resolution") and status == "resolved":
            incident_data["resolution"] = params["resolution"]

        result = _api_call(
            token,
            f"/incidents/{incident_id}",
            method="PUT",
            data={"incident": incident_data},
            extra_headers={"From": from_email}
        )

        if result.get("ok") and "data" in result:
            inc = result["data"].get("incident", {})
            return {
                "ok": True,
                "result": {
                    "id": inc.get("id"),
                    "incident_number": inc.get("incident_number"),
                    "title": inc.get("title"),
                    "status": inc.get("status"),
                    "html_url": inc.get("html_url"),
                    "last_status_change_at": inc.get("last_status_change_at"),
                }
            }
        return result
    except Exception as e:
        logger.exception("update_incident failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Service Actions
# =============================================================================

def list_services(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List services.

    Params:
        query (str): Filter by name (optional)
        team_ids (list): Filter by team IDs (optional)
        time_zone (str): Time zone (default: 'UTC')
        sort_by (str): Sort field: 'name', 'id' (default: 'name')
        limit (int): Max results (default: 25, max: 100)
        offset (int): Pagination offset (default: 0)
        include (list): Additional data to include: 'escalation_policies', 'teams' (optional)
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        query_params: Dict[str, Any] = {}

        if params.get("query"):
            query_params["query"] = params["query"]
        if params.get("team_ids"):
            query_params["team_ids[]"] = params["team_ids"]
        if params.get("time_zone"):
            query_params["time_zone"] = params["time_zone"]
        if params.get("sort_by"):
            query_params["sort_by"] = params["sort_by"]
        if params.get("include"):
            query_params["include[]"] = params["include"]

        query_params["limit"] = params.get("limit", 25)
        query_params["offset"] = params.get("offset", 0)

        result = _api_call(token, "/services", params=query_params)

        if result.get("ok") and "data" in result:
            services = result["data"].get("services", [])
            return {
                "ok": True,
                "result": {
                    "services": [
                        {
                            "id": svc.get("id"),
                            "name": svc.get("name"),
                            "description": svc.get("description"),
                            "status": svc.get("status"),
                            "html_url": svc.get("html_url"),
                            "escalation_policy": {
                                "id": svc.get("escalation_policy", {}).get("id"),
                                "summary": svc.get("escalation_policy", {}).get("summary"),
                            },
                            "teams": [
                                {"id": t.get("id"), "summary": t.get("summary")}
                                for t in svc.get("teams", [])
                            ],
                            "created_at": svc.get("created_at"),
                        }
                        for svc in services
                    ],
                    "total": result["data"].get("total", len(services)),
                    "more": result["data"].get("more", False),
                }
            }
        return result
    except Exception as e:
        logger.exception("list_services failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# On-Call Actions
# =============================================================================

def list_oncalls(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List on-call users.

    Params:
        schedule_ids (list): Filter by schedule IDs (optional)
        user_ids (list): Filter by user IDs (optional)
        escalation_policy_ids (list): Filter by escalation policy IDs (optional)
        since (str): Start date/time ISO8601 (optional)
        until (str): End date/time ISO8601 (optional)
        time_zone (str): Time zone (default: 'UTC')
        earliest (bool): Return only the earliest on-call per schedule (default: False)
        limit (int): Max results (default: 25, max: 100)
        offset (int): Pagination offset (default: 0)
        include (list): Additional data: 'escalation_policies', 'schedules', 'users' (optional)
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        query_params: Dict[str, Any] = {}

        if params.get("schedule_ids"):
            query_params["schedule_ids[]"] = params["schedule_ids"]
        if params.get("user_ids"):
            query_params["user_ids[]"] = params["user_ids"]
        if params.get("escalation_policy_ids"):
            query_params["escalation_policy_ids[]"] = params["escalation_policy_ids"]
        if params.get("since"):
            query_params["since"] = params["since"]
        if params.get("until"):
            query_params["until"] = params["until"]
        if params.get("time_zone"):
            query_params["time_zone"] = params["time_zone"]
        if params.get("earliest"):
            query_params["earliest"] = "true"
        if params.get("include"):
            query_params["include[]"] = params["include"]

        query_params["limit"] = params.get("limit", 25)
        query_params["offset"] = params.get("offset", 0)

        result = _api_call(token, "/oncalls", params=query_params)

        if result.get("ok") and "data" in result:
            oncalls = result["data"].get("oncalls", [])
            return {
                "ok": True,
                "result": {
                    "oncalls": [
                        {
                            "user": {
                                "id": oc.get("user", {}).get("id"),
                                "name": oc.get("user", {}).get("summary"),
                                "email": oc.get("user", {}).get("email"),
                                "html_url": oc.get("user", {}).get("html_url"),
                            },
                            "schedule": {
                                "id": oc.get("schedule", {}).get("id"),
                                "summary": oc.get("schedule", {}).get("summary"),
                            } if oc.get("schedule") else None,
                            "escalation_policy": {
                                "id": oc.get("escalation_policy", {}).get("id"),
                                "summary": oc.get("escalation_policy", {}).get("summary"),
                            },
                            "escalation_level": oc.get("escalation_level"),
                            "start": oc.get("start"),
                            "end": oc.get("end"),
                        }
                        for oc in oncalls
                    ],
                    "total": result["data"].get("total", len(oncalls)),
                    "more": result["data"].get("more", False),
                }
            }
        return result
    except Exception as e:
        logger.exception("list_oncalls failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Events API Actions
# =============================================================================

def create_event(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send an event to PagerDuty Events API v2.

    Params:
        routing_key (str): Integration routing key (required)
        event_action (str): 'trigger', 'acknowledge', or 'resolve' (required)
        summary (str): Event summary (required for trigger)
        severity (str): 'critical', 'error', 'warning', or 'info' (required for trigger)
        source (str): Event source (optional, defaults to hostname)
        dedup_key (str): Deduplication key (optional for trigger, required for ack/resolve)
        timestamp (str): ISO8601 timestamp (optional)
        component (str): Component name (optional)
        group (str): Logical grouping (optional)
        class_type (str): Class/type of event (optional)
        custom_details (dict): Additional details (optional)
        images (list): List of image objects (optional)
        links (list): List of link objects (optional)
    """
    try:
        # Note: Events API doesn't use profile token, but we still load profile for config
        load_profile(profile_name)

        routing_key = params.get("routing_key")
        if not routing_key:
            return {"ok": False, "error": "routing_key is required"}

        event_action = params.get("event_action")
        if not event_action:
            return {"ok": False, "error": "event_action is required"}
        if event_action not in ("trigger", "acknowledge", "resolve"):
            return {"ok": False, "error": "event_action must be 'trigger', 'acknowledge', or 'resolve'"}

        payload: Dict[str, Any] = {
            "routing_key": routing_key,
            "event_action": event_action,
        }

        if event_action == "trigger":
            summary = params.get("summary")
            if not summary:
                return {"ok": False, "error": "summary is required for trigger events"}

            severity = params.get("severity")
            if not severity:
                return {"ok": False, "error": "severity is required for trigger events"}
            if severity not in ("critical", "error", "warning", "info"):
                return {"ok": False, "error": "severity must be 'critical', 'error', 'warning', or 'info'"}

            payload["payload"] = {
                "summary": summary,
                "severity": severity,
                "source": params.get("source", "tinyhive"),
            }

            if params.get("timestamp"):
                payload["payload"]["timestamp"] = params["timestamp"]
            if params.get("component"):
                payload["payload"]["component"] = params["component"]
            if params.get("group"):
                payload["payload"]["group"] = params["group"]
            if params.get("class_type"):
                payload["payload"]["class"] = params["class_type"]
            if params.get("custom_details"):
                payload["payload"]["custom_details"] = params["custom_details"]

            if params.get("images"):
                payload["images"] = params["images"]
            if params.get("links"):
                payload["links"] = params["links"]

        dedup_key = params.get("dedup_key")
        if dedup_key:
            payload["dedup_key"] = dedup_key
        elif event_action in ("acknowledge", "resolve"):
            return {"ok": False, "error": "dedup_key is required for acknowledge/resolve events"}

        result = _events_api_call(routing_key, payload)

        if result.get("ok") and "data" in result:
            return {
                "ok": True,
                "result": {
                    "status": result["data"].get("status"),
                    "message": result["data"].get("message"),
                    "dedup_key": result["data"].get("dedup_key"),
                }
            }
        return result
    except Exception as e:
        logger.exception("create_event failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# User Actions
# =============================================================================

def list_users(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List users.

    Params:
        query (str): Filter by name or email (optional)
        team_ids (list): Filter by team IDs (optional)
        include (list): Additional data: 'contact_methods', 'notification_rules', 'teams' (optional)
        limit (int): Max results (default: 25, max: 100)
        offset (int): Pagination offset (default: 0)
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        query_params: Dict[str, Any] = {}

        if params.get("query"):
            query_params["query"] = params["query"]
        if params.get("team_ids"):
            query_params["team_ids[]"] = params["team_ids"]
        if params.get("include"):
            query_params["include[]"] = params["include"]

        query_params["limit"] = params.get("limit", 25)
        query_params["offset"] = params.get("offset", 0)

        result = _api_call(token, "/users", params=query_params)

        if result.get("ok") and "data" in result:
            users = result["data"].get("users", [])
            return {
                "ok": True,
                "result": {
                    "users": [
                        {
                            "id": user.get("id"),
                            "name": user.get("name"),
                            "email": user.get("email"),
                            "role": user.get("role"),
                            "time_zone": user.get("time_zone"),
                            "html_url": user.get("html_url"),
                            "teams": [
                                {"id": t.get("id"), "summary": t.get("summary")}
                                for t in user.get("teams", [])
                            ],
                            "contact_methods": [
                                {
                                    "id": cm.get("id"),
                                    "type": cm.get("type"),
                                    "summary": cm.get("summary"),
                                }
                                for cm in user.get("contact_methods", [])
                            ] if user.get("contact_methods") else [],
                        }
                        for user in users
                    ],
                    "total": result["data"].get("total", len(users)),
                    "more": result["data"].get("more", False),
                }
            }
        return result
    except Exception as e:
        logger.exception("list_users failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "create_incident": create_incident,
    "list_incidents": list_incidents,
    "get_incident": get_incident,
    "update_incident": update_incident,
    "list_services": list_services,
    "list_oncalls": list_oncalls,
    "create_event": create_event,
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
        return {"ok": False, "error": f"Unknown action: {action}"}

    logger.info(f"Executing pagerduty.{profile}.{action}")
    return ACTIONS[action](profile, params)
