"""
Prometheus Controller for TinyHive

A controller for interacting with Prometheus HTTP API.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Basic profile (no auth):
{
    "prometheus_url": "http://localhost:9090"
}

Profile with basic auth (credentials from environment):
{
    "prometheus_url": "https://prometheus.example.com",
    "basic_auth_user_env": "PROMETHEUS_USER",
    "basic_auth_password_env": "PROMETHEUS_PASSWORD"
}

Method IDs:
  controller.prometheus.{profile}.query
  controller.prometheus.{profile}.query_range
  controller.prometheus.{profile}.series
  controller.prometheus.{profile}.labels
  controller.prometheus.{profile}.label_values
  controller.prometheus.{profile}.targets
  controller.prometheus.{profile}.rules
  controller.prometheus.{profile}.alerts

Dependencies:
------------
None (standard library only)
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.prometheus")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

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


# =============================================================================
# HTTP Helpers
# =============================================================================

def _get_auth_header(profile: Dict[str, Any]) -> Optional[str]:
    """Get basic auth header if configured in profile."""
    user_env = profile.get("basic_auth_user_env")
    password_env = profile.get("basic_auth_password_env")

    if not user_env or not password_env:
        return None

    user = os.environ.get(user_env)
    password = os.environ.get(password_env)

    if not user or not password:
        return None

    credentials = f"{user}:{password}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


def _api_call(
    profile: Dict[str, Any],
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make a Prometheus API call."""
    prometheus_url = profile.get("prometheus_url", "").rstrip("/")
    if not prometheus_url:
        return {"ok": False, "error": "prometheus_url not configured in profile"}

    url = f"{prometheus_url}/api/v1/{endpoint}"

    if params:
        # Filter out None values and convert lists for match[] parameter
        query_params = []
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, list):
                # Handle match[] which can appear multiple times
                for v in value:
                    query_params.append((key, str(v)))
            else:
                query_params.append((key, str(value)))

        if query_params:
            url += "?" + urlencode(query_params)

    headers = {
        "Accept": "application/json",
    }

    auth_header = _get_auth_header(profile)
    if auth_header:
        headers["Authorization"] = auth_header

    try:
        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            data = json.loads(response_body)

            # Prometheus API returns {"status": "success", "data": ...}
            if data.get("status") == "success":
                return {"ok": True, "data": data.get("data")}
            else:
                error_type = data.get("errorType", "unknown")
                error_msg = data.get("error", "Unknown error")
                return {"ok": False, "error": f"{error_type}: {error_msg}"}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_msg = error_data.get("error", error_body[:500])
        except json.JSONDecodeError:
            error_msg = error_body[:500]
        logger.error("Prometheus API error %d: %s", e.code, error_msg)
        return {"ok": False, "error": f"HTTP {e.code}: {error_msg}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Prometheus API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def query(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute an instant query.

    Prometheus API: GET /api/v1/query

    Params:
        query (str): PromQL query expression (required)
        time (str): Evaluation timestamp (RFC3339 or Unix timestamp, optional)
        timeout (str): Evaluation timeout (optional)

    Returns:
        {"ok": True, "data": {"resultType": "...", "result": [...]}}
    """
    profile = load_profile(profile_name)

    prom_query = params.get("query")
    if not prom_query:
        return {"ok": False, "error": "query parameter is required"}

    api_params = {
        "query": prom_query,
        "time": params.get("time"),
        "timeout": params.get("timeout"),
    }

    return _api_call(profile, "query", api_params)


def query_range(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a range query.

    Prometheus API: GET /api/v1/query_range

    Params:
        query (str): PromQL query expression (required)
        start (str): Start timestamp (RFC3339 or Unix timestamp, required)
        end (str): End timestamp (RFC3339 or Unix timestamp, required)
        step (str): Query resolution step (duration or float seconds, required)
        timeout (str): Evaluation timeout (optional)

    Returns:
        {"ok": True, "data": {"resultType": "matrix", "result": [...]}}
    """
    profile = load_profile(profile_name)

    prom_query = params.get("query")
    start = params.get("start")
    end = params.get("end")
    step = params.get("step")

    if not prom_query:
        return {"ok": False, "error": "query parameter is required"}
    if not start:
        return {"ok": False, "error": "start parameter is required"}
    if not end:
        return {"ok": False, "error": "end parameter is required"}
    if not step:
        return {"ok": False, "error": "step parameter is required"}

    api_params = {
        "query": prom_query,
        "start": start,
        "end": end,
        "step": step,
        "timeout": params.get("timeout"),
    }

    return _api_call(profile, "query_range", api_params)


def series(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Find series by label matchers.

    Prometheus API: GET /api/v1/series

    Params:
        match (list[str]): Series selector(s) (required, at least one)
        start (str): Start timestamp (optional)
        end (str): End timestamp (optional)

    Returns:
        {"ok": True, "data": [{"__name__": "...", "label": "value"}, ...]}
    """
    profile = load_profile(profile_name)

    match = params.get("match")
    if not match:
        return {"ok": False, "error": "match parameter is required (list of selectors)"}

    # Ensure match is a list
    if isinstance(match, str):
        match = [match]

    api_params = {
        "match[]": match,
        "start": params.get("start"),
        "end": params.get("end"),
    }

    return _api_call(profile, "series", api_params)


def labels(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get label names.

    Prometheus API: GET /api/v1/labels

    Params:
        start (str): Start timestamp (optional)
        end (str): End timestamp (optional)
        match (list[str]): Series selector(s) to filter labels (optional)

    Returns:
        {"ok": True, "data": ["__name__", "instance", "job", ...]}
    """
    profile = load_profile(profile_name)

    match = params.get("match")
    if isinstance(match, str):
        match = [match]

    api_params = {
        "start": params.get("start"),
        "end": params.get("end"),
    }

    if match:
        api_params["match[]"] = match

    return _api_call(profile, "labels", api_params)


def label_values(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get values for a specific label.

    Prometheus API: GET /api/v1/label/<label_name>/values

    Params:
        label_name (str): Label name to get values for (required)
        start (str): Start timestamp (optional)
        end (str): End timestamp (optional)
        match (list[str]): Series selector(s) to filter values (optional)

    Returns:
        {"ok": True, "data": ["value1", "value2", ...]}
    """
    profile = load_profile(profile_name)

    label_name = params.get("label_name")
    if not label_name:
        return {"ok": False, "error": "label_name parameter is required"}

    match = params.get("match")
    if isinstance(match, str):
        match = [match]

    api_params = {
        "start": params.get("start"),
        "end": params.get("end"),
    }

    if match:
        api_params["match[]"] = match

    endpoint = f"label/{label_name}/values"
    return _api_call(profile, endpoint, api_params)


def targets(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get current scrape targets.

    Prometheus API: GET /api/v1/targets

    Params:
        state (str): Filter by target state: active, dropped, any (optional)

    Returns:
        {"ok": True, "data": {"activeTargets": [...], "droppedTargets": [...]}}
    """
    profile = load_profile(profile_name)

    api_params = {
        "state": params.get("state"),
    }

    return _api_call(profile, "targets", api_params)


def rules(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get alerting and recording rules.

    Prometheus API: GET /api/v1/rules

    Params:
        type (str): Filter by rule type: alert, record (optional)
        rule_name (list[str]): Filter by rule names (optional)
        rule_group (list[str]): Filter by rule group names (optional)
        file (list[str]): Filter by rule file names (optional)

    Returns:
        {"ok": True, "data": {"groups": [...]}}
    """
    profile = load_profile(profile_name)

    rule_name = params.get("rule_name")
    if isinstance(rule_name, str):
        rule_name = [rule_name]

    rule_group = params.get("rule_group")
    if isinstance(rule_group, str):
        rule_group = [rule_group]

    file = params.get("file")
    if isinstance(file, str):
        file = [file]

    api_params = {
        "type": params.get("type"),
    }

    if rule_name:
        api_params["rule_name[]"] = rule_name
    if rule_group:
        api_params["rule_group[]"] = rule_group
    if file:
        api_params["file[]"] = file

    return _api_call(profile, "rules", api_params)


def alerts(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get active alerts.

    Prometheus API: GET /api/v1/alerts

    Params:
        None required

    Returns:
        {"ok": True, "data": {"alerts": [...]}}
    """
    profile = load_profile(profile_name)

    return _api_call(profile, "alerts", {})


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "query": query,
    "query_range": query_range,
    "series": series,
    "labels": labels,
    "label_values": label_values,
    "targets": targets,
    "rules": rules,
    "alerts": alerts,
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

    try:
        logger.info(f"Executing prometheus.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
