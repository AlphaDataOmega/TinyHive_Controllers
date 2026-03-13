"""
Amplitude Controller for TinyHive

A controller for Amplitude Analytics API.
Supports event tracking, user identification, batch operations,
data export, user activity queries, and analytics reports.

Method IDs:
  controller.amplitude.{profile}.track
  controller.amplitude.{profile}.identify
  controller.amplitude.{profile}.batch
  controller.amplitude.{profile}.export
  controller.amplitude.{profile}.get_user_activity
  controller.amplitude.{profile}.query_events
  controller.amplitude.{profile}.get_retention
  controller.amplitude.{profile}.get_funnel

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Basic profile:
{
    "api_key_env": "AMPLITUDE_API_KEY",
    "secret_key_env": "AMPLITUDE_SECRET_KEY"
}

With custom timeout:
{
    "api_key_env": "AMPLITUDE_API_KEY",
    "secret_key_env": "AMPLITUDE_SECRET_KEY",
    "timeout": 60
}

Required Permissions:
--------------------
- Track/Identify/Batch: API Key (HTTP API)
- Export/User Activity/Queries: API Key + Secret Key (Export/Dashboard API with Basic Auth)

API Endpoints:
-------------
- HTTP API (tracking): https://api2.amplitude.com/2
- Export API: https://amplitude.com/api/2

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

logger = logging.getLogger("tinyhive.controller.amplitude")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Amplitude API endpoints
HTTP_API_BASE = "https://api2.amplitude.com/2"
EXPORT_API_BASE = "https://amplitude.com/api/2"

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


def _get_api_key(profile: Dict[str, Any]) -> str:
    """Get API key from environment variable specified in profile."""
    env_var = profile.get("api_key_env", "AMPLITUDE_API_KEY")
    api_key = os.environ.get(env_var)
    if not api_key:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return api_key


def _get_secret_key(profile: Dict[str, Any]) -> str:
    """Get secret key from environment variable specified in profile."""
    env_var = profile.get("secret_key_env", "AMPLITUDE_SECRET_KEY")
    secret_key = os.environ.get(env_var)
    if not secret_key:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return secret_key


def _get_basic_auth_header(profile: Dict[str, Any]) -> str:
    """Get Basic Auth header for Export API (api_key:secret_key)."""
    api_key = _get_api_key(profile)
    secret_key = _get_secret_key(profile)
    credentials = f"{api_key}:{secret_key}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    url: str,
    method: str = "POST",
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an Amplitude API call.

    Returns:
        {"ok": True, "result": ...} on success
        {"ok": False, "error": ...} on failure
    """
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
                    return {"ok": True, "result": json.loads(response_body)}
                except json.JSONDecodeError:
                    return {"ok": True, "result": response_body}
            return {"ok": True, "result": {"success": True}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("error", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Amplitude API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Amplitude API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def track(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Track events via HTTP API V2.

    Params:
        events (list): Array of event objects (required)
            Each event should contain at minimum:
            - user_id (str) or device_id (str): User/device identifier
            - event_type (str): Name of the event
            Additional fields (all optional):
            - time (int): Timestamp in milliseconds
            - event_properties (dict): Event properties
            - user_properties (dict): User properties
            - app_version (str): App version
            - platform (str): Platform
            - os_name (str): OS name
            - os_version (str): OS version
            - device_brand (str): Device brand
            - device_manufacturer (str): Device manufacturer
            - device_model (str): Device model
            - carrier (str): Carrier
            - country (str): Country
            - region (str): Region
            - city (str): City
            - dma (str): DMA
            - language (str): Language
            - price (float): Price (for revenue events)
            - quantity (int): Quantity (for revenue events)
            - revenue (float): Revenue
            - productId (str): Product ID
            - revenueType (str): Revenue type
            - location_lat (float): Latitude
            - location_lng (float): Longitude
            - ip (str): IP address
            - idfa (str): IDFA
            - idfv (str): IDFV
            - adid (str): Android advertising ID
            - android_id (str): Android ID
            - event_id (int): Event ID for deduplication
            - session_id (int): Session ID
            - insert_id (str): Insert ID for deduplication

    Returns:
        {"ok": True, "result": {"code": 200, "events_ingested": N, ...}}
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        events = params.get("events")
        if not events:
            return {"ok": False, "error": "events is required"}
        if not isinstance(events, list):
            return {"ok": False, "error": "events must be a list"}

        # Validate each event has required fields
        for i, event in enumerate(events):
            if not isinstance(event, dict):
                return {"ok": False, "error": f"events[{i}] must be a dict"}
            if not event.get("user_id") and not event.get("device_id"):
                return {"ok": False, "error": f"events[{i}] must have user_id or device_id"}
            if not event.get("event_type"):
                return {"ok": False, "error": f"events[{i}] must have event_type"}

        payload = {
            "api_key": api_key,
            "events": events,
        }

        url = f"{HTTP_API_BASE}/httpapi"
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        return _api_call(url, method="POST", data=data, headers=headers, timeout=timeout)

    except Exception as e:
        logger.exception("track failed")
        return {"ok": False, "error": str(e)}


def identify(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Identify user properties via HTTP API V2.

    Params:
        user_id (str): User identifier (required unless device_id provided)
        device_id (str): Device identifier (required if user_id not provided)
        user_properties (dict): User properties to set (required)
            Supports Amplitude property operations:
            - $set: Set properties
            - $setOnce: Set only if not already set
            - $add: Increment numeric properties
            - $append: Append to array properties
            - $prepend: Prepend to array properties
            - $unset: Remove properties
            - $preInsert: Insert at beginning if not exists
            - $postInsert: Insert at end if not exists
            - $clearAll: Clear all user properties

    Returns:
        {"ok": True, "result": {"code": 200, ...}}
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        user_id = params.get("user_id")
        device_id = params.get("device_id")
        user_properties = params.get("user_properties")

        if not user_id and not device_id:
            return {"ok": False, "error": "Either user_id or device_id is required"}
        if not user_properties:
            return {"ok": False, "error": "user_properties is required"}

        identification = {
            "user_properties": user_properties,
        }
        if user_id:
            identification["user_id"] = user_id
        if device_id:
            identification["device_id"] = device_id

        payload = {
            "api_key": api_key,
            "identification": [identification],
        }

        url = f"{HTTP_API_BASE}/identify"
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        return _api_call(url, method="POST", data=data, headers=headers, timeout=timeout)

    except Exception as e:
        logger.exception("identify failed")
        return {"ok": False, "error": str(e)}


def batch(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send batch events via HTTP API V2.

    This is similar to track but optimized for high-volume event batching.
    The Batch API endpoint has higher rate limits.

    Params:
        events (list): Array of event objects (required)
            Same format as track action.
        options (dict): Optional settings
            - min_id_length (int): Minimum length for user_id/device_id

    Returns:
        {"ok": True, "result": {"code": 200, "events_ingested": N, ...}}
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        events = params.get("events")
        options = params.get("options", {})

        if not events:
            return {"ok": False, "error": "events is required"}
        if not isinstance(events, list):
            return {"ok": False, "error": "events must be a list"}

        # Validate each event
        for i, event in enumerate(events):
            if not isinstance(event, dict):
                return {"ok": False, "error": f"events[{i}] must be a dict"}
            if not event.get("user_id") and not event.get("device_id"):
                return {"ok": False, "error": f"events[{i}] must have user_id or device_id"}
            if not event.get("event_type"):
                return {"ok": False, "error": f"events[{i}] must have event_type"}

        payload = {
            "api_key": api_key,
            "events": events,
        }
        if options:
            payload["options"] = options

        url = f"{HTTP_API_BASE}/batch"
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        return _api_call(url, method="POST", data=data, headers=headers, timeout=timeout)

    except Exception as e:
        logger.exception("batch failed")
        return {"ok": False, "error": str(e)}


def export(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Export raw event data via Export API.

    Requires both API key and secret key (Basic Auth).

    Params:
        start (str): Start date/time in YYYYMMDDTHH format (required)
            Example: "20240101T00" for Jan 1, 2024 at midnight
        end (str): End date/time in YYYYMMDDTHH format (required)
            Example: "20240102T00" for Jan 2, 2024 at midnight

    Returns:
        {"ok": True, "result": {"events": [...], "count": N}}

    Note:
        The export API returns gzipped JSONL data. This action parses it
        and returns the events as a list.
    """
    try:
        profile = load_profile(profile_name)
        auth_header = _get_basic_auth_header(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        start = params.get("start")
        end = params.get("end")

        if not start:
            return {"ok": False, "error": "start is required (format: YYYYMMDDTHH)"}
        if not end:
            return {"ok": False, "error": "end is required (format: YYYYMMDDTHH)"}

        query_params = urlencode({"start": start, "end": end})
        url = f"{EXPORT_API_BASE}/export?{query_params}"
        headers = {"Authorization": auth_header}

        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=timeout) as response:
            # Response is gzipped JSONL
            import gzip
            response_data = response.read()

            # Try to decompress if gzipped
            try:
                decompressed = gzip.decompress(response_data)
                response_body = decompressed.decode("utf-8")
            except (gzip.BadGzipFile, OSError):
                # Not gzipped, use as-is
                response_body = response_data.decode("utf-8")

            # Parse JSONL
            events = []
            for line in response_body.strip().split("\n"):
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            return {"ok": True, "result": {"events": events, "count": len(events)}}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error("Export API error %d: %s", e.code, error_body[:500])
        return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("export failed")
        return {"ok": False, "error": str(e)}


def get_user_activity(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get user activity/events via Dashboard API.

    Requires both API key and secret key (Basic Auth).

    Params:
        user_id (str): User identifier (required)
        offset (int): Offset for pagination (optional, default: 0)
        limit (int): Maximum events to return (optional, default: 1000, max: 1000)

    Returns:
        {"ok": True, "result": {"events": [...], "userData": {...}}}
    """
    try:
        profile = load_profile(profile_name)
        auth_header = _get_basic_auth_header(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        user_id = params.get("user_id")
        offset = params.get("offset", 0)
        limit = params.get("limit", 1000)

        if not user_id:
            return {"ok": False, "error": "user_id is required"}

        query_params = urlencode({
            "user": user_id,
            "offset": offset,
            "limit": min(limit, 1000),
        })
        url = f"{EXPORT_API_BASE}/useractivity?{query_params}"
        headers = {"Authorization": auth_header}

        return _api_call(url, method="GET", headers=headers, timeout=timeout)

    except Exception as e:
        logger.exception("get_user_activity failed")
        return {"ok": False, "error": str(e)}


def query_events(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Query event counts/segmentation via Dashboard API.

    Requires both API key and secret key (Basic Auth).

    Params:
        event_type (str): Event name to query (required)
        start (str): Start date in YYYYMMDD format (required)
        end (str): End date in YYYYMMDD format (required)
        interval (int): Time interval (optional)
            -300000 = real-time
            1 = daily
            7 = weekly
            30 = monthly
        group_by (list): Properties to group by (optional)

    Returns:
        {"ok": True, "result": {"data": {...}, "xValues": [...], ...}}
    """
    try:
        profile = load_profile(profile_name)
        auth_header = _get_basic_auth_header(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        event_type = params.get("event_type")
        start = params.get("start")
        end = params.get("end")
        interval = params.get("interval", 1)
        group_by = params.get("group_by")

        if not event_type:
            return {"ok": False, "error": "event_type is required"}
        if not start:
            return {"ok": False, "error": "start is required (format: YYYYMMDD)"}
        if not end:
            return {"ok": False, "error": "end is required (format: YYYYMMDD)"}

        # Build event segmentation query
        e_param = json.dumps({"event_type": event_type})

        query = {
            "e": e_param,
            "start": start,
            "end": end,
            "i": interval,
        }
        if group_by:
            query["g"] = json.dumps(group_by)

        query_params = urlencode(query)
        url = f"{EXPORT_API_BASE}/events/segmentation?{query_params}"
        headers = {"Authorization": auth_header}

        return _api_call(url, method="GET", headers=headers, timeout=timeout)

    except Exception as e:
        logger.exception("query_events failed")
        return {"ok": False, "error": str(e)}


def get_retention(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get retention analysis via Dashboard API.

    Requires both API key and secret key (Basic Auth).

    Params:
        start (str): Start date in YYYYMMDD format (required)
        end (str): End date in YYYYMMDD format (required)
        retention_type (str): Type of retention (optional)
            - "retention" (default): Standard retention
            - "unbounded": Unbounded retention (any day after)
            - "bracket": N-day retention
        se (dict): Starting event (optional)
            - event_type (str): Event name
        re (dict): Return event (optional)
            - event_type (str): Event name
        rm (str): Retention metric (optional)
            - "bracket" for N-day retention
        rb (int): Retention bracket day (optional, for bracket retention)

    Returns:
        {"ok": True, "result": {"data": {...}, ...}}
    """
    try:
        profile = load_profile(profile_name)
        auth_header = _get_basic_auth_header(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        start = params.get("start")
        end = params.get("end")
        retention_type = params.get("retention_type", "retention")
        se = params.get("se")  # Starting event
        re = params.get("re")  # Return event
        rm = params.get("rm")  # Retention metric
        rb = params.get("rb")  # Retention bracket

        if not start:
            return {"ok": False, "error": "start is required (format: YYYYMMDD)"}
        if not end:
            return {"ok": False, "error": "end is required (format: YYYYMMDD)"}

        query = {
            "start": start,
            "end": end,
        }

        if se:
            query["se"] = json.dumps(se)
        if re:
            query["re"] = json.dumps(re)
        if rm:
            query["rm"] = rm
        if rb is not None:
            query["rb"] = rb

        query_params = urlencode(query)
        url = f"{EXPORT_API_BASE}/{retention_type}?{query_params}"
        headers = {"Authorization": auth_header}

        return _api_call(url, method="GET", headers=headers, timeout=timeout)

    except Exception as e:
        logger.exception("get_retention failed")
        return {"ok": False, "error": str(e)}


def get_funnel(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get funnel analysis via Dashboard API.

    Requires both API key and secret key (Basic Auth).

    Params:
        funnel_id (str): Funnel ID to query (required)
            Get funnel IDs from Amplitude dashboard or use list funnels API.
        start (str): Start date in YYYYMMDD format (required)
        end (str): End date in YYYYMMDD format (required)
        mode (str): Funnel mode (optional)
            - "unordered": Events can happen in any order
            - "ordered": Events must happen in sequence (default)
        n (str): Conversion window (optional)
            - "new": New users only
            - "active": Active users
        cs (int): Conversion window in seconds (optional)
        group_by (list): Properties to group by (optional)

    Returns:
        {"ok": True, "result": {"data": {...}, "events": [...], ...}}
    """
    try:
        profile = load_profile(profile_name)
        auth_header = _get_basic_auth_header(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        funnel_id = params.get("funnel_id")
        start = params.get("start")
        end = params.get("end")
        mode = params.get("mode")
        n = params.get("n")
        cs = params.get("cs")
        group_by = params.get("group_by")

        if not funnel_id:
            return {"ok": False, "error": "funnel_id is required"}
        if not start:
            return {"ok": False, "error": "start is required (format: YYYYMMDD)"}
        if not end:
            return {"ok": False, "error": "end is required (format: YYYYMMDD)"}

        query = {
            "start": start,
            "end": end,
        }

        if mode:
            query["mode"] = mode
        if n:
            query["n"] = n
        if cs is not None:
            query["cs"] = cs
        if group_by:
            query["g"] = json.dumps(group_by)

        query_params = urlencode(query)
        url = f"{EXPORT_API_BASE}/funnels/{funnel_id}?{query_params}"
        headers = {"Authorization": auth_header}

        return _api_call(url, method="GET", headers=headers, timeout=timeout)

    except Exception as e:
        logger.exception("get_funnel failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "track": track,
    "identify": identify,
    "batch": batch,
    "export": export,
    "get_user_activity": get_user_activity,
    "query_events": query_events,
    "get_retention": get_retention,
    "get_funnel": get_funnel,
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

    logger.info(f"Executing amplitude.{profile}.{action}")
    return ACTIONS[action](profile, params)
