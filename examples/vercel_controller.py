"""
Vercel Controller for TinyHive

A controller for interacting with the Vercel REST API for managing
projects, deployments, domains, and environment variables.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "team_id": "team_xxxxxxxxxxxx"  // Optional: Vercel team ID
}

Environment Variables:
---------------------
VERCEL_ACCESS_TOKEN: Vercel API access token (required)
    Generate at: https://vercel.com/account/tokens

Method IDs:
----------
controller.vercel.{profile}.list_projects
controller.vercel.{profile}.get_project
controller.vercel.{profile}.list_deployments
controller.vercel.{profile}.get_deployment
controller.vercel.{profile}.create_deployment
controller.vercel.{profile}.cancel_deployment
controller.vercel.{profile}.list_domains
controller.vercel.{profile}.get_env_vars

Dependencies:
------------
None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger("tinyhive.controller.vercel")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# Vercel API base URL
VERCEL_API_BASE = "https://api.vercel.com"

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with Vercel configuration.")
    return json.loads(path.read_text())


# =============================================================================
# HTTP Helpers
# =============================================================================

def _get_access_token() -> str:
    """Get Vercel access token from environment."""
    token = os.environ.get("VERCEL_ACCESS_TOKEN", "")
    if not token:
        raise ValueError(
            "VERCEL_ACCESS_TOKEN environment variable not set. "
            "Generate a token at: https://vercel.com/account/tokens"
        )
    return token


def _api_call(
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    timeout: int = DEFAULT_TIMEOUT,
    team_id: Optional[str] = None
) -> Dict[str, Any]:
    """Make an authenticated Vercel API call."""
    token = _get_access_token()

    # Add teamId query parameter if provided
    if team_id:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}teamId={team_id}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("error", {}).get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Vercel API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Vercel API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Project Actions
# =============================================================================

def list_projects(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List projects in the Vercel account/team.

    Params:
        limit (int): Maximum number of projects to return (default: 20)
    """
    profile = load_profile(profile_name)
    team_id = profile.get("team_id")

    limit = params.get("limit", 20)

    query_params = {"limit": limit}
    url = f"{VERCEL_API_BASE}/v9/projects?{urlencode(query_params)}"

    result = _api_call(url, team_id=team_id)

    if result.get("ok") and "result" in result:
        projects = result["result"].get("projects", [])
        return {
            "ok": True,
            "data": {
                "projects": [
                    {
                        "id": p.get("id"),
                        "name": p.get("name"),
                        "framework": p.get("framework"),
                        "created_at": p.get("createdAt"),
                        "updated_at": p.get("updatedAt"),
                        "latest_deployments": [
                            {
                                "id": d.get("id"),
                                "url": d.get("url"),
                                "state": d.get("state"),
                                "created_at": d.get("createdAt")
                            }
                            for d in p.get("latestDeployments", [])[:3]
                        ]
                    }
                    for p in projects
                ],
                "count": len(projects)
            }
        }
    return result


