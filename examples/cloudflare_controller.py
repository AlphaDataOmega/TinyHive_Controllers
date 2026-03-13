"""
Cloudflare Controller for TinyHive

A controller for managing Cloudflare zones, DNS records, cache, and settings
via the Cloudflare API v4.

Method IDs:
  controller.cloudflare.{profile}.list_zones
  controller.cloudflare.{profile}.get_zone
  controller.cloudflare.{profile}.purge_cache
  controller.cloudflare.{profile}.create_dns_record
  controller.cloudflare.{profile}.update_dns_record
  controller.cloudflare.{profile}.delete_dns_record
  controller.cloudflare.{profile}.list_dns_records
  controller.cloudflare.{profile}.toggle_dev_mode
  controller.cloudflare.{profile}.get_analytics

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "token_env": "CLOUDFLARE_API_TOKEN",
    "account_id": "optional-account-id"
}

Required API Token Permissions:
------------------------------
- Zone Read (for list_zones, get_zone)
- Zone Settings Edit (for toggle_dev_mode)
- Cache Purge (for purge_cache)
- DNS Edit (for create/update/delete_dns_record)
- DNS Read (for list_dns_records)
- Analytics Read (for get_analytics)

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

logger = logging.getLogger("tinyhive.controller.cloudflare")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Cloudflare API base URL
CF_API_BASE = "https://api.cloudflare.com/client/v4"

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


def _get_api_token(profile: Dict[str, Any]) -> str:
    """Get the Cloudflare API token from environment."""
    token_env = profile.get("token_env", "CLOUDFLARE_API_TOKEN")
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
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated Cloudflare API call.

    Args:
        token: Cloudflare API token
        endpoint: API endpoint (e.g., "/zones")
        method: HTTP method
        data: JSON body data
        params: Query parameters
        timeout: Request timeout in seconds

    Returns:
        Dict with 'ok' status and 'result' or 'error'
    """
    url = f"{CF_API_BASE}{endpoint}"

    if params:
        # Filter out None values
        filtered_params = {k: v for k, v in params.items() if v is not None}
        if filtered_params:
            url += "?" + urlencode(filtered_params)

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
                # Cloudflare API returns {success: bool, result: ..., errors: [...]}
                if result.get("success"):
                    return {"ok": True, "result": result.get("result"), "result_info": result.get("result_info")}
                else:
                    errors = result.get("errors", [])
                    error_msg = "; ".join(e.get("message", str(e)) for e in errors)
                    return {"ok": False, "error": error_msg or "Unknown error"}
            return {"ok": True, "result": None}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            errors = error_data.get("errors", [])
            error_msg = "; ".join(err.get("message", str(err)) for err in errors)
        except json.JSONDecodeError:
            error_msg = error_body[:500]
        logger.error("Cloudflare API error %d: %s", e.code, error_msg)
        return {"ok": False, "error": f"HTTP {e.code}: {error_msg}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Cloudflare API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Zone Actions
# =============================================================================

def list_zones(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all zones/domains in the account.

    Params:
        name (str): Filter by zone name (optional)
        status (str): Filter by status: active, pending, initializing, moved, deleted (optional)
        per_page (int): Number of results per page, max 50 (default: 20)
        page (int): Page number (default: 1)

    Returns:
        List of zones with id, name, status, name_servers, etc.
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)

    query_params = {
        "name": params.get("name"),
        "status": params.get("status"),
        "per_page": params.get("per_page", 20),
        "page": params.get("page", 1),
    }

    result = _api_call(token, "/zones", params=query_params)

    if result.get("ok") and result.get("result"):
        zones = [
            {
                "id": z.get("id"),
                "name": z.get("name"),
                "status": z.get("status"),
                "paused": z.get("paused"),
                "type": z.get("type"),
                "name_servers": z.get("name_servers", []),
                "created_on": z.get("created_on"),
                "modified_on": z.get("modified_on"),
            }
            for z in result["result"]
        ]
        return {
            "ok": True,
            "data": {"zones": zones, "count": len(zones)},
            "result_info": result.get("result_info"),
        }
    return result


def get_zone(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a specific zone.

    Params:
        zone_id (str): The zone identifier (required)

    Returns:
        Zone details including id, name, status, settings, etc.
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)

    zone_id = params.get("zone_id")
    if not zone_id:
        return {"ok": False, "error": "zone_id is required"}

    result = _api_call(token, f"/zones/{zone_id}")

    if result.get("ok") and result.get("result"):
        z = result["result"]
        return {
            "ok": True,
            "data": {
                "id": z.get("id"),
                "name": z.get("name"),
                "status": z.get("status"),
                "paused": z.get("paused"),
                "type": z.get("type"),
                "development_mode": z.get("development_mode"),
                "name_servers": z.get("name_servers", []),
                "original_name_servers": z.get("original_name_servers", []),
                "created_on": z.get("created_on"),
                "modified_on": z.get("modified_on"),
                "plan": z.get("plan", {}).get("name"),
            },
        }
    return result


# =============================================================================
# Cache Actions
# =============================================================================

def purge_cache(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Purge cache for a zone.

    Params:
        zone_id (str): The zone identifier (required)
        purge_everything (bool): Purge all cached content (default: False)
        files (list): List of URLs to purge (optional, used if purge_everything is False)
        tags (list): List of cache tags to purge (optional)
        hosts (list): List of hosts to purge (optional)
        prefixes (list): List of URL prefixes to purge (optional)

    Returns:
        Purge operation result
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)

    zone_id = params.get("zone_id")
    if not zone_id:
        return {"ok": False, "error": "zone_id is required"}

    purge_everything = params.get("purge_everything", False)
    files = params.get("files")
    tags = params.get("tags")
    hosts = params.get("hosts")
    prefixes = params.get("prefixes")

    data: Dict[str, Any] = {}

    if purge_everything:
        data["purge_everything"] = True
    elif files:
        data["files"] = files
    elif tags:
        data["tags"] = tags
    elif hosts:
        data["hosts"] = hosts
    elif prefixes:
        data["prefixes"] = prefixes
    else:
        return {"ok": False, "error": "Must specify purge_everything=True, files, tags, hosts, or prefixes"}

    result = _api_call(token, f"/zones/{zone_id}/purge_cache", method="POST", data=data)

    if result.get("ok"):
        return {"ok": True, "data": {"purged": True, "id": result.get("result", {}).get("id")}}
    return result


# =============================================================================
# DNS Record Actions
# =============================================================================

def list_dns_records(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List DNS records for a zone.

    Params:
        zone_id (str): The zone identifier (required)
        type (str): Filter by record type: A, AAAA, CNAME, TXT, MX, etc. (optional)
        name (str): Filter by record name (optional)
        content (str): Filter by record content (optional)
        per_page (int): Number of results per page (default: 100)
        page (int): Page number (default: 1)

    Returns:
        List of DNS records
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)

    zone_id = params.get("zone_id")
    if not zone_id:
        return {"ok": False, "error": "zone_id is required"}

    query_params = {
        "type": params.get("type"),
        "name": params.get("name"),
        "content": params.get("content"),
        "per_page": params.get("per_page", 100),
        "page": params.get("page", 1),
    }

    result = _api_call(token, f"/zones/{zone_id}/dns_records", params=query_params)

    if result.get("ok") and result.get("result") is not None:
        records = [
            {
                "id": r.get("id"),
                "type": r.get("type"),
                "name": r.get("name"),
                "content": r.get("content"),
                "proxied": r.get("proxied"),
                "proxiable": r.get("proxiable"),
                "ttl": r.get("ttl"),
                "priority": r.get("priority"),
                "created_on": r.get("created_on"),
                "modified_on": r.get("modified_on"),
            }
            for r in result["result"]
        ]
        return {
            "ok": True,
            "data": {"records": records, "count": len(records)},
            "result_info": result.get("result_info"),
        }
    return result


def create_dns_record(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new DNS record.

    Params:
        zone_id (str): The zone identifier (required)
        type (str): Record type: A, AAAA, CNAME, TXT, MX, NS, SRV, etc. (required)
        name (str): DNS record name, e.g., "example.com" or "sub.example.com" (required)
        content (str): Record content, e.g., IP address for A record (required)
        ttl (int): TTL in seconds, 1 = automatic (default: 1)
        proxied (bool): Whether to proxy through Cloudflare (default: False)
        priority (int): Priority for MX/SRV records (optional)

    Returns:
        Created DNS record details
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)

    zone_id = params.get("zone_id")
    record_type = params.get("type")
    name = params.get("name")
    content = params.get("content")

    if not zone_id:
        return {"ok": False, "error": "zone_id is required"}
    if not record_type:
        return {"ok": False, "error": "type is required"}
    if not name:
        return {"ok": False, "error": "name is required"}
    if not content:
        return {"ok": False, "error": "content is required"}

    data: Dict[str, Any] = {
        "type": record_type,
        "name": name,
        "content": content,
        "ttl": params.get("ttl", 1),
    }

    # Only include proxied for proxy-able record types
    if record_type in ("A", "AAAA", "CNAME"):
        data["proxied"] = params.get("proxied", False)

    if params.get("priority") is not None:
        data["priority"] = params["priority"]

    result = _api_call(token, f"/zones/{zone_id}/dns_records", method="POST", data=data)

    if result.get("ok") and result.get("result"):
        r = result["result"]
        return {
            "ok": True,
            "data": {
                "id": r.get("id"),
                "type": r.get("type"),
                "name": r.get("name"),
                "content": r.get("content"),
                "proxied": r.get("proxied"),
                "ttl": r.get("ttl"),
                "created_on": r.get("created_on"),
            },
        }
    return result


def update_dns_record(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing DNS record.

    Params:
        zone_id (str): The zone identifier (required)
        record_id (str): The DNS record identifier (required)
        type (str): Record type: A, AAAA, CNAME, TXT, MX, etc. (required)
        name (str): DNS record name (required)
        content (str): Record content (required)
        ttl (int): TTL in seconds, 1 = automatic (optional)
        proxied (bool): Whether to proxy through Cloudflare (optional)
        priority (int): Priority for MX/SRV records (optional)

    Returns:
        Updated DNS record details
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)

    zone_id = params.get("zone_id")
    record_id = params.get("record_id")
    record_type = params.get("type")
    name = params.get("name")
    content = params.get("content")

    if not zone_id:
        return {"ok": False, "error": "zone_id is required"}
    if not record_id:
        return {"ok": False, "error": "record_id is required"}
    if not record_type:
        return {"ok": False, "error": "type is required"}
    if not name:
        return {"ok": False, "error": "name is required"}
    if not content:
        return {"ok": False, "error": "content is required"}

    data: Dict[str, Any] = {
        "type": record_type,
        "name": name,
        "content": content,
    }

    if params.get("ttl") is not None:
        data["ttl"] = params["ttl"]

    if params.get("proxied") is not None:
        data["proxied"] = params["proxied"]

    if params.get("priority") is not None:
        data["priority"] = params["priority"]

    result = _api_call(token, f"/zones/{zone_id}/dns_records/{record_id}", method="PUT", data=data)

    if result.get("ok") and result.get("result"):
        r = result["result"]
        return {
            "ok": True,
            "data": {
                "id": r.get("id"),
                "type": r.get("type"),
                "name": r.get("name"),
                "content": r.get("content"),
                "proxied": r.get("proxied"),
                "ttl": r.get("ttl"),
                "modified_on": r.get("modified_on"),
            },
        }
    return result


def delete_dns_record(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a DNS record.

    Params:
        zone_id (str): The zone identifier (required)
        record_id (str): The DNS record identifier (required)

    Returns:
        Deletion confirmation with record ID
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)

    zone_id = params.get("zone_id")
    record_id = params.get("record_id")

    if not zone_id:
        return {"ok": False, "error": "zone_id is required"}
    if not record_id:
        return {"ok": False, "error": "record_id is required"}

    result = _api_call(token, f"/zones/{zone_id}/dns_records/{record_id}", method="DELETE")

    if result.get("ok"):
        return {"ok": True, "data": {"deleted": True, "id": result.get("result", {}).get("id", record_id)}}
    return result


# =============================================================================
# Zone Settings Actions
# =============================================================================

def toggle_dev_mode(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enable or disable development mode for a zone.

    Development mode temporarily bypasses Cloudflare's cache, allowing you to
    see changes to your origin server in real time. It lasts for 3 hours unless
    disabled manually.

    Params:
        zone_id (str): The zone identifier (required)
        enabled (bool): True to enable, False to disable (required)

    Returns:
        Development mode status and expiration time
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)

    zone_id = params.get("zone_id")
    enabled = params.get("enabled")

    if not zone_id:
        return {"ok": False, "error": "zone_id is required"}
    if enabled is None:
        return {"ok": False, "error": "enabled is required (true or false)"}

    data = {"value": "on" if enabled else "off"}

    result = _api_call(token, f"/zones/{zone_id}/settings/development_mode", method="PATCH", data=data)

    if result.get("ok") and result.get("result"):
        r = result["result"]
        return {
            "ok": True,
            "data": {
                "id": r.get("id"),
                "value": r.get("value"),
                "enabled": r.get("value") == "on",
                "time_remaining": r.get("time_remaining"),
                "modified_on": r.get("modified_on"),
            },
        }
    return result


# =============================================================================
# Analytics Actions
# =============================================================================

def get_analytics(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get zone analytics data.

    Params:
        zone_id (str): The zone identifier (required)
        since (str): Start datetime in ISO 8601 format, e.g., "2024-01-01T00:00:00Z" (optional)
        until (str): End datetime in ISO 8601 format (optional)

    Returns:
        Analytics data including requests, bandwidth, threats, etc.
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)

    zone_id = params.get("zone_id")
    if not zone_id:
        return {"ok": False, "error": "zone_id is required"}

    query_params: Dict[str, Any] = {}
    if params.get("since"):
        query_params["since"] = params["since"]
    if params.get("until"):
        query_params["until"] = params["until"]

    result = _api_call(token, f"/zones/{zone_id}/analytics/dashboard", params=query_params if query_params else None)

    if result.get("ok") and result.get("result"):
        r = result["result"]
        totals = r.get("totals", {})
        timeseries = r.get("timeseries", [])

        return {
            "ok": True,
            "data": {
                "since": r.get("since"),
                "until": r.get("until"),
                "totals": {
                    "requests": totals.get("requests", {}).get("all", 0),
                    "cached_requests": totals.get("requests", {}).get("cached", 0),
                    "uncached_requests": totals.get("requests", {}).get("uncached", 0),
                    "bandwidth_bytes": totals.get("bandwidth", {}).get("all", 0),
                    "cached_bandwidth_bytes": totals.get("bandwidth", {}).get("cached", 0),
                    "threats": totals.get("threats", {}).get("all", 0),
                    "pageviews": totals.get("pageviews", {}).get("all", 0),
                    "unique_visitors": totals.get("uniques", {}).get("all", 0),
                },
                "timeseries_count": len(timeseries),
            },
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_zones": list_zones,
    "get_zone": get_zone,
    "purge_cache": purge_cache,
    "create_dns_record": create_dns_record,
    "update_dns_record": update_dns_record,
    "delete_dns_record": delete_dns_record,
    "list_dns_records": list_dns_records,
    "toggle_dev_mode": toggle_dev_mode,
    "get_analytics": get_analytics,
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
        logger.info(f"Executing cloudflare.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
