"""API controller template — REST API integration.

Method IDs:
  controller.api.{profile}.list
  controller.api.{profile}.get
  controller.api.{profile}.create
  controller.api.{profile}.update
  controller.api.{profile}.delete
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

log = logging.getLogger("tinyhive.controller.api")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

DEFAULT_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Available: {list_profiles()}")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

def _get_api_key(profile: Dict[str, Any]) -> str:
    """Get API key from environment variable specified in profile."""
    env_var = profile.get("api_key_env", "")
    if not env_var:
        raise ValueError("Profile missing 'api_key_env'")
    key = os.environ.get(env_var, "")
    if not key:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return key


def _make_request(
    method: str,
    url: str,
    headers: Dict[str, str],
    data: Optional[bytes] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """Make an HTTP request and return parsed JSON response."""
    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return {
                "ok": True,
                "status": response.status,
                "data": json.loads(body) if body else None,
            }
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": e.code,
            "error": f"HTTP {e.code}: {e.reason}",
            "body": body[:1000],
        }
    except URLError as e:
        return {"ok": False, "error": f"Connection error: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def list_resources(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List resources from the API.

    Params:
        - page: Page number (default: 1)
        - per_page: Items per page (default: 20)
        - filter: Optional filter criteria
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    base_url = profile.get("base_url", "").rstrip("/")

    resource = params.get("resource", "items")
    page = params.get("page", 1)
    per_page = params.get("per_page", 20)

    url = f"{base_url}/{resource}?page={page}&per_page={per_page}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    return _make_request("GET", url, headers, timeout=profile.get("timeout", DEFAULT_TIMEOUT))


def get_resource(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get a single resource by ID.

    Params:
        - resource: Resource type (e.g., "items")
        - id: Resource ID
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    base_url = profile.get("base_url", "").rstrip("/")

    resource = params.get("resource", "items")
    resource_id = params.get("id", "")

    if not resource_id:
        return {"ok": False, "error": "id is required"}

    url = f"{base_url}/{resource}/{resource_id}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    return _make_request("GET", url, headers, timeout=profile.get("timeout", DEFAULT_TIMEOUT))


def create_resource(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new resource.

    Params:
        - resource: Resource type
        - data: Resource data to create
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    base_url = profile.get("base_url", "").rstrip("/")

    resource = params.get("resource", "items")
    data = params.get("data", {})

    url = f"{base_url}/{resource}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    return _make_request(
        "POST", url, headers,
        data=json.dumps(data).encode("utf-8"),
        timeout=profile.get("timeout", DEFAULT_TIMEOUT)
    )


def update_resource(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Update an existing resource.

    Params:
        - resource: Resource type
        - id: Resource ID
        - data: Fields to update
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    base_url = profile.get("base_url", "").rstrip("/")

    resource = params.get("resource", "items")
    resource_id = params.get("id", "")
    data = params.get("data", {})

    if not resource_id:
        return {"ok": False, "error": "id is required"}

    url = f"{base_url}/{resource}/{resource_id}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    return _make_request(
        "PUT", url, headers,
        data=json.dumps(data).encode("utf-8"),
        timeout=profile.get("timeout", DEFAULT_TIMEOUT)
    )


def delete_resource(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Delete a resource.

    Params:
        - resource: Resource type
        - id: Resource ID
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    base_url = profile.get("base_url", "").rstrip("/")

    resource = params.get("resource", "items")
    resource_id = params.get("id", "")

    if not resource_id:
        return {"ok": False, "error": "id is required"}

    url = f"{base_url}/{resource}/{resource_id}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    return _make_request("DELETE", url, headers, timeout=profile.get("timeout", DEFAULT_TIMEOUT))


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

ACTIONS = {
    "list": list_resources,
    "get": get_resource,
    "create": create_resource,
    "update": update_resource,
    "delete": delete_resource,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """Dispatch an action by name with a profile."""
    if action not in ACTIONS:
        return {
            "ok": False,
            "error": f"Unknown action '{action}'. Available: {list(ACTIONS.keys())}"
        }
    return ACTIONS[action](profile, params)
