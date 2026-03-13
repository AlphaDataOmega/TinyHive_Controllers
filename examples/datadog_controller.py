"""
Datadog Controller for TinyHive

A controller for Datadog monitoring and observability platform.
Supports metrics submission, monitors, events, logs, dashboards, and incidents.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "site": "datadoghq.com",  // or datadoghq.eu, us3.datadoghq.com, etc.
    "api_key_env": "DD_API_KEY",
    "app_key_env": "DD_APP_KEY"
}

Environment Variables:
---------------------
- DD_API_KEY: Datadog API key (required)
- DD_APP_KEY: Datadog Application key (required for most endpoints)

API Endpoints:
-------------
- v1: metrics, monitors, events, dashboards
- v2: logs, incidents

Dependencies:
------------
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

logger = logging.getLogger("tinyhive.controller.datadog")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

DEFAULT_TIMEOUT = 60


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


def _get_credentials(profile: Dict[str, Any]) -> tuple:
    """Get API key and App key from environment variables."""
    api_key_env = profile.get("api_key_env", "DD_API_KEY")
    app_key_env = profile.get("app_key_env", "DD_APP_KEY")

    api_key = os.environ.get(api_key_env)
    app_key = os.environ.get(app_key_env)

    if not api_key:
        raise ValueError(f"Missing API key: environment variable '{api_key_env}' not set")

    return api_key, app_key


def _get_base_url(profile: Dict[str, Any], version: str = "v1") -> str:
    """Get the base API URL for the given profile and API version."""
    site = profile.get("site", "datadoghq.com")
    return f"https://api.{site}/api/{version}"


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    profile: Dict[str, Any],
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    version: str = "v1",
    timeout: int = DEFAULT_TIMEOUT,
    require_app_key: bool = True
) -> Dict[str, Any]:
    """Make an authenticated Datadog API call."""
    api_key, app_key = _get_credentials(profile)

    if require_app_key and not app_key:
        app_key_env = profile.get("app_key_env", "DD_APP_KEY")
        return {"ok": False, "error": f"Missing App key: environment variable '{app_key_env}' not set"}

    base_url = _get_base_url(profile, version)
    url = f"{base_url}/{endpoint}"

    headers = {
        "Content-Type": "application/json",
        "DD-API-KEY": api_key,
    }
    if app_key:
        headers["DD-APPLICATION-KEY"] = app_key

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "data": json.loads(response_body)}
            return {"ok": True, "data": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("errors", [error_body[:500]])
            if isinstance(error_message, list):
                error_message = "; ".join(error_message)
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Datadog API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Datadog API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def submit_metrics(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Submit custom metrics to Datadog.

    Params:
        series (list): List of metric series to submit. Each series is a dict with:
            - metric (str): Metric name (required)
            - points (list): List of [timestamp, value] pairs (required)
            - type (str): Metric type: 'gauge', 'rate', 'count' (default: 'gauge')
            - tags (list): List of tags (optional)
            - host (str): Hostname (optional)
            - interval (int): Interval for rate/count metrics (optional)

    Example:
        {
            "series": [
                {
                    "metric": "custom.metric.name",
                    "points": [[1234567890, 42.0]],
                    "type": "gauge",
                    "tags": ["env:prod", "service:api"]
                }
            ]
        }
    """
    profile = load_profile(profile_name)

    series = params.get("series")
    if not series:
        return {"ok": False, "error": "series is required"}

    if not isinstance(series, list):
        return {"ok": False, "error": "series must be a list"}

    # Validate and normalize series
    normalized_series = []
    for s in series:
        if not s.get("metric"):
            return {"ok": False, "error": "Each series must have a 'metric' name"}
        if not s.get("points"):
            return {"ok": False, "error": "Each series must have 'points'"}

        normalized = {
            "metric": s["metric"],
            "points": s["points"],
            "type": s.get("type", "gauge"),
        }
        if s.get("tags"):
            normalized["tags"] = s["tags"]
        if s.get("host"):
            normalized["host"] = s["host"]
        if s.get("interval"):
            normalized["interval"] = s["interval"]

        normalized_series.append(normalized)

    payload = {"series": normalized_series}

    # Metrics submission only requires API key, not App key
    result = _api_call(profile, "series", method="POST", data=payload, require_app_key=False)

    if result.get("ok"):
        return {"ok": True, "result": {"submitted": len(normalized_series)}}
    return result


