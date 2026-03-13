"""
Okta Controller for TinyHive

A controller for managing Okta users, groups, and applications via the Okta API.

Method IDs:
  controller.okta.{profile}.list_users
  controller.okta.{profile}.get_user
  controller.okta.{profile}.create_user
  controller.okta.{profile}.update_user
  controller.okta.{profile}.deactivate_user
  controller.okta.{profile}.list_groups
  controller.okta.{profile}.add_user_to_group
  controller.okta.{profile}.list_applications

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "domain": "your-org.okta.com",
    "token_env": "OKTA_API_TOKEN"
}

Required Permissions:
--------------------
- list_users: okta.users.read
- get_user: okta.users.read
- create_user: okta.users.manage
- update_user: okta.users.manage
- deactivate_user: okta.users.manage
- list_groups: okta.groups.read
- add_user_to_group: okta.groups.manage
- list_applications: okta.apps.read

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

logger = logging.getLogger("tinyhive.controller.okta")

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


def _get_api_token(profile: Dict[str, Any]) -> str:
    """Get the Okta API token from environment variable."""
    token_env = profile.get("token_env", "OKTA_API_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(f"Environment variable '{token_env}' not set")
    return token


def _get_base_url(profile: Dict[str, Any]) -> str:
    """Get the Okta API base URL from profile."""
    domain = profile.get("domain")
    if not domain:
        raise ValueError("Profile must specify 'domain' (e.g., 'your-org.okta.com')")
    return f"https://{domain}/api/v1"


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    url: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Okta API call."""
    headers = {
        "Authorization": f"SSWS {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
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
            return {"ok": True, "data": None}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("errorSummary", error_body[:500])
            error_causes = error_data.get("errorCauses", [])
            if error_causes:
                cause_messages = [c.get("errorSummary", "") for c in error_causes]
                error_message = f"{error_message}: {'; '.join(cause_messages)}"
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Okta API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Okta API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# User Actions
# =============================================================================

def list_users(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List users in Okta.

    Params:
        filter (str): Okta filter expression (e.g., 'status eq "ACTIVE"')
        search (str): Search expression for user profile attributes
        limit (int): Maximum number of users to return (default: 200, max: 200)
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    query_params = {}
    if params.get("filter"):
        query_params["filter"] = params["filter"]
    if params.get("search"):
        query_params["search"] = params["search"]
    if params.get("limit"):
        query_params["limit"] = min(int(params["limit"]), 200)
    else:
        query_params["limit"] = 200

    url = f"{base_url}/users"
    if query_params:
        url += f"?{urlencode(query_params)}"

    result = _api_call(token, url)

    if result.get("ok") and "data" in result:
        users = result["data"] or []
        return {
            "ok": True,
            "data": {
                "users": [
                    {
                        "id": u.get("id"),
                        "status": u.get("status"),
                        "login": u.get("profile", {}).get("login"),
                        "email": u.get("profile", {}).get("email"),
                        "firstName": u.get("profile", {}).get("firstName"),
                        "lastName": u.get("profile", {}).get("lastName"),
                        "created": u.get("created"),
                        "lastLogin": u.get("lastLogin"),
                    }
                    for u in users
                ],
                "count": len(users)
            }
        }
    return result


def get_user(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a user by ID.

    Params:
        user_id (str): User ID or login (email) (required)
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    user_id = params.get("user_id")
    if not user_id:
        return {"ok": False, "error": "user_id is required"}

    url = f"{base_url}/users/{user_id}"
    result = _api_call(token, url)

    if result.get("ok") and "data" in result:
        user = result["data"]
        return {
            "ok": True,
            "data": {
                "id": user.get("id"),
                "status": user.get("status"),
                "profile": user.get("profile"),
                "credentials": {
                    "provider": user.get("credentials", {}).get("provider", {})
                },
                "created": user.get("created"),
                "activated": user.get("activated"),
                "lastLogin": user.get("lastLogin"),
                "lastUpdated": user.get("lastUpdated"),
            }
        }
    return result


def create_user(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new user in Okta.

    Params:
        profile (dict): User profile (required)
            - login (str): User login/email (required)
            - email (str): User email (required)
            - firstName (str): First name (required)
            - lastName (str): Last name (required)
            - ... other profile fields
        credentials (dict): User credentials (optional)
            - password (dict): {"value": "password"} for setting password
            - recovery_question (dict): {"question": "...", "answer": "..."}
        groupIds (list): List of group IDs to add user to (optional)
        activate (bool): Activate user immediately (default: True)
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    user_profile = params.get("profile")
    if not user_profile:
        return {"ok": False, "error": "profile is required"}

    required_fields = ["login", "email", "firstName", "lastName"]
    for field in required_fields:
        if field not in user_profile:
            return {"ok": False, "error": f"profile.{field} is required"}

    request_body: Dict[str, Any] = {"profile": user_profile}

    if params.get("credentials"):
        request_body["credentials"] = params["credentials"]

    if params.get("groupIds"):
        request_body["groupIds"] = params["groupIds"]

    activate = params.get("activate", True)
    url = f"{base_url}/users?activate={str(activate).lower()}"

    result = _api_call(token, url, method="POST", data=request_body)

    if result.get("ok") and "data" in result:
        user = result["data"]
        return {
            "ok": True,
            "data": {
                "id": user.get("id"),
                "status": user.get("status"),
                "login": user.get("profile", {}).get("login"),
                "email": user.get("profile", {}).get("email"),
                "created": user.get("created"),
            }
        }
    return result


def update_user(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update a user's profile.

    Params:
        user_id (str): User ID (required)
        profile (dict): Profile fields to update (required)
            - firstName, lastName, email, etc.
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    user_id = params.get("user_id")
    if not user_id:
        return {"ok": False, "error": "user_id is required"}

    user_profile = params.get("profile")
    if not user_profile:
        return {"ok": False, "error": "profile is required"}

    request_body = {"profile": user_profile}
    url = f"{base_url}/users/{user_id}"

    result = _api_call(token, url, method="POST", data=request_body)

    if result.get("ok") and "data" in result:
        user = result["data"]
        return {
            "ok": True,
            "data": {
                "id": user.get("id"),
                "status": user.get("status"),
                "profile": user.get("profile"),
                "lastUpdated": user.get("lastUpdated"),
            }
        }
    return result


def deactivate_user(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deactivate a user.

    Params:
        user_id (str): User ID (required)
        send_email (bool): Send deactivation email to user (default: False)
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    user_id = params.get("user_id")
    if not user_id:
        return {"ok": False, "error": "user_id is required"}

    send_email = params.get("send_email", False)
    url = f"{base_url}/users/{user_id}/lifecycle/deactivate?sendEmail={str(send_email).lower()}"

    result = _api_call(token, url, method="POST")

    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "user_id": user_id,
                "status": "DEPROVISIONED",
                "message": "User deactivated successfully"
            }
        }
    return result


# =============================================================================
# Group Actions
# =============================================================================

def list_groups(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List groups in Okta.

    Params:
        filter (str): Okta filter expression (e.g., 'type eq "OKTA_GROUP"')
        q (str): Search query for group name
        limit (int): Maximum number of groups to return (default: 200, max: 200)
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    query_params = {}
    if params.get("filter"):
        query_params["filter"] = params["filter"]
    if params.get("q"):
        query_params["q"] = params["q"]
    if params.get("limit"):
        query_params["limit"] = min(int(params["limit"]), 200)
    else:
        query_params["limit"] = 200

    url = f"{base_url}/groups"
    if query_params:
        url += f"?{urlencode(query_params)}"

    result = _api_call(token, url)

    if result.get("ok") and "data" in result:
        groups = result["data"] or []
        return {
            "ok": True,
            "data": {
                "groups": [
                    {
                        "id": g.get("id"),
                        "type": g.get("type"),
                        "name": g.get("profile", {}).get("name"),
                        "description": g.get("profile", {}).get("description"),
                        "created": g.get("created"),
                        "lastUpdated": g.get("lastUpdated"),
                        "lastMembershipUpdated": g.get("lastMembershipUpdated"),
                    }
                    for g in groups
                ],
                "count": len(groups)
            }
        }
    return result


def add_user_to_group(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a user to a group.

    Params:
        group_id (str): Group ID (required)
        user_id (str): User ID (required)
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    group_id = params.get("group_id")
    if not group_id:
        return {"ok": False, "error": "group_id is required"}

    user_id = params.get("user_id")
    if not user_id:
        return {"ok": False, "error": "user_id is required"}

    url = f"{base_url}/groups/{group_id}/users/{user_id}"

    result = _api_call(token, url, method="PUT")

    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "group_id": group_id,
                "user_id": user_id,
                "message": "User added to group successfully"
            }
        }
    return result


# =============================================================================
# Application Actions
# =============================================================================

def list_applications(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List applications in Okta.

    Params:
        filter (str): Okta filter expression (e.g., 'status eq "ACTIVE"')
        q (str): Search query for application name
        limit (int): Maximum number of applications to return (default: 200, max: 200)
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    query_params = {}
    if params.get("filter"):
        query_params["filter"] = params["filter"]
    if params.get("q"):
        query_params["q"] = params["q"]
    if params.get("limit"):
        query_params["limit"] = min(int(params["limit"]), 200)
    else:
        query_params["limit"] = 200

    url = f"{base_url}/apps"
    if query_params:
        url += f"?{urlencode(query_params)}"

    result = _api_call(token, url)

    if result.get("ok") and "data" in result:
        apps = result["data"] or []
        return {
            "ok": True,
            "data": {
                "applications": [
                    {
                        "id": a.get("id"),
                        "name": a.get("name"),
                        "label": a.get("label"),
                        "status": a.get("status"),
                        "signOnMode": a.get("signOnMode"),
                        "created": a.get("created"),
                        "lastUpdated": a.get("lastUpdated"),
                    }
                    for a in apps
                ],
                "count": len(apps)
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_users": list_users,
    "get_user": get_user,
    "create_user": create_user,
    "update_user": update_user,
    "deactivate_user": deactivate_user,
    "list_groups": list_groups,
    "add_user_to_group": add_user_to_group,
    "list_applications": list_applications,
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
        logger.info(f"Executing okta.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