def get_project(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific project.

    Params:
        project_id (str): Project ID or name (required)
    """
    profile = load_profile(profile_name)
    team_id = profile.get("team_id")

    project_id = params.get("project_id", "")
    if not project_id:
        return {"ok": False, "error": "project_id is required"}

    url = f"{VERCEL_API_BASE}/v9/projects/{project_id}"

    result = _api_call(url, team_id=team_id)

    if result.get("ok") and "result" in result:
        p = result["result"]
        return {
            "ok": True,
            "data": {
                "id": p.get("id"),
                "name": p.get("name"),
                "framework": p.get("framework"),
                "node_version": p.get("nodeVersion"),
                "build_command": p.get("buildCommand"),
                "output_directory": p.get("outputDirectory"),
                "root_directory": p.get("rootDirectory"),
                "install_command": p.get("installCommand"),
                "dev_command": p.get("devCommand"),
                "created_at": p.get("createdAt"),
                "updated_at": p.get("updatedAt"),
                "account_id": p.get("accountId"),
                "link": p.get("link"),
                "latest_deployments": [
                    {
                        "id": d.get("id"),
                        "url": d.get("url"),
                        "state": d.get("state"),
                        "created_at": d.get("createdAt")
                    }
                    for d in p.get("latestDeployments", [])
                ]
            }
        }
    return result


# =============================================================================
# Deployment Actions
# =============================================================================

def list_deployments(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List deployments for a project.

    Params:
        project_id (str): Project ID or name (optional, lists all if not provided)
        limit (int): Maximum number of deployments to return (default: 20)
        state (str): Filter by state: BUILDING, ERROR, INITIALIZING, QUEUED, READY, CANCELED (optional)
    """
    profile = load_profile(profile_name)
    team_id = profile.get("team_id")

    query_params = {"limit": params.get("limit", 20)}

    project_id = params.get("project_id")
    if project_id:
        query_params["projectId"] = project_id

    state = params.get("state")
    if state:
        query_params["state"] = state.upper()

    url = f"{VERCEL_API_BASE}/v6/deployments?{urlencode(query_params)}"

    result = _api_call(url, team_id=team_id)

    if result.get("ok") and "result" in result:
        deployments = result["result"].get("deployments", [])
        return {
            "ok": True,
            "data": {
                "deployments": [
                    {
                        "id": d.get("uid"),
                        "name": d.get("name"),
                        "url": d.get("url"),
                        "state": d.get("state"),
                        "created_at": d.get("createdAt"),
                        "ready_at": d.get("ready"),
                        "source": d.get("source"),
                        "target": d.get("target"),
                        "creator": {
                            "uid": d.get("creator", {}).get("uid"),
                            "username": d.get("creator", {}).get("username")
                        } if d.get("creator") else None
                    }
                    for d in deployments
                ],
                "count": len(deployments)
            }
        }
    return result


def get_deployment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific deployment.

    Params:
        deployment_id (str): Deployment ID or URL (required)
    """
    profile = load_profile(profile_name)
    team_id = profile.get("team_id")

    deployment_id = params.get("deployment_id", "")
    if not deployment_id:
        return {"ok": False, "error": "deployment_id is required"}

    url = f"{VERCEL_API_BASE}/v13/deployments/{deployment_id}"

    result = _api_call(url, team_id=team_id)

    if result.get("ok") and "result" in result:
        d = result["result"]
        return {
            "ok": True,
            "data": {
                "id": d.get("id"),
                "name": d.get("name"),
                "url": d.get("url"),
                "state": d.get("readyState"),
                "created_at": d.get("createdAt"),
                "ready_at": d.get("ready"),
                "building_at": d.get("buildingAt"),
                "source": d.get("source"),
                "target": d.get("target"),
                "alias": d.get("alias", []),
                "git_source": d.get("gitSource"),
                "meta": d.get("meta"),
                "regions": d.get("regions"),
                "routes": d.get("routes"),
                "creator": {
                    "uid": d.get("creator", {}).get("uid"),
                    "username": d.get("creator", {}).get("username"),
                    "email": d.get("creator", {}).get("email")
                } if d.get("creator") else None
            }
        }
    return result


def create_deployment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new deployment.

    Params:
        name (str): Project name (required)
        git_source (dict): Git source configuration (required)
            - type (str): "github", "gitlab", or "bitbucket"
            - repo (str): Repository in format "owner/repo"
            - ref (str): Branch, tag, or commit SHA
    """
    profile = load_profile(profile_name)
    team_id = profile.get("team_id")

    name = params.get("name", "")
    git_source = params.get("git_source", {})

    if not name:
        return {"ok": False, "error": "name is required"}
    if not git_source:
        return {"ok": False, "error": "git_source is required"}

    # Validate git_source structure
    git_type = git_source.get("type", "")
    repo = git_source.get("repo", "")
    ref = git_source.get("ref", "")

    if not git_type or git_type not in ("github", "gitlab", "bitbucket"):
        return {"ok": False, "error": "git_source.type must be 'github', 'gitlab', or 'bitbucket'"}
    if not repo:
        return {"ok": False, "error": "git_source.repo is required"}
    if not ref:
        return {"ok": False, "error": "git_source.ref is required"}

    # Build request body
    body = {
        "name": name,
        "gitSource": {
            "type": git_type,
            "repo": repo,
            "ref": ref
        }
    }

    url = f"{VERCEL_API_BASE}/v13/deployments"

    result = _api_call(
        url,
        method="POST",
        data=json.dumps(body).encode("utf-8"),
        team_id=team_id
    )

    if result.get("ok") and "result" in result:
        d = result["result"]
        return {
            "ok": True,
            "data": {
                "id": d.get("id"),
                "name": d.get("name"),
                "url": d.get("url"),
                "state": d.get("readyState"),
                "created_at": d.get("createdAt")
            }
        }
    return result


def cancel_deployment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cancel a deployment that is currently building.

    Params:
        deployment_id (str): Deployment ID (required)
    """
    profile = load_profile(profile_name)
    team_id = profile.get("team_id")

    deployment_id = params.get("deployment_id", "")
    if not deployment_id:
        return {"ok": False, "error": "deployment_id is required"}

    url = f"{VERCEL_API_BASE}/v12/deployments/{deployment_id}/cancel"

    result = _api_call(url, method="PATCH", team_id=team_id)

    if result.get("ok") and "result" in result:
        d = result["result"]
        return {
            "ok": True,
            "data": {
                "id": d.get("id"),
                "name": d.get("name"),
                "url": d.get("url"),
                "state": d.get("readyState"),
                "canceled_at": d.get("canceledAt")
            }
        }
    return result


# =============================================================================
# Domain Actions
# =============================================================================

def list_domains(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List domains associated with a project.

    Params:
        project_id (str): Project ID or name (required)
    """
    profile = load_profile(profile_name)
    team_id = profile.get("team_id")

    project_id = params.get("project_id", "")
    if not project_id:
        return {"ok": False, "error": "project_id is required"}

    url = f"{VERCEL_API_BASE}/v9/projects/{project_id}/domains"

    result = _api_call(url, team_id=team_id)

    if result.get("ok") and "result" in result:
        domains = result["result"].get("domains", [])
        return {
            "ok": True,
            "data": {
                "domains": [
                    {
                        "name": d.get("name"),
                        "apex_name": d.get("apexName"),
                        "project_id": d.get("projectId"),
                        "redirect": d.get("redirect"),
                        "redirect_status_code": d.get("redirectStatusCode"),
                        "git_branch": d.get("gitBranch"),
                        "created_at": d.get("createdAt"),
                        "updated_at": d.get("updatedAt"),
                        "verified": d.get("verified")
                    }
                    for d in domains
                ],
                "count": len(domains)
            }
        }
    return result


# =============================================================================
# Environment Variable Actions
# =============================================================================

def get_env_vars(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get environment variables for a project.

    Params:
        project_id (str): Project ID or name (required)
    """
    profile = load_profile(profile_name)
    team_id = profile.get("team_id")

    project_id = params.get("project_id", "")
    if not project_id:
        return {"ok": False, "error": "project_id is required"}

    url = f"{VERCEL_API_BASE}/v9/projects/{project_id}/env"

    result = _api_call(url, team_id=team_id)

    if result.get("ok") and "result" in result:
        env_vars = result["result"].get("envs", [])
        return {
            "ok": True,
            "data": {
                "env_vars": [
                    {
                        "id": e.get("id"),
                        "key": e.get("key"),
                        "value": e.get("value"),
                        "type": e.get("type"),
                        "target": e.get("target"),
                        "git_branch": e.get("gitBranch"),
                        "created_at": e.get("createdAt"),
                        "updated_at": e.get("updatedAt")
                    }
                    for e in env_vars
                ],
                "count": len(env_vars)
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_projects": list_projects,
    "get_project": get_project,
    "list_deployments": list_deployments,
    "get_deployment": get_deployment,
    "create_deployment": create_deployment,
    "cancel_deployment": cancel_deployment,
    "list_domains": list_domains,
    "get_env_vars": get_env_vars,
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
        logger.info(f"Executing vercel.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