def query_metrics(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Query time series data from Datadog.

    Params:
        query (str): Metrics query string (required)
            Example: "avg:system.cpu.user{host:myhost}"
        from_ts (int): Start timestamp in seconds (required)
        to_ts (int): End timestamp in seconds (required)

    Returns:
        Time series data with points and metadata.
    """
    profile = load_profile(profile_name)

    query = params.get("query")
    from_ts = params.get("from_ts") or params.get("from")
    to_ts = params.get("to_ts") or params.get("to")

    if not query:
        return {"ok": False, "error": "query is required"}
    if from_ts is None:
        return {"ok": False, "error": "from_ts is required"}
    if to_ts is None:
        return {"ok": False, "error": "to_ts is required"}

    endpoint = f"query?from={int(from_ts)}&to={int(to_ts)}&query={query}"

    result = _api_call(profile, endpoint, method="GET")

    if result.get("ok") and "data" in result:
        data = result["data"]
        series = data.get("series", [])
        return {
            "ok": True,
            "result": {
                "status": data.get("status"),
                "series": [
                    {
                        "metric": s.get("metric"),
                        "display_name": s.get("display_name"),
                        "scope": s.get("scope"),
                        "pointlist": s.get("pointlist", []),
                        "unit": s.get("unit"),
                    }
                    for s in series
                ],
                "from_date": data.get("from_date"),
                "to_date": data.get("to_date"),
            }
        }
    return result


def create_monitor(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a monitor (alert) in Datadog.

    Params:
        name (str): Monitor name (required)
        type (str): Monitor type (required). Common types:
            - 'metric alert': Alert on metric threshold
            - 'query alert': Alert on query result
            - 'service check': Alert on service check status
            - 'event alert': Alert on events
            - 'log alert': Alert on log query
        query (str): Monitor query (required)
            Example: "avg(last_5m):avg:system.cpu.user{*} > 80"
        message (str): Notification message (required)
        tags (list): List of tags (optional)
        priority (int): Priority 1-5 (optional)
        options (dict): Additional options (optional)
            - thresholds: {"critical": 90, "warning": 80}
            - notify_no_data: true/false
            - renotify_interval: minutes
            - escalation_message: string

    Returns:
        Created monitor details including ID.
    """
    profile = load_profile(profile_name)

    name = params.get("name")
    monitor_type = params.get("type")
    query = params.get("query")
    message = params.get("message")

    if not name:
        return {"ok": False, "error": "name is required"}
    if not monitor_type:
        return {"ok": False, "error": "type is required"}
    if not query:
        return {"ok": False, "error": "query is required"}
    if not message:
        return {"ok": False, "error": "message is required"}

    payload = {
        "name": name,
        "type": monitor_type,
        "query": query,
        "message": message,
    }

    if params.get("tags"):
        payload["tags"] = params["tags"]
    if params.get("priority"):
        payload["priority"] = params["priority"]
    if params.get("options"):
        payload["options"] = params["options"]

    result = _api_call(profile, "monitor", method="POST", data=payload)

    if result.get("ok") and "data" in result:
        data = result["data"]
        return {
            "ok": True,
            "result": {
                "id": data.get("id"),
                "name": data.get("name"),
                "type": data.get("type"),
                "query": data.get("query"),
                "overall_state": data.get("overall_state"),
                "created": data.get("created"),
            }
        }
    return result


def list_monitors(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List monitors in Datadog.

    Params:
        name (str): Filter by monitor name (optional)
        tags (list): Filter by tags (optional)
        page (int): Page number for pagination (optional, default: 0)
        page_size (int): Number of results per page (optional, default: 100)

    Returns:
        List of monitors matching the filters.
    """
    profile = load_profile(profile_name)

    query_params = []

    if params.get("name"):
        query_params.append(f"name={params['name']}")
    if params.get("tags"):
        tags = params["tags"]
        if isinstance(tags, list):
            tags = ",".join(tags)
        query_params.append(f"tags={tags}")
    if params.get("page"):
        query_params.append(f"page={params['page']}")
    if params.get("page_size"):
        query_params.append(f"page_size={params['page_size']}")

    endpoint = "monitor"
    if query_params:
        endpoint += "?" + "&".join(query_params)

    result = _api_call(profile, endpoint, method="GET")

    if result.get("ok") and "data" in result:
        monitors = result["data"]
        if not isinstance(monitors, list):
            monitors = [monitors] if monitors else []
        return {
            "ok": True,
            "result": {
                "monitors": [
                    {
                        "id": m.get("id"),
                        "name": m.get("name"),
                        "type": m.get("type"),
                        "query": m.get("query"),
                        "overall_state": m.get("overall_state"),
                        "tags": m.get("tags", []),
                        "created": m.get("created"),
                        "modified": m.get("modified"),
                    }
                    for m in monitors
                ],
                "count": len(monitors),
            }
        }
    return result


def create_event(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post an event to Datadog.

    Params:
        title (str): Event title (required)
        text (str): Event body/description (required)
        tags (list): List of tags (optional)
        alert_type (str): Event severity (optional)
            - 'error', 'warning', 'info', 'success', 'user_update',
              'recommendation', 'snapshot'
        priority (str): Event priority (optional): 'normal' or 'low'
        host (str): Hostname to associate (optional)
        aggregation_key (str): Key to group events (optional)
        source_type_name (str): Source type (optional)
        date_happened (int): Unix timestamp (optional, default: now)

    Returns:
        Created event details including ID.
    """
    profile = load_profile(profile_name)

    title = params.get("title")
    text = params.get("text")

    if not title:
        return {"ok": False, "error": "title is required"}
    if not text:
        return {"ok": False, "error": "text is required"}

    payload = {
        "title": title,
        "text": text,
    }

    if params.get("tags"):
        payload["tags"] = params["tags"]
    if params.get("alert_type"):
        payload["alert_type"] = params["alert_type"]
    if params.get("priority"):
        payload["priority"] = params["priority"]
    if params.get("host"):
        payload["host"] = params["host"]
    if params.get("aggregation_key"):
        payload["aggregation_key"] = params["aggregation_key"]
    if params.get("source_type_name"):
        payload["source_type_name"] = params["source_type_name"]
    if params.get("date_happened"):
        payload["date_happened"] = params["date_happened"]

    # Events only require API key
    result = _api_call(profile, "events", method="POST", data=payload, require_app_key=False)

    if result.get("ok") and "data" in result:
        data = result["data"]
        event = data.get("event", data)
        return {
            "ok": True,
            "result": {
                "id": event.get("id"),
                "title": event.get("title"),
                "url": event.get("url"),
                "status": "created",
            }
        }
    return result


def search_logs(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search logs in Datadog.

    Params:
        query (str): Log search query (required)
            Example: "service:myapp status:error"
        from_ts (int/str): Start time - Unix timestamp or ISO string (required)
        to_ts (int/str): End time - Unix timestamp or ISO string (required)
        limit (int): Maximum logs to return (optional, default: 50, max: 1000)
        sort (str): Sort order (optional): 'asc' or 'desc' (default: 'desc')
        indexes (list): Log indexes to search (optional)

    Returns:
        List of matching log entries.
    """
    profile = load_profile(profile_name)

    query = params.get("query")
    from_ts = params.get("from_ts") or params.get("from")
    to_ts = params.get("to_ts") or params.get("to")

    if not query:
        return {"ok": False, "error": "query is required"}
    if from_ts is None:
        return {"ok": False, "error": "from_ts is required"}
    if to_ts is None:
        return {"ok": False, "error": "to_ts is required"}

    # Convert timestamps to ISO format if they're integers
    if isinstance(from_ts, (int, float)):
        from datetime import datetime, timezone
        from_ts = datetime.fromtimestamp(from_ts, tz=timezone.utc).isoformat()
    if isinstance(to_ts, (int, float)):
        from datetime import datetime, timezone
        to_ts = datetime.fromtimestamp(to_ts, tz=timezone.utc).isoformat()

    payload = {
        "filter": {
            "query": query,
            "from": from_ts,
            "to": to_ts,
        },
        "page": {
            "limit": min(params.get("limit", 50), 1000),
        }
    }

    if params.get("sort"):
        payload["sort"] = params["sort"]
    if params.get("indexes"):
        payload["filter"]["indexes"] = params["indexes"]

    # Logs search uses v2 API
    result = _api_call(profile, "logs/events/search", method="POST", data=payload, version="v2")

    if result.get("ok") and "data" in result:
        data = result["data"]
        logs = data.get("data", [])
        return {
            "ok": True,
            "result": {
                "logs": [
                    {
                        "id": log.get("id"),
                        "timestamp": log.get("attributes", {}).get("timestamp"),
                        "status": log.get("attributes", {}).get("status"),
                        "service": log.get("attributes", {}).get("service"),
                        "host": log.get("attributes", {}).get("host"),
                        "message": log.get("attributes", {}).get("message"),
                        "tags": log.get("attributes", {}).get("tags", []),
                    }
                    for log in logs
                ],
                "count": len(logs),
            }
        }
    return result


def list_dashboards(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List dashboards in Datadog.

    Params:
        filter_shared (bool): Filter to only shared dashboards (optional)
        filter_deleted (bool): Include deleted dashboards (optional)
        count (int): Number of dashboards to return (optional)
        start (int): Starting index for pagination (optional)

    Returns:
        List of dashboards with basic info.
    """
    profile = load_profile(profile_name)

    query_params = []

    if params.get("filter_shared") is not None:
        query_params.append(f"filter[shared]={str(params['filter_shared']).lower()}")
    if params.get("filter_deleted") is not None:
        query_params.append(f"filter[deleted]={str(params['filter_deleted']).lower()}")
    if params.get("count"):
        query_params.append(f"count={params['count']}")
    if params.get("start"):
        query_params.append(f"start={params['start']}")

    endpoint = "dashboard"
    if query_params:
        endpoint += "?" + "&".join(query_params)

    result = _api_call(profile, endpoint, method="GET")

    if result.get("ok") and "data" in result:
        data = result["data"]
        dashboards = data.get("dashboards", [])
        return {
            "ok": True,
            "result": {
                "dashboards": [
                    {
                        "id": d.get("id"),
                        "title": d.get("title"),
                        "description": d.get("description"),
                        "layout_type": d.get("layout_type"),
                        "url": d.get("url"),
                        "author_handle": d.get("author_handle"),
                        "created_at": d.get("created_at"),
                        "modified_at": d.get("modified_at"),
                        "is_read_only": d.get("is_read_only"),
                    }
                    for d in dashboards
                ],
                "count": len(dashboards),
            }
        }
    return result


def create_incident(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an incident in Datadog.

    Params:
        title (str): Incident title (required)
        customer_impact (dict): Customer impact details (required)
            - customer_impacted (bool): Whether customers are impacted
            - customer_impact_scope (str): Scope of impact (optional)
            - customer_impact_start (int): Start timestamp (optional)
            - customer_impact_end (int): End timestamp (optional)
        severity (str): Incident severity (optional)
            - 'SEV-1', 'SEV-2', 'SEV-3', 'SEV-4', 'SEV-5', 'UNKNOWN'
        fields (dict): Custom fields (optional)
        notification_handles (list): Notification targets (optional)

    Returns:
        Created incident details including ID.

    Note:
        Requires Datadog Incident Management feature.
    """
    profile = load_profile(profile_name)

    title = params.get("title")
    customer_impact = params.get("customer_impact")

    if not title:
        return {"ok": False, "error": "title is required"}
    if not customer_impact:
        return {"ok": False, "error": "customer_impact is required"}
    if "customer_impacted" not in customer_impact:
        return {"ok": False, "error": "customer_impact.customer_impacted is required"}

    # Build incident payload using v2 API structure
    attributes = {
        "title": title,
        "customer_impacted": customer_impact.get("customer_impacted", False),
    }

    if customer_impact.get("customer_impact_scope"):
        attributes["customer_impact_scope"] = customer_impact["customer_impact_scope"]
    if customer_impact.get("customer_impact_start"):
        attributes["customer_impact_start"] = customer_impact["customer_impact_start"]
    if customer_impact.get("customer_impact_end"):
        attributes["customer_impact_end"] = customer_impact["customer_impact_end"]

    if params.get("severity"):
        attributes["fields"] = {
            "severity": {
                "type": "dropdown",
                "value": params["severity"]
            }
        }

    if params.get("fields"):
        if "fields" not in attributes:
            attributes["fields"] = {}
        attributes["fields"].update(params["fields"])

    if params.get("notification_handles"):
        attributes["notification_handles"] = params["notification_handles"]

    payload = {
        "data": {
            "type": "incidents",
            "attributes": attributes,
        }
    }

    # Incidents use v2 API
    result = _api_call(profile, "incidents", method="POST", data=payload, version="v2")

    if result.get("ok") and "data" in result:
        data = result["data"].get("data", result["data"])
        attrs = data.get("attributes", {})
        return {
            "ok": True,
            "result": {
                "id": data.get("id"),
                "title": attrs.get("title"),
                "status": attrs.get("status"),
                "severity": attrs.get("severity"),
                "customer_impacted": attrs.get("customer_impacted"),
                "created": attrs.get("created"),
                "public_id": attrs.get("public_id"),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "submit_metrics": submit_metrics,
    "query_metrics": query_metrics,
    "create_monitor": create_monitor,
    "list_monitors": list_monitors,
    "create_event": create_event,
    "search_logs": search_logs,
    "list_dashboards": list_dashboards,
    "create_incident": create_incident,
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

    logger.info(f"Executing datadog.{profile}.{action}")
    return ACTIONS[action](profile, params)
