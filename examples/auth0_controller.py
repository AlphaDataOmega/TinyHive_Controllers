"""Auth0 Controller — Auth0 Management API integration.

This controller provides integration with Auth0 Management API using
OAuth2 Machine-to-Machine (M2M) client credentials authentication.

Method IDs:
  controller.auth0.{profile}.list_users
  controller.auth0.{profile}.get_user
  controller.auth0.{profile}.create_user
  controller.auth0.{profile}.update_user
  controller.auth0.{profile}.delete_user
  controller.auth0.{profile}.assign_roles
  controller.auth0.{profile}.list_roles
  controller.auth0.{profile}.get_user_logs

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:

  {
    "domain": "your-tenant.auth0.com",
    "client_id_env": "AUTH0_CLIENT_ID",
    "client_secret_env": "AUTH0_CLIENT_SECRET",
    "audience": "https://your-tenant.auth0.com/api/v2/",
    "default_connection": "Username-Password-Authentication"
  }

Required Scopes (configure in Auth0 Dashboard -> Applications -> APIs):
  - read:users
  - create:users
  - update:users
  - delete:users
  - read:roles
  - create:role_members
  - read:logs

Dependencies:
  - None (standard library only)
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.auth0")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# Token cache: profile_name -> (token, expiry_timestamp)
_token_cache: Dict[str, Tuple[str, float]] = {}

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with Auth0 configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available Auth0 profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# OAuth2 M2M Token Management
# =============================================================================

def _get_access_token(profile: Dict[str, Any], profile_name: str) -> str:
    """Get OAuth2 access token for Auth0 Management API using client credentials.

    Uses M2M (Machine-to-Machine) authentication flow:
    1. POST to https://{domain}/oauth/token
    2. With client_credentials grant type
    3. Returns access token for Management API
    """
    # Check cache first
    if profile_name in _token_cache:
        token, expiry = _token_cache[profile_name]
        if time.time() < expiry:
            return token

    domain = profile.get("domain")
    if not domain:
        raise ValueError("Profile must specify 'domain'")

    # Get client credentials from environment
    client_id_env = profile.get("client_id_env", "AUTH0_CLIENT_ID")
    client_secret_env = profile.get("client_secret_env", "AUTH0_CLIENT_SECRET")

    client_id = os.environ.get(client_id_env)
    client_secret = os.environ.get(client_secret_env)

    if not client_id:
        raise ValueError(f"Environment variable '{client_id_env}' not set")
    if not client_secret:
        raise ValueError(f"Environment variable '{client_secret_env}' not set")

    # Default audience is the Management API
    audience = profile.get("audience", f"https://{domain}/api/v2/")

    # Request token
    token_url = f"https://{domain}/oauth/token"

    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "audience": audience
    }

    data = json.dumps(payload).encode("utf-8")

    req = Request(
        token_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urlopen(req, timeout=30) as response:
            token_data = json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"Token request failed: HTTP {e.code}: {error_body}")
    except URLError as e:
        raise ValueError(f"Token request failed: {e.reason}")

    access_token = token_data.get("access_token")
    if not access_token:
        raise ValueError("No access_token in response")

    # Cache token with buffer before expiry
    expires_in = token_data.get("expires_in", 86400)
    expiry = time.time() + expires_in - 60
    _token_cache[profile_name] = (access_token, expiry)

    return access_token


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Auth0 Management API call."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "data": json.loads(response_body)}
            return {"ok": True, "data": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_data.get("error_description", error_body[:500]))
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Auth0 API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Auth0 API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# User Management Actions
# =============================================================================

def list_users(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List users in Auth0 tenant.

    Required Scope: read:users

    Params:
        per_page (int): Number of results per page (default: 50, max: 100)
        page (int): Page index (zero-based, default: 0)
        search_engine (str): Search engine version: 'v2' or 'v3' (default: 'v3')
        q (str): Lucene query string for filtering users (optional)
            Examples:
            - email:"john@example.com"
            - name:*john*
            - app_metadata.plan:"premium"
            - identities.connection:"google-oauth2"
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    domain = profile["domain"]

    query_params = {
        "per_page": params.get("per_page", 50),
        "page": params.get("page", 0),
        "search_engine": params.get("search_engine", "v3"),
    }

    if params.get("q"):
        query_params["q"] = params["q"]

    url = f"https://{domain}/api/v2/users?{urlencode(query_params)}"
    result = _api_call(token, url)

    if result.get("ok") and "data" in result:
        users = result["data"]
        return {
            "ok": True,
            "data": {
                "users": [
                    {
                        "user_id": u.get("user_id"),
                        "email": u.get("email"),
                        "email_verified": u.get("email_verified"),
                        "name": u.get("name"),
                        "nickname": u.get("nickname"),
                        "picture": u.get("picture"),
                        "created_at": u.get("created_at"),
                        "updated_at": u.get("updated_at"),
                        "last_login": u.get("last_login"),
                        "logins_count": u.get("logins_count"),
                        "identities": u.get("identities", []),
                    }
                    for u in (users if isinstance(users, list) else [])
                ],
                "page": params.get("page", 0),
                "per_page": params.get("per_page", 50),
            }
        }
    return result


def get_user(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a user by ID.

    Required Scope: read:users

    Params:
        user_id (str): The user_id of the user to retrieve (required)
            Format: auth0|xxx, google-oauth2|xxx, etc.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    domain = profile["domain"]

    user_id = params.get("user_id", "")
    if not user_id:
        return {"ok": False, "error": "user_id required"}

    # URL-encode user_id as it contains special characters
    from urllib.parse import quote
    encoded_user_id = quote(user_id, safe="")

    url = f"https://{domain}/api/v2/users/{encoded_user_id}"
    result = _api_call(token, url)

    if result.get("ok") and "data" in result:
        u = result["data"]
        return {
            "ok": True,
            "data": {
                "user_id": u.get("user_id"),
                "email": u.get("email"),
                "email_verified": u.get("email_verified"),
                "name": u.get("name"),
                "nickname": u.get("nickname"),
                "picture": u.get("picture"),
                "created_at": u.get("created_at"),
                "updated_at": u.get("updated_at"),
                "last_login": u.get("last_login"),
                "logins_count": u.get("logins_count"),
                "identities": u.get("identities", []),
                "app_metadata": u.get("app_metadata", {}),
                "user_metadata": u.get("user_metadata", {}),
            }
        }
    return result


def create_user(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new user.

    Required Scope: create:users

    Params:
        email (str): User's email address (required)
        password (str): User's password (required for database connections)
        connection (str): Connection name (default: from profile or 'Username-Password-Authentication')
        name (str): User's full name (optional)
        nickname (str): User's nickname (optional)
        email_verified (bool): Whether email is verified (default: False)
        user_metadata (dict): Custom user metadata (optional)
        app_metadata (dict): Custom app metadata (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    domain = profile["domain"]

    email = params.get("email", "")
    if not email:
        return {"ok": False, "error": "email required"}

    connection = params.get("connection", profile.get("default_connection", "Username-Password-Authentication"))

    payload: Dict[str, Any] = {
        "email": email,
        "connection": connection,
    }

    # Password is required for database connections
    if params.get("password"):
        payload["password"] = params["password"]

    # Optional fields
    if params.get("name"):
        payload["name"] = params["name"]
    if params.get("nickname"):
        payload["nickname"] = params["nickname"]
    if "email_verified" in params:
        payload["email_verified"] = params["email_verified"]
    if params.get("user_metadata"):
        payload["user_metadata"] = params["user_metadata"]
    if params.get("app_metadata"):
        payload["app_metadata"] = params["app_metadata"]

    url = f"https://{domain}/api/v2/users"
    data = json.dumps(payload).encode("utf-8")

    result = _api_call(token, url, method="POST", data=data)

    if result.get("ok") and "data" in result:
        u = result["data"]
        return {
            "ok": True,
            "data": {
                "user_id": u.get("user_id"),
                "email": u.get("email"),
                "email_verified": u.get("email_verified"),
                "name": u.get("name"),
                "nickname": u.get("nickname"),
                "created_at": u.get("created_at"),
                "connection": connection,
            }
        }
    return result


def update_user(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update a user's attributes.

    Required Scope: update:users

    Params:
        user_id (str): The user_id of the user to update (required)
        fields (dict): Fields to update. Supported fields:
            - email (str): New email address
            - email_verified (bool): Email verification status
            - name (str): User's full name
            - nickname (str): User's nickname
            - picture (str): URL to user's picture
            - password (str): New password (database connections only)
            - blocked (bool): Whether user is blocked
            - user_metadata (dict): Custom user metadata
            - app_metadata (dict): Custom app metadata
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    domain = profile["domain"]

    user_id = params.get("user_id", "")
    if not user_id:
        return {"ok": False, "error": "user_id required"}

    fields = params.get("fields", {})
    if not fields:
        return {"ok": False, "error": "fields required"}

    # Only include allowed fields
    allowed_fields = {
        "email", "email_verified", "name", "nickname", "picture",
        "password", "blocked", "user_metadata", "app_metadata",
        "phone_number", "phone_verified", "verify_email"
    }

    payload = {k: v for k, v in fields.items() if k in allowed_fields}

    if not payload:
        return {"ok": False, "error": "No valid fields to update"}

    from urllib.parse import quote
    encoded_user_id = quote(user_id, safe="")

    url = f"https://{domain}/api/v2/users/{encoded_user_id}"
    data = json.dumps(payload).encode("utf-8")

    result = _api_call(token, url, method="PATCH", data=data)

    if result.get("ok") and "data" in result:
        u = result["data"]
        return {
            "ok": True,
            "data": {
                "user_id": u.get("user_id"),
                "email": u.get("email"),
                "email_verified": u.get("email_verified"),
                "name": u.get("name"),
                "nickname": u.get("nickname"),
                "updated_at": u.get("updated_at"),
            }
        }
    return result


def delete_user(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a user.

    Required Scope: delete:users

    Params:
        user_id (str): The user_id of the user to delete (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    domain = profile["domain"]

    user_id = params.get("user_id", "")
    if not user_id:
        return {"ok": False, "error": "user_id required"}

    from urllib.parse import quote
    encoded_user_id = quote(user_id, safe="")

    url = f"https://{domain}/api/v2/users/{encoded_user_id}"
    result = _api_call(token, url, method="DELETE")

    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "deleted": True,
                "user_id": user_id
            }
        }
    return result


# =============================================================================
# Role Management Actions
# =============================================================================

def assign_roles(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assign roles to a user.

    Required Scope: create:role_members

    Params:
        user_id (str): The user_id of the user (required)
        role_ids (list): List of role IDs to assign (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    domain = profile["domain"]

    user_id = params.get("user_id", "")
    if not user_id:
        return {"ok": False, "error": "user_id required"}

    role_ids = params.get("role_ids", [])
    if not role_ids:
        return {"ok": False, "error": "role_ids required"}
    if not isinstance(role_ids, list):
        return {"ok": False, "error": "role_ids must be a list"}

    from urllib.parse import quote
    encoded_user_id = quote(user_id, safe="")

    url = f"https://{domain}/api/v2/users/{encoded_user_id}/roles"
    payload = {"roles": role_ids}
    data = json.dumps(payload).encode("utf-8")

    result = _api_call(token, url, method="POST", data=data)

    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "assigned": True,
                "user_id": user_id,
                "role_ids": role_ids
            }
        }
    return result


def list_roles(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all roles defined in the tenant.

    Required Scope: read:roles

    Params:
        per_page (int): Number of results per page (default: 50, max: 100)
        page (int): Page index (zero-based, default: 0)
        name_filter (str): Filter roles by name (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    domain = profile["domain"]

    query_params = {
        "per_page": params.get("per_page", 50),
        "page": params.get("page", 0),
    }

    if params.get("name_filter"):
        query_params["name_filter"] = params["name_filter"]

    url = f"https://{domain}/api/v2/roles?{urlencode(query_params)}"
    result = _api_call(token, url)

    if result.get("ok") and "data" in result:
        roles = result["data"]
        return {
            "ok": True,
            "data": {
                "roles": [
                    {
                        "id": r.get("id"),
                        "name": r.get("name"),
                        "description": r.get("description"),
                    }
                    for r in (roles if isinstance(roles, list) else [])
                ],
                "page": params.get("page", 0),
                "per_page": params.get("per_page", 50),
            }
        }
    return result


# =============================================================================
# Logs Actions
# =============================================================================

def get_user_logs(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get authentication logs for a specific user.

    Required Scope: read:logs

    Params:
        user_id (str): The user_id to get logs for (required)
        per_page (int): Number of results per page (default: 50, max: 100)
        page (int): Page index (zero-based, default: 0)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    domain = profile["domain"]

    user_id = params.get("user_id", "")
    if not user_id:
        return {"ok": False, "error": "user_id required"}

    per_page = params.get("per_page", 50)
    page = params.get("page", 0)

    # Search logs by user_id using the q parameter with Lucene syntax
    from urllib.parse import quote
    query = f'user_id:"{user_id}"'

    query_params = {
        "per_page": per_page,
        "page": page,
        "q": query,
    }

    url = f"https://{domain}/api/v2/logs?{urlencode(query_params)}"
    result = _api_call(token, url)

    if result.get("ok") and "data" in result:
        logs = result["data"]
        return {
            "ok": True,
            "data": {
                "logs": [
                    {
                        "log_id": log.get("log_id") or log.get("_id"),
                        "date": log.get("date"),
                        "type": log.get("type"),
                        "description": log.get("description"),
                        "client_id": log.get("client_id"),
                        "client_name": log.get("client_name"),
                        "ip": log.get("ip"),
                        "user_agent": log.get("user_agent"),
                        "user_id": log.get("user_id"),
                        "user_name": log.get("user_name"),
                        "connection": log.get("connection"),
                        "connection_id": log.get("connection_id"),
                    }
                    for log in (logs if isinstance(logs, list) else [])
                ],
                "user_id": user_id,
                "page": page,
                "per_page": per_page,
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
    "delete_user": delete_user,
    "assign_roles": assign_roles,
    "list_roles": list_roles,
    "get_user_logs": get_user_logs,
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
        logger.info(f"Executing auth0.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
