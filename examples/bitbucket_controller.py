"""
Bitbucket Controller for TinyHive

A controller for interacting with Bitbucket Cloud API 2.0.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "username": "your-bitbucket-username",
    "token_env": "BITBUCKET_APP_PASSWORD",
    "default_workspace": "your-workspace"
}

Authentication:
--------------
- App Password: Set BITBUCKET_APP_PASSWORD environment variable
  (Create at: Bitbucket Settings > Personal settings > App passwords)
- Access Token: Set BITBUCKET_ACCESS_TOKEN environment variable
  (For OAuth2 Bearer token authentication)

Required Permissions (App Password):
-----------------------------------
- list_repos: Repositories:Read
- get_repo: Repositories:Read
- list_pull_requests: Pull requests:Read
- create_pull_request: Pull requests:Write
- get_pull_request: Pull requests:Read
- list_commits: Repositories:Read
- get_file: Repositories:Read
- list_pipelines: Pipelines:Read

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
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger("tinyhive.controller.bitbucket")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Bitbucket Cloud API base URL
API_BASE = "https://api.bitbucket.org/2.0"

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


def list_profiles() -> List[str]:
    """List available Bitbucket profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# Authentication
# =============================================================================

def _get_auth_header(profile: Dict[str, Any]) -> Dict[str, str]:
    """
    Get authentication header for Bitbucket API.

    Supports:
    - Basic Auth with username + App Password
    - Bearer token (OAuth2 access token)
    """
    # Check for Bearer token first
    bearer_env = profile.get("bearer_token_env", "BITBUCKET_ACCESS_TOKEN")
    bearer_token = os.environ.get(bearer_env)
    if bearer_token:
        return {"Authorization": f"Bearer {bearer_token}"}

    # Fall back to Basic Auth with App Password
    username = profile.get("username")
    if not username:
        raise ValueError("Profile must specify 'username' for Basic Auth")

    token_env = profile.get("token_env", "BITBUCKET_APP_PASSWORD")
    app_password = os.environ.get(token_env)
    if not app_password:
        raise ValueError(
            f"Environment variable '{token_env}' not set. "
            "Create an App Password at: Bitbucket Settings > Personal settings > App passwords"
        )

    credentials = f"{username}:{app_password}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {encoded}"}


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    profile: Dict[str, Any],
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Bitbucket API call."""
    url = f"{API_BASE}{endpoint}"

    headers = _get_auth_header(profile)
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "application/json"

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
            if "error" in error_data:
                error_message = error_data["error"].get("message", error_body[:500])
            else:
                error_message = error_body[:500]
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Bitbucket API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Bitbucket API call")
        return {"ok": False, "error": str(e)}


def _api_call_raw(
    profile: Dict[str, Any],
    endpoint: str,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Bitbucket API call returning raw content."""
    url = f"{API_BASE}{endpoint}"

    headers = _get_auth_header(profile)

    try:
        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=timeout) as response:
            content = response.read()
            # Try to decode as UTF-8, fall back to base64
            try:
                return {"ok": True, "data": {"content": content.decode("utf-8"), "encoding": "utf-8"}}
            except UnicodeDecodeError:
                return {"ok": True, "data": {"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except URLError as e:
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def list_repos(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List repositories in a workspace.

    Params:
        workspace (str): Workspace slug (default: from profile)
        role (str): Filter by role: owner, admin, contributor, member (optional)
        sort (str): Sort field, e.g., '-updated_on' for descending (optional)
        page (int): Page number (optional)
        pagelen (int): Results per page, max 100 (optional)
    """
    profile = load_profile(profile_name)

    workspace = params.get("workspace", profile.get("default_workspace"))
    if not workspace:
        return {"ok": False, "error": "workspace required (in profile or params)"}

    query_params = {}
    if params.get("role"):
        query_params["role"] = params["role"]
    if params.get("sort"):
        query_params["sort"] = params["sort"]
    if params.get("page"):
        query_params["page"] = params["page"]
    if params.get("pagelen"):
        query_params["pagelen"] = min(params["pagelen"], 100)

    endpoint = f"/repositories/{quote(workspace, safe='')}"
    if query_params:
        endpoint += f"?{urlencode(query_params)}"

    result = _api_call(profile, endpoint)

    if result.get("ok") and "data" in result:
        data = result["data"]
        repos = data.get("values", [])
        return {
            "ok": True,
            "data": {
                "repositories": [
                    {
                        "uuid": r.get("uuid"),
                        "name": r.get("name"),
                        "full_name": r.get("full_name"),
                        "slug": r.get("slug"),
                        "description": r.get("description"),
                        "is_private": r.get("is_private"),
                        "language": r.get("language"),
                        "created_on": r.get("created_on"),
                        "updated_on": r.get("updated_on"),
                        "size": r.get("size"),
                        "mainbranch": r.get("mainbranch", {}).get("name") if r.get("mainbranch") else None,
                    }
                    for r in repos
                ],
                "page": data.get("page"),
                "pagelen": data.get("pagelen"),
                "size": data.get("size"),
                "next": data.get("next"),
            }
        }
    return result


def get_repo(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get repository details.

    Params:
        workspace (str): Workspace slug (default: from profile)
        repo_slug (str): Repository slug (required)
    """
    profile = load_profile(profile_name)

    workspace = params.get("workspace", profile.get("default_workspace"))
    if not workspace:
        return {"ok": False, "error": "workspace required (in profile or params)"}

    repo_slug = params.get("repo_slug")
    if not repo_slug:
        return {"ok": False, "error": "repo_slug required"}

    endpoint = f"/repositories/{quote(workspace, safe='')}/{quote(repo_slug, safe='')}"
    result = _api_call(profile, endpoint)

    if result.get("ok") and "data" in result:
        r = result["data"]
        return {
            "ok": True,
            "data": {
                "uuid": r.get("uuid"),
                "name": r.get("name"),
                "full_name": r.get("full_name"),
                "slug": r.get("slug"),
                "description": r.get("description"),
                "is_private": r.get("is_private"),
                "language": r.get("language"),
                "created_on": r.get("created_on"),
                "updated_on": r.get("updated_on"),
                "size": r.get("size"),
                "mainbranch": r.get("mainbranch", {}).get("name") if r.get("mainbranch") else None,
                "owner": r.get("owner", {}).get("display_name"),
                "project": r.get("project", {}).get("name") if r.get("project") else None,
                "fork_policy": r.get("fork_policy"),
                "has_issues": r.get("has_issues"),
                "has_wiki": r.get("has_wiki"),
            }
        }
    return result


def list_pull_requests(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List pull requests for a repository.

    Params:
        workspace (str): Workspace slug (default: from profile)
        repo_slug (str): Repository slug (required)
        state (str): Filter by state: OPEN, MERGED, DECLINED, SUPERSEDED (default: OPEN)
        page (int): Page number (optional)
        pagelen (int): Results per page, max 50 (optional)
    """
    profile = load_profile(profile_name)

    workspace = params.get("workspace", profile.get("default_workspace"))
    if not workspace:
        return {"ok": False, "error": "workspace required (in profile or params)"}

    repo_slug = params.get("repo_slug")
    if not repo_slug:
        return {"ok": False, "error": "repo_slug required"}

    query_params = {}
    state = params.get("state", "OPEN")
    if state:
        query_params["state"] = state.upper()
    if params.get("page"):
        query_params["page"] = params["page"]
    if params.get("pagelen"):
        query_params["pagelen"] = min(params["pagelen"], 50)

    endpoint = f"/repositories/{quote(workspace, safe='')}/{quote(repo_slug, safe='')}/pullrequests"
    if query_params:
        endpoint += f"?{urlencode(query_params)}"

    result = _api_call(profile, endpoint)

    if result.get("ok") and "data" in result:
        data = result["data"]
        prs = data.get("values", [])
        return {
            "ok": True,
            "data": {
                "pull_requests": [
                    {
                        "id": pr.get("id"),
                        "title": pr.get("title"),
                        "description": pr.get("description"),
                        "state": pr.get("state"),
                        "author": pr.get("author", {}).get("display_name"),
                        "source_branch": pr.get("source", {}).get("branch", {}).get("name"),
                        "destination_branch": pr.get("destination", {}).get("branch", {}).get("name"),
                        "created_on": pr.get("created_on"),
                        "updated_on": pr.get("updated_on"),
                        "comment_count": pr.get("comment_count"),
                        "task_count": pr.get("task_count"),
                    }
                    for pr in prs
                ],
                "page": data.get("page"),
                "pagelen": data.get("pagelen"),
                "size": data.get("size"),
                "next": data.get("next"),
            }
        }
    return result


def create_pull_request(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a pull request.

    Params:
        workspace (str): Workspace slug (default: from profile)
        repo_slug (str): Repository slug (required)
        title (str): PR title (required)
        source_branch (str): Source branch name (required)
        dest_branch (str): Destination branch name (required)
        description (str): PR description (optional)
        close_source_branch (bool): Close source branch on merge (default: False)
        reviewers (list): List of reviewer UUIDs (optional)
    """
    profile = load_profile(profile_name)

    workspace = params.get("workspace", profile.get("default_workspace"))
    if not workspace:
        return {"ok": False, "error": "workspace required (in profile or params)"}

    repo_slug = params.get("repo_slug")
    if not repo_slug:
        return {"ok": False, "error": "repo_slug required"}

    title = params.get("title")
    if not title:
        return {"ok": False, "error": "title required"}

    source_branch = params.get("source_branch")
    if not source_branch:
        return {"ok": False, "error": "source_branch required"}

    dest_branch = params.get("dest_branch")
    if not dest_branch:
        return {"ok": False, "error": "dest_branch required"}

    pr_data = {
        "title": title,
        "source": {
            "branch": {"name": source_branch}
        },
        "destination": {
            "branch": {"name": dest_branch}
        }
    }

    if params.get("description"):
        pr_data["description"] = params["description"]

    if params.get("close_source_branch"):
        pr_data["close_source_branch"] = True

    if params.get("reviewers"):
        pr_data["reviewers"] = [{"uuid": uuid} for uuid in params["reviewers"]]

    endpoint = f"/repositories/{quote(workspace, safe='')}/{quote(repo_slug, safe='')}/pullrequests"
    result = _api_call(profile, endpoint, method="POST", data=pr_data)

    if result.get("ok") and "data" in result:
        pr = result["data"]
        return {
            "ok": True,
            "data": {
                "id": pr.get("id"),
                "title": pr.get("title"),
                "description": pr.get("description"),
                "state": pr.get("state"),
                "author": pr.get("author", {}).get("display_name"),
                "source_branch": pr.get("source", {}).get("branch", {}).get("name"),
                "destination_branch": pr.get("destination", {}).get("branch", {}).get("name"),
                "created_on": pr.get("created_on"),
                "links": {
                    "html": pr.get("links", {}).get("html", {}).get("href"),
                }
            }
        }
    return result


def get_pull_request(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get pull request details.

    Params:
        workspace (str): Workspace slug (default: from profile)
        repo_slug (str): Repository slug (required)
        pr_id (int): Pull request ID (required)
    """
    profile = load_profile(profile_name)

    workspace = params.get("workspace", profile.get("default_workspace"))
    if not workspace:
        return {"ok": False, "error": "workspace required (in profile or params)"}

    repo_slug = params.get("repo_slug")
    if not repo_slug:
        return {"ok": False, "error": "repo_slug required"}

    pr_id = params.get("pr_id")
    if pr_id is None:
        return {"ok": False, "error": "pr_id required"}

    endpoint = f"/repositories/{quote(workspace, safe='')}/{quote(repo_slug, safe='')}/pullrequests/{pr_id}"
    result = _api_call(profile, endpoint)

    if result.get("ok") and "data" in result:
        pr = result["data"]
        return {
            "ok": True,
            "data": {
                "id": pr.get("id"),
                "title": pr.get("title"),
                "description": pr.get("description"),
                "state": pr.get("state"),
                "author": pr.get("author", {}).get("display_name"),
                "source_branch": pr.get("source", {}).get("branch", {}).get("name"),
                "source_commit": pr.get("source", {}).get("commit", {}).get("hash"),
                "destination_branch": pr.get("destination", {}).get("branch", {}).get("name"),
                "destination_commit": pr.get("destination", {}).get("commit", {}).get("hash"),
                "merge_commit": pr.get("merge_commit", {}).get("hash") if pr.get("merge_commit") else None,
                "close_source_branch": pr.get("close_source_branch"),
                "created_on": pr.get("created_on"),
                "updated_on": pr.get("updated_on"),
                "comment_count": pr.get("comment_count"),
                "task_count": pr.get("task_count"),
                "reviewers": [
                    {"display_name": r.get("display_name"), "uuid": r.get("uuid")}
                    for r in pr.get("reviewers", [])
                ],
                "participants": [
                    {
                        "display_name": p.get("user", {}).get("display_name"),
                        "role": p.get("role"),
                        "approved": p.get("approved"),
                    }
                    for p in pr.get("participants", [])
                ],
                "links": {
                    "html": pr.get("links", {}).get("html", {}).get("href"),
                    "diff": pr.get("links", {}).get("diff", {}).get("href"),
                }
            }
        }
    return result


def list_commits(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List commits in a repository.

    Params:
        workspace (str): Workspace slug (default: from profile)
        repo_slug (str): Repository slug (required)
        branch (str): Branch name or commit hash (optional, default: default branch)
        path (str): Filter commits affecting this path (optional)
        page (int): Page number (optional)
        pagelen (int): Results per page, max 100 (optional)
    """
    profile = load_profile(profile_name)

    workspace = params.get("workspace", profile.get("default_workspace"))
    if not workspace:
        return {"ok": False, "error": "workspace required (in profile or params)"}

    repo_slug = params.get("repo_slug")
    if not repo_slug:
        return {"ok": False, "error": "repo_slug required"}

    # Build endpoint - branch can be included in path
    endpoint = f"/repositories/{quote(workspace, safe='')}/{quote(repo_slug, safe='')}/commits"

    branch = params.get("branch")
    if branch:
        endpoint += f"/{quote(branch, safe='')}"

    query_params = {}
    if params.get("path"):
        query_params["path"] = params["path"]
    if params.get("page"):
        query_params["page"] = params["page"]
    if params.get("pagelen"):
        query_params["pagelen"] = min(params["pagelen"], 100)

    if query_params:
        endpoint += f"?{urlencode(query_params)}"

    result = _api_call(profile, endpoint)

    if result.get("ok") and "data" in result:
        data = result["data"]
        commits = data.get("values", [])
        return {
            "ok": True,
            "data": {
                "commits": [
                    {
                        "hash": c.get("hash"),
                        "message": c.get("message"),
                        "author": c.get("author", {}).get("raw"),
                        "author_user": c.get("author", {}).get("user", {}).get("display_name") if c.get("author", {}).get("user") else None,
                        "date": c.get("date"),
                        "parents": [p.get("hash") for p in c.get("parents", [])],
                    }
                    for c in commits
                ],
                "page": data.get("page"),
                "pagelen": data.get("pagelen"),
                "next": data.get("next"),
            }
        }
    return result


def get_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get file content from a repository.

    Params:
        workspace (str): Workspace slug (default: from profile)
        repo_slug (str): Repository slug (required)
        path (str): File path in the repository (required)
        commit (str): Commit hash or branch name (optional, default: HEAD)
    """
    profile = load_profile(profile_name)

    workspace = params.get("workspace", profile.get("default_workspace"))
    if not workspace:
        return {"ok": False, "error": "workspace required (in profile or params)"}

    repo_slug = params.get("repo_slug")
    if not repo_slug:
        return {"ok": False, "error": "repo_slug required"}

    file_path = params.get("path")
    if not file_path:
        return {"ok": False, "error": "path required"}

    commit = params.get("commit", "HEAD")

    # Use the src endpoint to get file content
    endpoint = f"/repositories/{quote(workspace, safe='')}/{quote(repo_slug, safe='')}/src/{quote(commit, safe='')}/{quote(file_path, safe='')}"

    result = _api_call_raw(profile, endpoint)

    if result.get("ok") and "data" in result:
        return {
            "ok": True,
            "data": {
                "path": file_path,
                "commit": commit,
                "content": result["data"]["content"],
                "encoding": result["data"]["encoding"],
            }
        }
    return result


def list_pipelines(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List pipelines for a repository.

    Params:
        workspace (str): Workspace slug (default: from profile)
        repo_slug (str): Repository slug (required)
        page (int): Page number (optional)
        pagelen (int): Results per page, max 100 (optional)
        sort (str): Sort field, e.g., '-created_on' (optional)
    """
    profile = load_profile(profile_name)

    workspace = params.get("workspace", profile.get("default_workspace"))
    if not workspace:
        return {"ok": False, "error": "workspace required (in profile or params)"}

    repo_slug = params.get("repo_slug")
    if not repo_slug:
        return {"ok": False, "error": "repo_slug required"}

    query_params = {}
    if params.get("page"):
        query_params["page"] = params["page"]
    if params.get("pagelen"):
        query_params["pagelen"] = min(params["pagelen"], 100)
    if params.get("sort"):
        query_params["sort"] = params["sort"]

    endpoint = f"/repositories/{quote(workspace, safe='')}/{quote(repo_slug, safe='')}/pipelines/"
    if query_params:
        endpoint += f"?{urlencode(query_params)}"

    result = _api_call(profile, endpoint)

    if result.get("ok") and "data" in result:
        data = result["data"]
        pipelines = data.get("values", [])
        return {
            "ok": True,
            "data": {
                "pipelines": [
                    {
                        "uuid": p.get("uuid"),
                        "build_number": p.get("build_number"),
                        "state": _extract_pipeline_state(p.get("state", {})),
                        "trigger": p.get("trigger", {}).get("name"),
                        "target": {
                            "type": p.get("target", {}).get("type"),
                            "ref_name": p.get("target", {}).get("ref_name"),
                            "commit": p.get("target", {}).get("commit", {}).get("hash"),
                        } if p.get("target") else None,
                        "creator": p.get("creator", {}).get("display_name") if p.get("creator") else None,
                        "created_on": p.get("created_on"),
                        "completed_on": p.get("completed_on"),
                        "duration_in_seconds": p.get("duration_in_seconds"),
                    }
                    for p in pipelines
                ],
                "page": data.get("page"),
                "pagelen": data.get("pagelen"),
                "size": data.get("size"),
                "next": data.get("next"),
            }
        }
    return result


def _extract_pipeline_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Extract pipeline state information."""
    state_name = state.get("name", "UNKNOWN")
    result_info = {}

    if "result" in state:
        result_info["result"] = state["result"].get("name")
    if "stage" in state:
        result_info["stage"] = state["stage"].get("name")

    return {"name": state_name, **result_info}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_repos": list_repos,
    "get_repo": get_repo,
    "list_pull_requests": list_pull_requests,
    "create_pull_request": create_pull_request,
    "get_pull_request": get_pull_request,
    "list_commits": list_commits,
    "get_file": get_file,
    "list_pipelines": list_pipelines,
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
        logger.info(f"Executing bitbucket.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
