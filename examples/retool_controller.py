"""
Retool Controller for TinyHive

A controller for managing Retool apps, users, groups, and workflows via the Retool API.
Supports both Retool Cloud and self-hosted instances.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "host": "your-org.retool.com",  // For cloud: org.retool.com, for self-hosted: your-domain.com
    "api_key_env": "RETOOL_API_KEY"  // Environment variable containing the API key
}

Required Permissions:
--------------------
- Apps: Read/write access to apps
- Users: User management permissions
- Groups: Group management permissions
- Workflows: Workflow execution permissions

Dependencies:
------------
None (standard library only)

API Documentation:
-----------------
https://docs.retool.com/reference/api
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.retool")

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


def _get_api_key(profile: Dict[str, Any]) -> str:
    """Get the API key from the environment variable specified in the profile."""
    env_var = profile.get("api_key_env", "RETOOL_API_KEY")
    api_key = os.environ.get(env_var)
    if not api_key:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return api_key


def _get_base_url(profile: Dict[str, Any]) -> str:
    """Get the base URL for the Retool API."""
    host = profile.get("host")
    if not host:
        raise ValueError("Profile must specify 'host' (e.g., 'your-org.retool.com')")
    return f"https://{host}/api/v2"


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    profile: Dict[str, Any],
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Retool API call."""
    api_key = _get_api_key(profile)
    base_url = _get_base_url(profile)
    url = f"{base_url}{endpoint}"

    headers = {
        "Authorization": f"Bearer {api_key}",
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
                return {"ok": True, "data": json.loads(response_body)}
            return {"ok": True, "data": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Retool API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Retool API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# App Actions
# =============================================================================

def list_apps(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List Retool apps.

    Params:
        folder_id (str): Filter by folder ID (optional)
    """
    try:
        profile = load_profile(profile_name)

        endpoint = "/apps"
        query_params = {}

        folder_id = params.get("folder_id")
        if folder_id:
            query_params["folder_id"] = folder_id

        if query_params:
            endpoint += f"?{urlencode(query_params)}"

        result = _api_call(profile, endpoint, method="GET")

        if result.get("ok") and "data" in result:
            apps_data = result["data"]
            # Handle both list and dict response formats
            if isinstance(apps_data, dict):
                apps = apps_data.get("data", apps_data.get("apps", []))
            else:
                apps = apps_data
            return {
                "ok": True,
                "data": {
                    "apps": apps,
                    "count": len(apps) if isinstance(apps, list) else 0
                }
            }
        return result
    except Exception as e:
        logger.exception("list_apps failed")
        return {"ok": False, "error": str(e)}


def get_app(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a specific app.

    Params:
        app_id (str): The app ID (required)
    """
    try:
        profile = load_profile(profile_name)

        app_id = params.get("app_id")
        if not app_id:
            return {"ok": False, "error": "app_id is required"}

        endpoint = f"/apps/{app_id}"
        result = _api_call(profile, endpoint, method="GET")

        if result.get("ok") and "data" in result:
            app_data = result["data"]
            # Handle nested data structure
            if isinstance(app_data, dict) and "data" in app_data:
                app_data = app_data["data"]
            return {"ok": True, "data": {"app": app_data}}
        return result
    except Exception as e:
        logger.exception("get_app failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# User Actions
# =============================================================================

def list_users(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all users in the Retool organization.

    Params:
        None
    """
    try:
        profile = load_profile(profile_name)

        endpoint = "/users"
        result = _api_call(profile, endpoint, method="GET")

        if result.get("ok") and "data" in result:
            users_data = result["data"]
            # Handle both list and dict response formats
            if isinstance(users_data, dict):
                users = users_data.get("data", users_data.get("users", []))
            else:
                users = users_data
            return {
                "ok": True,
                "data": {
                    "users": users,
                    "count": len(users) if isinstance(users, list) else 0
                }
            }
        return result
    except Exception as e:
        logger.exception("list_users failed")
        return {"ok": False, "error": str(e)}


def get_user(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a specific user.

    Params:
        user_id (str): The user ID (required)
    """
    try:
        profile = load_profile(profile_name)

        user_id = params.get("user_id")
        if not user_id:
            return {"ok": False, "error": "user_id is required"}

        endpoint = f"/users/{user_id}"
        result = _api_call(profile, endpoint, method="GET")

        if result.get("ok") and "data" in result:
            user_data = result["data"]
            # Handle nested data structure
            if isinstance(user_data, dict) and "data" in user_data:
                user_data = user_data["data"]
            return {"ok": True, "data": {"user": user_data}}
        return result
    except Exception as e:
        logger.exception("get_user failed")
        return {"ok": False, "error": str(e)}


def create_user(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new user in the Retool organization.

    Params:
        email (str): User's email address (required)
        first_name (str): User's first name (required)
        last_name (str): User's last name (required)
    """
    try:
        profile = load_profile(profile_name)

        email = params.get("email")
        first_name = params.get("first_name")
        last_name = params.get("last_name")

        if not email:
            return {"ok": False, "error": "email is required"}
        if not first_name:
            return {"ok": False, "error": "first_name is required"}
        if not last_name:
            return {"ok": False, "error": "last_name is required"}

        endpoint = "/users"
        data = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name
        }

        result = _api_call(profile, endpoint, method="POST", data=data)

        if result.get("ok") and "data" in result:
            user_data = result["data"]
            # Handle nested data structure
            if isinstance(user_data, dict) and "data" in user_data:
                user_data = user_data["data"]
            return {"ok": True, "data": {"user": user_data}}
        return result
    except Exception as e:
        logger.exception("create_user failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Group Actions
# =============================================================================

def list_groups(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all permission groups in the Retool organization.

    Params:
        None
    """
    try:
        profile = load_profile(profile_name)

        endpoint = "/groups"
        result = _api_call(profile, endpoint, method="GET")

        if result.get("ok") and "data" in result:
            groups_data = result["data"]
            # Handle both list and dict response formats
            if isinstance(groups_data, dict):
                groups = groups_data.get("data", groups_data.get("groups", []))
            else:
                groups = groups_data
            return {
                "ok": True,
                "data": {
                    "groups": groups,
                    "count": len(groups) if isinstance(groups, list) else 0
                }
            }
        return result
    except Exception as e:
        logger.exception("list_groups failed")
        return {"ok": False, "error": str(e)}


def add_user_to_group(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a user to a permission group.

    Params:
        user_id (str): The user ID (required)
        group_id (str): The group ID (required)
    """
    try:
        profile = load_profile(profile_name)

        user_id = params.get("user_id")
        group_id = params.get("group_id")

        if not user_id:
            return {"ok": False, "error": "user_id is required"}
        if not group_id:
            return {"ok": False, "error": "group_id is required"}

        endpoint = f"/groups/{group_id}/members"
        data = {
            "user_id": user_id
        }

        result = _api_call(profile, endpoint, method="POST", data=data)

        if result.get("ok"):
            return {"ok": True, "data": {"user_id": user_id, "group_id": group_id, "status": "added"}}
        return result
    except Exception as e:
        logger.exception("add_user_to_group failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Workflow Actions
# =============================================================================

def run_workflow(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trigger a Retool workflow.

    Params:
        workflow_id (str): The workflow ID (required)
        data (dict): Data to pass to the workflow (optional)
    """
    try:
        profile = load_profile(profile_name)

        workflow_id = params.get("workflow_id")
        if not workflow_id:
            return {"ok": False, "error": "workflow_id is required"}

        workflow_data = params.get("data", {})

        endpoint = f"/workflows/{workflow_id}/run"
        result = _api_call(profile, endpoint, method="POST", data=workflow_data)

        if result.get("ok") and "data" in result:
            run_data = result["data"]
            # Handle nested data structure
            if isinstance(run_data, dict) and "data" in run_data:
                run_data = run_data["data"]
            return {"ok": True, "data": {"workflow_id": workflow_id, "result": run_data}}
        return result
    except Exception as e:
        logger.exception("run_workflow failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_apps": list_apps,
    "get_app": get_app,
    "list_users": list_users,
    "get_user": get_user,
    "create_user": create_user,
    "list_groups": list_groups,
    "add_user_to_group": add_user_to_group,
    "run_workflow": run_workflow,
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

    logger.info(f"Executing retool.{profile}.{action}")
    return ACTIONS[action](profile, params)
