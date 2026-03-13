"""Example: GitLab controller — Projects, Issues, Merge Requests integration.

This is a TinyHive controller for GitLab API v4.
Requires a Personal Access Token (PAT) set in environment.

Method IDs:
  controller.gitlab.{profile}.list_projects
  controller.gitlab.{profile}.get_project
  controller.gitlab.{profile}.list_issues
  controller.gitlab.{profile}.create_issue
  controller.gitlab.{profile}.list_mrs
  controller.gitlab.{profile}.create_mr
  controller.gitlab.{profile}.add_comment
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote, urlencode

log = logging.getLogger("tinyhive.controller.gitlab")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

DEFAULT_BASE_URL = "https://gitlab.com/api/v4"


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'")
    return json.loads(path.read_text())


def _get_access_token(profile: Dict[str, Any]) -> str:
    """Get GitLab Personal Access Token from environment."""
    env_var = profile.get("token_env", "GITLAB_PAT")
    token = os.environ.get(env_var, "")
    if not token:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return token


def _get_base_url(profile: Dict[str, Any]) -> str:
    """Get GitLab API base URL from profile or use default."""
    return profile.get("base_url", DEFAULT_BASE_URL).rstrip("/")


def _encode_project_id(project_id: Any) -> str:
    """URL-encode a project ID (handles namespace/project paths)."""
    if isinstance(project_id, int):
        return str(project_id)
    # For paths like "namespace/project", URL-encode the entire string
    return quote(str(project_id), safe="")


def _api_call(
    token: str,
    url: str,
    method: str = "GET",
    data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Make a GitLab API call."""
    headers = {
        "PRIVATE-TOKEN": token,
        "Content-Type": "application/json",
    }

    body = json.dumps(data).encode("utf-8") if data else None

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=30) as response:
            response_data = response.read().decode("utf-8")
            if response_data:
                return {"ok": True, "data": json.loads(response_data)}
            return {"ok": True, "data": None}
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {body[:500]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Project Actions
# ---------------------------------------------------------------------------

def list_projects(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List GitLab projects with filtering.

    Params:
        - owned: If True, limit to projects owned by current user (default: False)
        - membership: If True, limit to projects user is a member of (default: False)
        - search: Search term to filter projects by name
        - visibility: Filter by visibility (public, internal, private)
        - per_page: Number of results per page (default: 20, max: 100)
        - page: Page number (default: 1)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)

    query_params = {}

    if params.get("owned"):
        query_params["owned"] = "true"
    if params.get("membership"):
        query_params["membership"] = "true"
    if params.get("search"):
        query_params["search"] = params["search"]
    if params.get("visibility"):
        query_params["visibility"] = params["visibility"]

    query_params["per_page"] = params.get("per_page", 20)
    query_params["page"] = params.get("page", 1)

    url = f"{base_url}/projects"
    if query_params:
        url = f"{url}?{urlencode(query_params)}"

    return _api_call(token, url)


def get_project(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get a single project by ID or namespace/project path.

    Params:
        - project_id: Project ID (integer) or full path (e.g., "namespace/project")
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)

    project_id = params.get("project_id")
    if not project_id:
        return {"ok": False, "error": "project_id is required"}

    encoded_id = _encode_project_id(project_id)
    url = f"{base_url}/projects/{encoded_id}"

    return _api_call(token, url)


# ---------------------------------------------------------------------------
# Issue Actions
# ---------------------------------------------------------------------------

def list_issues(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List issues for a project with filtering.

    Params:
        - project_id: Project ID or path (required)
        - state: Filter by state (opened, closed, all) (default: all)
        - labels: Comma-separated list of label names
        - milestone: Milestone title to filter by
        - assignee_id: Filter by assignee user ID
        - author_id: Filter by author user ID
        - search: Search in title and description
        - per_page: Number of results per page (default: 20, max: 100)
        - page: Page number (default: 1)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)

    project_id = params.get("project_id")
    if not project_id:
        return {"ok": False, "error": "project_id is required"}

    encoded_id = _encode_project_id(project_id)

    query_params = {}

    if params.get("state"):
        query_params["state"] = params["state"]
    if params.get("labels"):
        query_params["labels"] = params["labels"]
    if params.get("milestone"):
        query_params["milestone"] = params["milestone"]
    if params.get("assignee_id"):
        query_params["assignee_id"] = params["assignee_id"]
    if params.get("author_id"):
        query_params["author_id"] = params["author_id"]
    if params.get("search"):
        query_params["search"] = params["search"]

    query_params["per_page"] = params.get("per_page", 20)
    query_params["page"] = params.get("page", 1)

    url = f"{base_url}/projects/{encoded_id}/issues"
    if query_params:
        url = f"{url}?{urlencode(query_params)}"

    return _api_call(token, url)


def create_issue(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new issue in a project.

    Params:
        - project_id: Project ID or path (required)
        - title: Issue title (required)
        - description: Issue description/body
        - labels: Comma-separated list of label names
        - assignee_ids: List of user IDs to assign
        - milestone_id: Milestone ID to associate
        - confidential: If True, mark issue as confidential (default: False)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)

    project_id = params.get("project_id")
    title = params.get("title")

    if not project_id:
        return {"ok": False, "error": "project_id is required"}
    if not title:
        return {"ok": False, "error": "title is required"}

    encoded_id = _encode_project_id(project_id)

    issue_data = {"title": title}

    if params.get("description"):
        issue_data["description"] = params["description"]
    if params.get("labels"):
        issue_data["labels"] = params["labels"]
    if params.get("assignee_ids"):
        issue_data["assignee_ids"] = params["assignee_ids"]
    if params.get("milestone_id"):
        issue_data["milestone_id"] = params["milestone_id"]
    if params.get("confidential"):
        issue_data["confidential"] = True

    url = f"{base_url}/projects/{encoded_id}/issues"

    return _api_call(token, url, method="POST", data=issue_data)


# ---------------------------------------------------------------------------
# Merge Request Actions
# ---------------------------------------------------------------------------

def list_mrs(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List merge requests for a project with filtering.

    Params:
        - project_id: Project ID or path (required)
        - state: Filter by state (opened, closed, merged, all) (default: all)
        - labels: Comma-separated list of label names
        - milestone: Milestone title to filter by
        - author_id: Filter by author user ID
        - assignee_id: Filter by assignee user ID
        - source_branch: Filter by source branch
        - target_branch: Filter by target branch
        - search: Search in title and description
        - per_page: Number of results per page (default: 20, max: 100)
        - page: Page number (default: 1)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)

    project_id = params.get("project_id")
    if not project_id:
        return {"ok": False, "error": "project_id is required"}

    encoded_id = _encode_project_id(project_id)

    query_params = {}

    if params.get("state"):
        query_params["state"] = params["state"]
    if params.get("labels"):
        query_params["labels"] = params["labels"]
    if params.get("milestone"):
        query_params["milestone"] = params["milestone"]
    if params.get("author_id"):
        query_params["author_id"] = params["author_id"]
    if params.get("assignee_id"):
        query_params["assignee_id"] = params["assignee_id"]
    if params.get("source_branch"):
        query_params["source_branch"] = params["source_branch"]
    if params.get("target_branch"):
        query_params["target_branch"] = params["target_branch"]
    if params.get("search"):
        query_params["search"] = params["search"]

    query_params["per_page"] = params.get("per_page", 20)
    query_params["page"] = params.get("page", 1)

    url = f"{base_url}/projects/{encoded_id}/merge_requests"
    if query_params:
        url = f"{url}?{urlencode(query_params)}"

    return _api_call(token, url)


def create_mr(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new merge request in a project.

    Params:
        - project_id: Project ID or path (required)
        - source_branch: Source branch name (required)
        - target_branch: Target branch name (required)
        - title: Merge request title (required)
        - description: Merge request description/body
        - assignee_ids: List of user IDs to assign
        - labels: Comma-separated list of label names
        - milestone_id: Milestone ID to associate
        - remove_source_branch: If True, remove source branch after merge
        - squash: If True, squash commits when merging
        - draft: If True, mark MR as draft/WIP (default: False)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)

    project_id = params.get("project_id")
    source_branch = params.get("source_branch")
    target_branch = params.get("target_branch")
    title = params.get("title")

    if not project_id:
        return {"ok": False, "error": "project_id is required"}
    if not source_branch:
        return {"ok": False, "error": "source_branch is required"}
    if not target_branch:
        return {"ok": False, "error": "target_branch is required"}
    if not title:
        return {"ok": False, "error": "title is required"}

    encoded_id = _encode_project_id(project_id)

    mr_data = {
        "source_branch": source_branch,
        "target_branch": target_branch,
        "title": title,
    }

    if params.get("description"):
        mr_data["description"] = params["description"]
    if params.get("assignee_ids"):
        mr_data["assignee_ids"] = params["assignee_ids"]
    if params.get("labels"):
        mr_data["labels"] = params["labels"]
    if params.get("milestone_id"):
        mr_data["milestone_id"] = params["milestone_id"]
    if params.get("remove_source_branch"):
        mr_data["remove_source_branch"] = True
    if params.get("squash"):
        mr_data["squash"] = True
    if params.get("draft"):
        mr_data["draft"] = True

    url = f"{base_url}/projects/{encoded_id}/merge_requests"

    return _api_call(token, url, method="POST", data=mr_data)


# ---------------------------------------------------------------------------
# Comment Actions
# ---------------------------------------------------------------------------

def add_comment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Add a comment/note to an issue or merge request.

    Params:
        - project_id: Project ID or path (required)
        - item_type: Type of item to comment on: "issue" or "mr" (required)
        - item_iid: Internal ID of the issue or MR (required)
        - body: Comment body/text (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)

    project_id = params.get("project_id")
    item_type = params.get("item_type")
    item_iid = params.get("item_iid")
    body = params.get("body")

    if not project_id:
        return {"ok": False, "error": "project_id is required"}
    if not item_type:
        return {"ok": False, "error": "item_type is required (issue or mr)"}
    if item_type not in ("issue", "mr"):
        return {"ok": False, "error": "item_type must be 'issue' or 'mr'"}
    if not item_iid:
        return {"ok": False, "error": "item_iid is required"}
    if not body:
        return {"ok": False, "error": "body is required"}

    encoded_id = _encode_project_id(project_id)

    # GitLab uses different endpoints for issue notes vs MR notes
    if item_type == "issue":
        url = f"{base_url}/projects/{encoded_id}/issues/{item_iid}/notes"
    else:  # mr
        url = f"{base_url}/projects/{encoded_id}/merge_requests/{item_iid}/notes"

    note_data = {"body": body}

    return _api_call(token, url, method="POST", data=note_data)


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

ACTIONS = {
    "list_projects": list_projects,
    "get_project": get_project,
    "list_issues": list_issues,
    "create_issue": create_issue,
    "list_mrs": list_mrs,
    "create_mr": create_mr,
    "add_comment": add_comment,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """Dispatch an action by name with a profile."""
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action '{action}'"}
    return ACTIONS[action](profile, params)
