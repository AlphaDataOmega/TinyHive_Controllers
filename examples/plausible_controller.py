"""Plausible Analytics Controller — Plausible Analytics integration via REST APIs.

This controller provides integration with Plausible Analytics for web analytics,
site management, and stats retrieval. Supports both Plausible Cloud and
self-hosted instances.

Method IDs:
  controller.plausible.{profile}.get_realtime_visitors
  controller.plausible.{profile}.get_aggregate
  controller.plausible.{profile}.get_timeseries
  controller.plausible.{profile}.get_breakdown
  controller.plausible.{profile}.list_sites
  controller.plausible.{profile}.create_site
  controller.plausible.{profile}.delete_site
  controller.plausible.{profile}.create_shared_link

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:

    {
      "api_key_env": "PLAUSIBLE_API_KEY",
      "base_url": "https://plausible.io",
      "site_id": "example.com"
    }

  - api_key_env: Environment variable containing the Plausible API key (required)
  - base_url: Plausible instance URL (default: https://plausible.io)
  - site_id: Default site ID/domain (optional, can be overridden per request)

API Endpoints:
  - Stats API: /api/v1/stats/...
  - Sites API: /api/v1/sites/...

Dependencies:
  - None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.plausible")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# Default Plausible cloud URL
DEFAULT_BASE_URL = "https://plausible.io"

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with Plausible configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available Plausible profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# Authentication Helpers
# =============================================================================

def _get_api_key(profile: Dict[str, Any]) -> str:
    """Get API key from environment variable."""
    api_key_env = profile.get("api_key_env", "PLAUSIBLE_API_KEY")
    api_key = os.environ.get(api_key_env, "")

    if not api_key:
        raise ValueError(
            f"Plausible API key not found. "
            f"Set environment variable: {api_key_env}"
        )
    return api_key


def _get_base_url(profile: Dict[str, Any]) -> str:
    """Get Plausible base URL from profile."""
    base_url = profile.get("base_url", DEFAULT_BASE_URL)
    # Remove trailing slash if present
    return base_url.rstrip("/")


def _get_site_id(profile: Dict[str, Any], params: Dict[str, Any]) -> str:
    """Get site ID from params or profile."""
    site_id = params.get("site_id", profile.get("site_id", ""))
    if not site_id:
        raise ValueError("site_id required (in profile or params)")
    return site_id


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    api_key: str,
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Plausible API call."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    if data:
        headers["Content-Type"] = "application/json"

    try:
        req = Request(url, data=data, headers=headers, method=method)
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
        logger.error("Plausible API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Plausible API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Stats API Actions
# =============================================================================

def get_realtime_visitors(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get current number of visitors on the site.

    Params:
        site_id (str): Domain of the site (optional, uses profile default)

    Returns:
        ok (bool): Success status
        data (dict): Current visitor count
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    base_url = _get_base_url(profile)
    site_id = _get_site_id(profile, params)

    url = f"{base_url}/api/v1/stats/realtime/visitors?site_id={quote(site_id, safe='')}"

    result = _api_call(api_key, url)

    if result.get("ok"):
        visitors = result.get("data")
        # Plausible returns just a number for realtime visitors
        if isinstance(visitors, int):
            return {
                "ok": True,
                "data": {
                    "site_id": site_id,
                    "visitors": visitors
                }
            }
        return {"ok": True, "data": {"site_id": site_id, "visitors": visitors}}
    return result


def get_aggregate(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get aggregate stats for a site.

    Params:
        site_id (str): Domain of the site (optional, uses profile default)
        period (str): Time period - '12mo', '6mo', 'month', '30d', '7d', 'day', 'custom'
            (default: '30d')
        date (str): Date for the period in YYYY-MM-DD format (optional)
        metrics (str): Comma-separated metrics - visitors, visits, pageviews, views_per_visit,
            bounce_rate, visit_duration, events, conversion_rate (default: 'visitors')
        filters (str): Filter expression (optional)
        compare (str): Compare with previous period - 'previous_period' (optional)

    Returns:
        ok (bool): Success status
        data (dict): Aggregate statistics
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    base_url = _get_base_url(profile)
    site_id = _get_site_id(profile, params)

    period = params.get("period", "30d")
    date = params.get("date")
    metrics = params.get("metrics", "visitors")
    filters = params.get("filters")
    compare = params.get("compare")

    # Build query parameters
    query_params = {
        "site_id": site_id,
        "period": period,
        "metrics": metrics,
    }

    if date:
        query_params["date"] = date
    if filters:
        query_params["filters"] = filters
    if compare:
        query_params["compare"] = compare

    url = f"{base_url}/api/v1/stats/aggregate?{urlencode(query_params)}"

    result = _api_call(api_key, url)

    if result.get("ok"):
        data = result.get("data", {})
        results = data.get("results", data)
        return {
            "ok": True,
            "data": {
                "site_id": site_id,
                "period": period,
                "results": results
            }
        }
    return result


def get_timeseries(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get timeseries stats for a site.

    Params:
        site_id (str): Domain of the site (optional, uses profile default)
        period (str): Time period - '12mo', '6mo', 'month', '30d', '7d', 'day', 'custom'
            (default: '30d')
        date (str): Date for the period in YYYY-MM-DD format (optional)
        metrics (str): Comma-separated metrics - visitors, visits, pageviews, views_per_visit,
            bounce_rate, visit_duration, events (default: 'visitors')
        interval (str): Interval for grouping - 'date', 'month' (default: 'date')
        filters (str): Filter expression (optional)

    Returns:
        ok (bool): Success status
        data (dict): Timeseries data points
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    base_url = _get_base_url(profile)
    site_id = _get_site_id(profile, params)

    period = params.get("period", "30d")
    date = params.get("date")
    metrics = params.get("metrics", "visitors")
    interval = params.get("interval", "date")
    filters = params.get("filters")

    # Build query parameters
    query_params = {
        "site_id": site_id,
        "period": period,
        "metrics": metrics,
        "interval": interval,
    }

    if date:
        query_params["date"] = date
    if filters:
        query_params["filters"] = filters

    url = f"{base_url}/api/v1/stats/timeseries?{urlencode(query_params)}"

    result = _api_call(api_key, url)

    if result.get("ok"):
        data = result.get("data", {})
        results = data.get("results", data)
        return {
            "ok": True,
            "data": {
                "site_id": site_id,
                "period": period,
                "interval": interval,
                "results": results
            }
        }
    return result


def get_breakdown(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get breakdown stats by a property.

    Params:
        site_id (str): Domain of the site (optional, uses profile default)
        period (str): Time period - '12mo', '6mo', 'month', '30d', '7d', 'day', 'custom'
            (default: '30d')
        date (str): Date for the period in YYYY-MM-DD format (optional)
        property (str): Property to break down by - visit:source, visit:referrer,
            visit:utm_medium, visit:utm_source, visit:utm_campaign, visit:utm_content,
            visit:utm_term, visit:device, visit:browser, visit:browser_version, visit:os,
            visit:os_version, visit:country, visit:region, visit:city, event:page,
            event:hostname, event:name, event:props:* (required)
        metrics (str): Comma-separated metrics - visitors, visits, pageviews, views_per_visit,
            bounce_rate, visit_duration, events (default: 'visitors')
        filters (str): Filter expression (optional)
        limit (int): Maximum results to return (default: 100)
        page (int): Page number for pagination (default: 1)

    Returns:
        ok (bool): Success status
        data (dict): Breakdown results
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    base_url = _get_base_url(profile)
    site_id = _get_site_id(profile, params)

    period = params.get("period", "30d")
    date = params.get("date")
    property_name = params.get("property", "")
    metrics = params.get("metrics", "visitors")
    filters = params.get("filters")
    limit = params.get("limit", 100)
    page = params.get("page", 1)

    if not property_name:
        return {"ok": False, "error": "property is required"}

    # Build query parameters
    query_params = {
        "site_id": site_id,
        "period": period,
        "property": property_name,
        "metrics": metrics,
        "limit": limit,
        "page": page,
    }

    if date:
        query_params["date"] = date
    if filters:
        query_params["filters"] = filters

    url = f"{base_url}/api/v1/stats/breakdown?{urlencode(query_params)}"

    result = _api_call(api_key, url)

    if result.get("ok"):
        data = result.get("data", {})
        results = data.get("results", data)
        return {
            "ok": True,
            "data": {
                "site_id": site_id,
                "period": period,
                "property": property_name,
                "results": results
            }
        }
    return result


# =============================================================================
# Sites API Actions
# =============================================================================

def list_sites(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all sites the API key has access to.

    Params:
        None

    Returns:
        ok (bool): Success status
        data (dict): List of sites
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    base_url = _get_base_url(profile)

    url = f"{base_url}/api/v1/sites"

    result = _api_call(api_key, url)

    if result.get("ok"):
        data = result.get("data", {})
        sites = data.get("sites", data if isinstance(data, list) else [])
        return {
            "ok": True,
            "data": {
                "sites": sites,
                "count": len(sites)
            }
        }
    return result


def create_site(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new site in Plausible.

    Params:
        domain (str): Domain name for the site (required)
        timezone (str): Timezone for the site in TZ database format
            (default: 'Etc/UTC')

    Returns:
        ok (bool): Success status
        data (dict): Created site details
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    base_url = _get_base_url(profile)

    domain = params.get("domain", "")
    timezone = params.get("timezone", "Etc/UTC")

    if not domain:
        return {"ok": False, "error": "domain is required"}

    payload = {
        "domain": domain,
        "timezone": timezone,
    }

    url = f"{base_url}/api/v1/sites"
    data = json.dumps(payload).encode("utf-8")

    result = _api_call(api_key, url, method="POST", data=data)

    if result.get("ok"):
        site_data = result.get("data", {})
        return {
            "ok": True,
            "data": {
                "domain": site_data.get("domain", domain),
                "timezone": site_data.get("timezone", timezone),
                "created": True
            }
        }
    return result


def delete_site(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a site from Plausible.

    Params:
        site_id (str): Domain of the site to delete (required)

    Returns:
        ok (bool): Success status
        data (dict): Deletion confirmation
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    base_url = _get_base_url(profile)

    site_id = params.get("site_id", "")
    if not site_id:
        return {"ok": False, "error": "site_id is required"}

    url = f"{base_url}/api/v1/sites/{quote(site_id, safe='')}"

    result = _api_call(api_key, url, method="DELETE")

    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "site_id": site_id,
                "deleted": True
            }
        }
    return result


def create_shared_link(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a shared dashboard link for a site.

    Params:
        site_id (str): Domain of the site (optional, uses profile default)
        name (str): Name for the shared link (required)

    Returns:
        ok (bool): Success status
        data (dict): Shared link details including URL
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    base_url = _get_base_url(profile)
    site_id = _get_site_id(profile, params)

    name = params.get("name", "")
    if not name:
        return {"ok": False, "error": "name is required"}

    payload = {
        "name": name,
    }

    url = f"{base_url}/api/v1/sites/shared-links?site_id={quote(site_id, safe='')}"
    data = json.dumps(payload).encode("utf-8")

    result = _api_call(api_key, url, method="PUT", data=data)

    if result.get("ok"):
        link_data = result.get("data", {})
        return {
            "ok": True,
            "data": {
                "site_id": site_id,
                "name": link_data.get("name", name),
                "url": link_data.get("url"),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "get_realtime_visitors": get_realtime_visitors,
    "get_aggregate": get_aggregate,
    "get_timeseries": get_timeseries,
    "get_breakdown": get_breakdown,
    "list_sites": list_sites,
    "create_site": create_site,
    "delete_site": delete_site,
    "create_shared_link": create_shared_link,
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
        logger.info(f"Executing plausible.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
