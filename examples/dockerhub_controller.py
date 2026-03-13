"""Docker Hub Controller for TinyHive

A controller for interacting with Docker Hub's API v2.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "username_env": "DOCKERHUB_USERNAME",
    "pat_env": "DOCKERHUB_PAT",
    "default_namespace": "myorg"
}

Environment Variables:
---------------------
- DOCKERHUB_USERNAME: Your Docker Hub username
- DOCKERHUB_PAT: Personal Access Token (create at https://hub.docker.com/settings/security)

Required Permissions:
--------------------
- Read access for search, list_repos, get_repo, list_tags, get_tag, get_rate_limits
- Read/Write access for delete_tag
- Admin access for list_webhooks

Dependencies:
------------
None - uses Python standard library only

Method IDs:
----------
  controller.dockerhub.{profile}.search
  controller.dockerhub.{profile}.list_repos
  controller.dockerhub.{profile}.get_repo
  controller.dockerhub.{profile}.list_tags
  controller.dockerhub.{profile}.get_tag
  controller.dockerhub.{profile}.delete_tag
  controller.dockerhub.{profile}.get_rate_limits
  controller.dockerhub.{profile}.list_webhooks
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.dockerhub")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# Docker Hub API endpoints
API_BASE = "https://hub.docker.com/v2"
AUTH_URL = "https://hub.docker.com/v2/users/login"

# Token cache: profile_name -> (token, expiry_timestamp)
_token_cache: Dict[str, Tuple[str, float]] = {}

DEFAULT_TIMEOUT = 30
TOKEN_EXPIRY_SECONDS = 300  # 5 minutes, Docker Hub tokens are short-lived


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with Docker Hub configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available Docker Hub profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# JWT Token Authentication
# =============================================================================

def _get_credentials(profile: Dict[str, Any]) -> Tuple[str, str]:
    """Get Docker Hub credentials from environment variables."""
    username_env = profile.get("username_env", "DOCKERHUB_USERNAME")
    pat_env = profile.get("pat_env", "DOCKERHUB_PAT")

    username = os.environ.get(username_env, "")
    pat = os.environ.get(pat_env, "")

    if not username:
        raise ValueError(f"Environment variable '{username_env}' not set.")
    if not pat:
        raise ValueError(f"Environment variable '{pat_env}' not set.")

    return username, pat


def _acquire_token(username: str, password: str) -> Tuple[str, float]:
    """Acquire a JWT token from Docker Hub."""
    payload = json.dumps({"username": username, "password": password}).encode("utf-8")

    req = Request(
        AUTH_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
            token = data.get("token", "")
            if not token:
                raise ValueError("No token returned from Docker Hub authentication")
            # Docker Hub tokens expire quickly; use a conservative expiry
            expiry = time.time() + TOKEN_EXPIRY_SECONDS
            return token, expiry
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"Authentication failed: HTTP {e.code}: {error_body[:500]}")


def _get_token(profile: Dict[str, Any], profile_name: str) -> str:
    """Get a valid JWT token, using cache if available."""
    if profile_name in _token_cache:
        token, expiry = _token_cache[profile_name]
        if time.time() < expiry:
            return token

    username, pat = _get_credentials(profile)
    token, expiry = _acquire_token(username, pat)
    _token_cache[profile_name] = (token, expiry)
    return token


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: Optional[str],
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    timeout: int = DEFAULT_TIMEOUT,
    extra_headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Make an authenticated Docker Hub API call."""
    headers = {
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)

    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            # Capture rate limit headers if present
            rate_limit_info = {}
            for header in ["RateLimit-Limit", "RateLimit-Remaining", "RateLimit-Reset"]:
                value = response.headers.get(header)
                if value:
                    rate_limit_info[header.lower().replace("-", "_")] = value

            if response_body:
                result = json.loads(response_body)
                if rate_limit_info:
                    result["_rate_limit"] = rate_limit_info
                return {"ok": True, "result": result}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_data.get("detail", error_body[:500]))
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Docker Hub API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Docker Hub API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def search(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for images on Docker Hub.

    Params:
        query (str): Search query (required)
        page_size (int): Number of results per page (default: 25, max: 100)
        page (int): Page number (default: 1)

    Returns:
        List of matching images with name, description, star_count, is_official, is_automated
    """
    profile = load_profile(profile_name)
    token = _get_token(profile, profile_name)

    query = params.get("query", "")
    if not query:
        return {"ok": False, "error": "query parameter is required"}

    page_size = min(params.get("page_size", 25), 100)
    page = params.get("page", 1)

    query_params = {
        "query": query,
        "page_size": page_size,
        "page": page
    }

    url = f"{API_BASE}/search/repositories/?{urlencode(query_params)}"
    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        data = result["result"]
        images = data.get("results", [])
        return {
            "ok": True,
            "data": {
                "images": [
                    {
                        "name": img.get("repo_name", img.get("name", "")),
                        "description": img.get("short_description", img.get("description", "")),
                        "star_count": img.get("star_count", 0),
                        "pull_count": img.get("pull_count", 0),
                        "is_official": img.get("is_official", False),
                        "is_automated": img.get("is_automated", False),
                    }
                    for img in images
                ],
                "count": data.get("count", len(images)),
                "page": page,
                "page_size": page_size,
            }
        }
    return result


def list_repos(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List repositories for a namespace (user or organization).

    Params:
        namespace (str): Username or organization (default: from profile or authenticated user)
        page_size (int): Number of results per page (default: 25, max: 100)
        page (int): Page number (default: 1)

    Returns:
        List of repositories with name, namespace, description, star_count, pull_count
    """
    profile = load_profile(profile_name)
    token = _get_token(profile, profile_name)

    namespace = params.get("namespace", profile.get("default_namespace", ""))
    if not namespace:
        # Try to get username from credentials
        username, _ = _get_credentials(profile)
        namespace = username

    page_size = min(params.get("page_size", 25), 100)
    page = params.get("page", 1)

    query_params = {
        "page_size": page_size,
        "page": page
    }

    url = f"{API_BASE}/repositories/{quote(namespace, safe='')}/?{urlencode(query_params)}"
    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        data = result["result"]
        repos = data.get("results", [])
        return {
            "ok": True,
            "data": {
                "repositories": [
                    {
                        "name": repo.get("name", ""),
                        "namespace": repo.get("namespace", namespace),
                        "description": repo.get("description", ""),
                        "star_count": repo.get("star_count", 0),
                        "pull_count": repo.get("pull_count", 0),
                        "last_updated": repo.get("last_updated"),
                        "is_private": repo.get("is_private", False),
                    }
                    for repo in repos
                ],
                "count": data.get("count", len(repos)),
                "namespace": namespace,
            }
        }
    return result


def get_repo(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a specific repository.

    Params:
        namespace (str): Username or organization (required)
        repository (str): Repository name (required)

    Returns:
        Repository details including name, description, star_count, pull_count, etc.
    """
    profile = load_profile(profile_name)
    token = _get_token(profile, profile_name)

    namespace = params.get("namespace", profile.get("default_namespace", ""))
    repository = params.get("repository", "")

    if not namespace:
        return {"ok": False, "error": "namespace parameter is required"}
    if not repository:
        return {"ok": False, "error": "repository parameter is required"}

    url = f"{API_BASE}/repositories/{quote(namespace, safe='')}/{quote(repository, safe='')}/"
    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        repo = result["result"]
        return {
            "ok": True,
            "data": {
                "name": repo.get("name", ""),
                "namespace": repo.get("namespace", namespace),
                "description": repo.get("description", ""),
                "full_description": repo.get("full_description", ""),
                "star_count": repo.get("star_count", 0),
                "pull_count": repo.get("pull_count", 0),
                "last_updated": repo.get("last_updated"),
                "is_private": repo.get("is_private", False),
                "is_automated": repo.get("is_automated", False),
                "can_edit": repo.get("can_edit", False),
                "affiliation": repo.get("affiliation"),
            }
        }
    return result


def list_tags(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List tags for a repository.

    Params:
        namespace (str): Username or organization (required)
        repository (str): Repository name (required)
        page_size (int): Number of results per page (default: 25, max: 100)
        page (int): Page number (default: 1)

    Returns:
        List of tags with name, digest, last_updated, size info
    """
    profile = load_profile(profile_name)
    token = _get_token(profile, profile_name)

    namespace = params.get("namespace", profile.get("default_namespace", ""))
    repository = params.get("repository", "")

    if not namespace:
        return {"ok": False, "error": "namespace parameter is required"}
    if not repository:
        return {"ok": False, "error": "repository parameter is required"}

    page_size = min(params.get("page_size", 25), 100)
    page = params.get("page", 1)

    query_params = {
        "page_size": page_size,
        "page": page
    }

    url = f"{API_BASE}/repositories/{quote(namespace, safe='')}/{quote(repository, safe='')}/tags/?{urlencode(query_params)}"
    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        data = result["result"]
        tags = data.get("results", [])
        return {
            "ok": True,
            "data": {
                "tags": [
                    {
                        "name": tag.get("name", ""),
                        "digest": tag.get("digest", ""),
                        "last_updated": tag.get("last_updated"),
                        "last_pushed": tag.get("tag_last_pushed"),
                        "full_size": tag.get("full_size", 0),
                        "images": [
                            {
                                "architecture": img.get("architecture", ""),
                                "os": img.get("os", ""),
                                "size": img.get("size", 0),
                                "digest": img.get("digest", ""),
                            }
                            for img in tag.get("images", [])
                        ] if tag.get("images") else [],
                    }
                    for tag in tags
                ],
                "count": data.get("count", len(tags)),
                "namespace": namespace,
                "repository": repository,
            }
        }
    return result


def get_tag(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a specific tag.

    Params:
        namespace (str): Username or organization (required)
        repository (str): Repository name (required)
        tag (str): Tag name (required)

    Returns:
        Tag details including name, digest, size, architecture info
    """
    profile = load_profile(profile_name)
    token = _get_token(profile, profile_name)

    namespace = params.get("namespace", profile.get("default_namespace", ""))
    repository = params.get("repository", "")
    tag_name = params.get("tag", "")

    if not namespace:
        return {"ok": False, "error": "namespace parameter is required"}
    if not repository:
        return {"ok": False, "error": "repository parameter is required"}
    if not tag_name:
        return {"ok": False, "error": "tag parameter is required"}

    url = f"{API_BASE}/repositories/{quote(namespace, safe='')}/{quote(repository, safe='')}/tags/{quote(tag_name, safe='')}/"
    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        tag = result["result"]
        return {
            "ok": True,
            "data": {
                "name": tag.get("name", ""),
                "digest": tag.get("digest", ""),
                "last_updated": tag.get("last_updated"),
                "last_pushed": tag.get("tag_last_pushed"),
                "full_size": tag.get("full_size", 0),
                "images": [
                    {
                        "architecture": img.get("architecture", ""),
                        "os": img.get("os", ""),
                        "os_version": img.get("os_version"),
                        "size": img.get("size", 0),
                        "digest": img.get("digest", ""),
                        "status": img.get("status", ""),
                    }
                    for img in tag.get("images", [])
                ] if tag.get("images") else [],
                "namespace": namespace,
                "repository": repository,
            }
        }
    return result


def delete_tag(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a tag from a repository.

    Params:
        namespace (str): Username or organization (required)
        repository (str): Repository name (required)
        tag (str): Tag name to delete (required)

    Returns:
        Success status

    WARNING: This action is destructive and cannot be undone!
    """
    profile = load_profile(profile_name)
    token = _get_token(profile, profile_name)

    namespace = params.get("namespace", profile.get("default_namespace", ""))
    repository = params.get("repository", "")
    tag_name = params.get("tag", "")

    if not namespace:
        return {"ok": False, "error": "namespace parameter is required"}
    if not repository:
        return {"ok": False, "error": "repository parameter is required"}
    if not tag_name:
        return {"ok": False, "error": "tag parameter is required"}

    url = f"{API_BASE}/repositories/{quote(namespace, safe='')}/{quote(repository, safe='')}/tags/{quote(tag_name, safe='')}/"
    result = _api_call(token, url, method="DELETE")

    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "deleted": True,
                "namespace": namespace,
                "repository": repository,
                "tag": tag_name,
            }
        }
    return result


def get_rate_limits(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get current rate limit status for Docker Hub.

    This makes a lightweight API call to retrieve rate limit headers.

    Params:
        None required

    Returns:
        Rate limit information including limit, remaining, and reset time
    """
    profile = load_profile(profile_name)
    token = _get_token(profile, profile_name)

    # Use the authenticated user endpoint as a lightweight check
    # or fall back to a minimal search
    username, _ = _get_credentials(profile)
    url = f"{API_BASE}/users/{quote(username, safe='')}/"

    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        req = Request(url, headers=headers, method="GET")

        with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            # Extract rate limit headers
            rate_limit = response.headers.get("RateLimit-Limit")
            rate_remaining = response.headers.get("RateLimit-Remaining")
            rate_reset = response.headers.get("RateLimit-Reset")

            # Also check Docker-specific headers
            docker_limit = response.headers.get("X-RateLimit-Limit")
            docker_remaining = response.headers.get("X-RateLimit-Remaining")

            return {
                "ok": True,
                "data": {
                    "authenticated": True,
                    "username": username,
                    "rate_limit": {
                        "limit": rate_limit or docker_limit,
                        "remaining": rate_remaining or docker_remaining,
                        "reset": rate_reset,
                    },
                    "note": "Authenticated users have higher rate limits than anonymous pulls"
                }
            }
    except HTTPError as e:
        # Even on error, try to extract rate limit info
        rate_limit = e.headers.get("RateLimit-Limit") if hasattr(e, 'headers') else None
        rate_remaining = e.headers.get("RateLimit-Remaining") if hasattr(e, 'headers') else None

        if rate_limit or rate_remaining:
            return {
                "ok": True,
                "data": {
                    "authenticated": True,
                    "rate_limit": {
                        "limit": rate_limit,
                        "remaining": rate_remaining,
                    }
                }
            }

        error_body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_webhooks(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List webhooks for a repository.

    Params:
        namespace (str): Username or organization (required)
        repository (str): Repository name (required)

    Returns:
        List of webhooks with id, name, hook_url, etc.

    Note: Requires admin access to the repository.
    """
    profile = load_profile(profile_name)
    token = _get_token(profile, profile_name)

    namespace = params.get("namespace", profile.get("default_namespace", ""))
    repository = params.get("repository", "")

    if not namespace:
        return {"ok": False, "error": "namespace parameter is required"}
    if not repository:
        return {"ok": False, "error": "repository parameter is required"}

    url = f"{API_BASE}/repositories/{quote(namespace, safe='')}/{quote(repository, safe='')}/webhooks/"
    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        data = result["result"]
        webhooks = data.get("results", []) if isinstance(data, dict) else data if isinstance(data, list) else []
        return {
            "ok": True,
            "data": {
                "webhooks": [
                    {
                        "id": hook.get("id"),
                        "name": hook.get("name", ""),
                        "hook_url": hook.get("hook_url", ""),
                        "active": hook.get("active", True),
                        "expect_final_callback": hook.get("expect_final_callback", False),
                        "created_at": hook.get("created"),
                        "last_updated": hook.get("last_updated"),
                    }
                    for hook in webhooks
                ],
                "namespace": namespace,
                "repository": repository,
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "search": search,
    "list_repos": list_repos,
    "get_repo": get_repo,
    "list_tags": list_tags,
    "get_tag": get_tag,
    "delete_tag": delete_tag,
    "get_rate_limits": get_rate_limits,
    "list_webhooks": list_webhooks,
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
        logger.info(f"Executing dockerhub.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
