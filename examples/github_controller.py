"""
GitHub Controller for TinyHive

A controller for interacting with GitHub REST API.

Method IDs:
  controller.github.{profile}.list_repos
  controller.github.{profile}.get_repo
  controller.github.{profile}.create_issue
  controller.github.{profile}.list_issues
  controller.github.{profile}.create_pr
  controller.github.{profile}.add_comment
  controller.github.{profile}.trigger_workflow
  controller.github.{profile}.create_release
  controller.github.{profile}.get_file

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "token_env": "GITHUB_TOKEN",
    "default_owner": "my-org",
    "api_base_url": "https://api.github.com"
}

Required Permissions (GitHub Token Scopes):
------------------------------------------
- list_repos: repo (or public_repo for public only)
- get_repo: repo (or public_repo for public only)
- create_issue: repo
- list_issues: repo
- create_pr: repo
- add_comment: repo
- trigger_workflow: repo, workflow
- create_release: repo
- get_file: repo (or public_repo for public only)

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
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.github")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

GITHUB_API_BASE = "https://api.github.com"
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


def _get_token(profile: Dict[str, Any]) -> str:
    """Get GitHub token from environment variable specified in profile."""
    token_env = profile.get("token_env", "GITHUB_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(f"Environment variable '{token_env}' not set")
    return token


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    token: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    base_url: str = GITHUB_API_BASE,
    timeout: int = DEFAULT_TIMEOUT,
    query_params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Make an authenticated GitHub API call."""
    url = f"{base_url}{endpoint}"

    if query_params:
        # Filter out None values
        filtered_params = {k: v for k, v in query_params.items() if v is not None}
        if filtered_params:
            url += "?" + urlencode(filtered_params)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "TinyHive-GitHub-Controller/1.0"
    }

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "data": json.loads(response_body)}
            return {"ok": True, "data": {}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_body[:500])
            errors = error_data.get("errors", [])
            if errors:
                error_details = "; ".join(
                    err.get("message", str(err)) for err in errors
                )
                error_message = f"{error_message}: {error_details}"
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("GitHub API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in GitHub API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def list_repos(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List repositories for a user or organization.

    Params:
        owner (str): Username or organization name (default: from profile)
        type (str): Type filter: all, owner, public, private, member (default: all)
        sort (str): Sort by: created, updated, pushed, full_name (default: full_name)
        direction (str): Sort direction: asc, desc (default: asc)
        per_page (int): Results per page (default: 30, max: 100)
        page (int): Page number (default: 1)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("api_base_url", GITHUB_API_BASE)

    owner = params.get("owner", profile.get("default_owner"))
    if not owner:
        return {"ok": False, "error": "owner is required (in params or profile default_owner)"}

    # Determine if it's a user or org - we'll try user endpoint first
    query_params = {
        "type": params.get("type", "all"),
        "sort": params.get("sort", "full_name"),
        "direction": params.get("direction", "asc"),
        "per_page": params.get("per_page", 30),
        "page": params.get("page", 1)
    }

    # Try user repos endpoint
    result = _api_call(
        token,
        f"/users/{quote(owner, safe='')}/repos",
        query_params=query_params,
        base_url=base_url
    )

    if result.get("ok"):
        repos = result["data"]
        return {
            "ok": True,
            "result": {
                "repos": [
                    {
                        "name": r.get("name"),
                        "full_name": r.get("full_name"),
                        "description": r.get("description"),
                        "private": r.get("private"),
                        "html_url": r.get("html_url"),
                        "clone_url": r.get("clone_url"),
                        "default_branch": r.get("default_branch"),
                        "language": r.get("language"),
                        "stargazers_count": r.get("stargazers_count"),
                        "forks_count": r.get("forks_count"),
                        "open_issues_count": r.get("open_issues_count"),
                        "created_at": r.get("created_at"),
                        "updated_at": r.get("updated_at"),
                        "pushed_at": r.get("pushed_at")
                    }
                    for r in repos
                ],
                "count": len(repos)
            }
        }
    return result


def get_repo(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific repository.

    Params:
        owner (str): Repository owner (required)
        repo (str): Repository name (required)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("api_base_url", GITHUB_API_BASE)

    owner = params.get("owner", profile.get("default_owner"))
    repo = params.get("repo")

    if not owner:
        return {"ok": False, "error": "owner is required"}
    if not repo:
        return {"ok": False, "error": "repo is required"}

    result = _api_call(
        token,
        f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}",
        base_url=base_url
    )

    if result.get("ok"):
        r = result["data"]
        return {
            "ok": True,
            "result": {
                "name": r.get("name"),
                "full_name": r.get("full_name"),
                "description": r.get("description"),
                "private": r.get("private"),
                "html_url": r.get("html_url"),
                "clone_url": r.get("clone_url"),
                "ssh_url": r.get("ssh_url"),
                "default_branch": r.get("default_branch"),
                "language": r.get("language"),
                "stargazers_count": r.get("stargazers_count"),
                "watchers_count": r.get("watchers_count"),
                "forks_count": r.get("forks_count"),
                "open_issues_count": r.get("open_issues_count"),
                "license": r.get("license", {}).get("name") if r.get("license") else None,
                "topics": r.get("topics", []),
                "visibility": r.get("visibility"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
                "pushed_at": r.get("pushed_at"),
                "owner": {
                    "login": r.get("owner", {}).get("login"),
                    "type": r.get("owner", {}).get("type")
                }
            }
        }
    return result


def create_issue(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new issue in a repository.

    Params:
        owner (str): Repository owner (required)
        repo (str): Repository name (required)
        title (str): Issue title (required)
        body (str): Issue body/description (optional)
        labels (list): List of label names (optional)
        assignees (list): List of usernames to assign (optional)
        milestone (int): Milestone number (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("api_base_url", GITHUB_API_BASE)

    owner = params.get("owner", profile.get("default_owner"))
    repo = params.get("repo")
    title = params.get("title")

    if not owner:
        return {"ok": False, "error": "owner is required"}
    if not repo:
        return {"ok": False, "error": "repo is required"}
    if not title:
        return {"ok": False, "error": "title is required"}

    data: Dict[str, Any] = {"title": title}

    if params.get("body"):
        data["body"] = params["body"]
    if params.get("labels"):
        data["labels"] = params["labels"]
    if params.get("assignees"):
        data["assignees"] = params["assignees"]
    if params.get("milestone"):
        data["milestone"] = params["milestone"]

    result = _api_call(
        token,
        f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/issues",
        method="POST",
        data=data,
        base_url=base_url
    )

    if result.get("ok"):
        issue = result["data"]
        return {
            "ok": True,
            "result": {
                "number": issue.get("number"),
                "title": issue.get("title"),
                "html_url": issue.get("html_url"),
                "state": issue.get("state"),
                "created_at": issue.get("created_at"),
                "user": issue.get("user", {}).get("login")
            }
        }
    return result


def list_issues(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List issues in a repository.

    Params:
        owner (str): Repository owner (required)
        repo (str): Repository name (required)
        state (str): Issue state: open, closed, all (default: open)
        labels (str): Comma-separated list of label names (optional)
        sort (str): Sort by: created, updated, comments (default: created)
        direction (str): Sort direction: asc, desc (default: desc)
        per_page (int): Results per page (default: 30, max: 100)
        page (int): Page number (default: 1)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("api_base_url", GITHUB_API_BASE)

    owner = params.get("owner", profile.get("default_owner"))
    repo = params.get("repo")

    if not owner:
        return {"ok": False, "error": "owner is required"}
    if not repo:
        return {"ok": False, "error": "repo is required"}

    query_params = {
        "state": params.get("state", "open"),
        "sort": params.get("sort", "created"),
        "direction": params.get("direction", "desc"),
        "per_page": params.get("per_page", 30),
        "page": params.get("page", 1)
    }

    if params.get("labels"):
        query_params["labels"] = params["labels"]

    result = _api_call(
        token,
        f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/issues",
        query_params=query_params,
        base_url=base_url
    )

    if result.get("ok"):
        issues = result["data"]
        return {
            "ok": True,
            "result": {
                "issues": [
                    {
                        "number": i.get("number"),
                        "title": i.get("title"),
                        "state": i.get("state"),
                        "html_url": i.get("html_url"),
                        "user": i.get("user", {}).get("login"),
                        "labels": [l.get("name") for l in i.get("labels", [])],
                        "assignees": [a.get("login") for a in i.get("assignees", [])],
                        "comments": i.get("comments"),
                        "created_at": i.get("created_at"),
                        "updated_at": i.get("updated_at"),
                        "is_pull_request": "pull_request" in i
                    }
                    for i in issues
                ],
                "count": len(issues)
            }
        }
    return result


def create_pr(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a pull request.

    Params:
        owner (str): Repository owner (required)
        repo (str): Repository name (required)
        title (str): PR title (required)
        head (str): Branch containing changes (required) - format: "branch" or "owner:branch"
        base (str): Branch to merge into (required)
        body (str): PR description (optional)
        draft (bool): Create as draft PR (default: false)
        maintainer_can_modify (bool): Allow maintainer edits (default: true)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("api_base_url", GITHUB_API_BASE)

    owner = params.get("owner", profile.get("default_owner"))
    repo = params.get("repo")
    title = params.get("title")
    head = params.get("head")
    base = params.get("base")

    if not owner:
        return {"ok": False, "error": "owner is required"}
    if not repo:
        return {"ok": False, "error": "repo is required"}
    if not title:
        return {"ok": False, "error": "title is required"}
    if not head:
        return {"ok": False, "error": "head is required"}
    if not base:
        return {"ok": False, "error": "base is required"}

    data: Dict[str, Any] = {
        "title": title,
        "head": head,
        "base": base,
        "maintainer_can_modify": params.get("maintainer_can_modify", True)
    }

    if params.get("body"):
        data["body"] = params["body"]
    if params.get("draft"):
        data["draft"] = params["draft"]

    result = _api_call(
        token,
        f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/pulls",
        method="POST",
        data=data,
        base_url=base_url
    )

    if result.get("ok"):
        pr = result["data"]
        return {
            "ok": True,
            "result": {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "html_url": pr.get("html_url"),
                "state": pr.get("state"),
                "draft": pr.get("draft"),
                "head": pr.get("head", {}).get("ref"),
                "base": pr.get("base", {}).get("ref"),
                "mergeable": pr.get("mergeable"),
                "created_at": pr.get("created_at"),
                "user": pr.get("user", {}).get("login")
            }
        }
    return result


def add_comment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a comment to an issue or pull request.

    Params:
        owner (str): Repository owner (required)
        repo (str): Repository name (required)
        issue_number (int): Issue or PR number (required)
        body (str): Comment body (required)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("api_base_url", GITHUB_API_BASE)

    owner = params.get("owner", profile.get("default_owner"))
    repo = params.get("repo")
    issue_number = params.get("issue_number")
    body = params.get("body")

    if not owner:
        return {"ok": False, "error": "owner is required"}
    if not repo:
        return {"ok": False, "error": "repo is required"}
    if issue_number is None:
        return {"ok": False, "error": "issue_number is required"}
    if not body:
        return {"ok": False, "error": "body is required"}

    result = _api_call(
        token,
        f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/issues/{issue_number}/comments",
        method="POST",
        data={"body": body},
        base_url=base_url
    )

    if result.get("ok"):
        comment = result["data"]
        return {
            "ok": True,
            "result": {
                "id": comment.get("id"),
                "html_url": comment.get("html_url"),
                "body": comment.get("body"),
                "user": comment.get("user", {}).get("login"),
                "created_at": comment.get("created_at")
            }
        }
    return result


def trigger_workflow(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trigger a workflow dispatch event.

    Params:
        owner (str): Repository owner (required)
        repo (str): Repository name (required)
        workflow_id (str): Workflow ID or filename (required) - e.g., "deploy.yml" or 12345
        ref (str): Git reference (branch or tag) to run workflow on (required)
        inputs (dict): Input parameters for the workflow (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("api_base_url", GITHUB_API_BASE)

    owner = params.get("owner", profile.get("default_owner"))
    repo = params.get("repo")
    workflow_id = params.get("workflow_id")
    ref = params.get("ref")

    if not owner:
        return {"ok": False, "error": "owner is required"}
    if not repo:
        return {"ok": False, "error": "repo is required"}
    if not workflow_id:
        return {"ok": False, "error": "workflow_id is required"}
    if not ref:
        return {"ok": False, "error": "ref is required"}

    data: Dict[str, Any] = {"ref": ref}

    if params.get("inputs"):
        data["inputs"] = params["inputs"]

    result = _api_call(
        token,
        f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/actions/workflows/{quote(str(workflow_id), safe='')}/dispatches",
        method="POST",
        data=data,
        base_url=base_url
    )

    # Workflow dispatch returns 204 No Content on success
    if result.get("ok"):
        return {
            "ok": True,
            "result": {
                "message": "Workflow dispatch triggered successfully",
                "workflow_id": workflow_id,
                "ref": ref
            }
        }
    return result


def create_release(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new release.

    Params:
        owner (str): Repository owner (required)
        repo (str): Repository name (required)
        tag_name (str): Tag name for the release (required)
        name (str): Release title (optional, defaults to tag_name)
        body (str): Release notes/description (optional)
        target_commitish (str): Commitish for the tag (default: default branch)
        draft (bool): Create as draft release (default: false)
        prerelease (bool): Mark as prerelease (default: false)
        generate_release_notes (bool): Auto-generate release notes (default: false)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("api_base_url", GITHUB_API_BASE)

    owner = params.get("owner", profile.get("default_owner"))
    repo = params.get("repo")
    tag_name = params.get("tag_name")

    if not owner:
        return {"ok": False, "error": "owner is required"}
    if not repo:
        return {"ok": False, "error": "repo is required"}
    if not tag_name:
        return {"ok": False, "error": "tag_name is required"}

    data: Dict[str, Any] = {"tag_name": tag_name}

    if params.get("name"):
        data["name"] = params["name"]
    if params.get("body"):
        data["body"] = params["body"]
    if params.get("target_commitish"):
        data["target_commitish"] = params["target_commitish"]
    if params.get("draft"):
        data["draft"] = params["draft"]
    if params.get("prerelease"):
        data["prerelease"] = params["prerelease"]
    if params.get("generate_release_notes"):
        data["generate_release_notes"] = params["generate_release_notes"]

    result = _api_call(
        token,
        f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/releases",
        method="POST",
        data=data,
        base_url=base_url
    )

    if result.get("ok"):
        release = result["data"]
        return {
            "ok": True,
            "result": {
                "id": release.get("id"),
                "tag_name": release.get("tag_name"),
                "name": release.get("name"),
                "html_url": release.get("html_url"),
                "draft": release.get("draft"),
                "prerelease": release.get("prerelease"),
                "created_at": release.get("created_at"),
                "published_at": release.get("published_at"),
                "author": release.get("author", {}).get("login"),
                "tarball_url": release.get("tarball_url"),
                "zipball_url": release.get("zipball_url")
            }
        }
    return result


def get_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get contents of a file from a repository.

    Params:
        owner (str): Repository owner (required)
        repo (str): Repository name (required)
        path (str): Path to file in repository (required)
        ref (str): Git reference (branch, tag, commit SHA) (optional, default: default branch)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("api_base_url", GITHUB_API_BASE)

    owner = params.get("owner", profile.get("default_owner"))
    repo = params.get("repo")
    path = params.get("path")

    if not owner:
        return {"ok": False, "error": "owner is required"}
    if not repo:
        return {"ok": False, "error": "repo is required"}
    if not path:
        return {"ok": False, "error": "path is required"}

    # URL encode the path, but preserve forward slashes
    encoded_path = "/".join(quote(segment, safe='') for segment in path.split("/"))

    query_params = {}
    if params.get("ref"):
        query_params["ref"] = params["ref"]

    result = _api_call(
        token,
        f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/contents/{encoded_path}",
        query_params=query_params if query_params else None,
        base_url=base_url
    )

    if result.get("ok"):
        content_data = result["data"]

        # Check if it's a file or directory
        if isinstance(content_data, list):
            # It's a directory listing
            return {
                "ok": True,
                "result": {
                    "type": "directory",
                    "path": path,
                    "entries": [
                        {
                            "name": entry.get("name"),
                            "path": entry.get("path"),
                            "type": entry.get("type"),
                            "size": entry.get("size"),
                            "sha": entry.get("sha")
                        }
                        for entry in content_data
                    ]
                }
            }
        else:
            # It's a file
            file_type = content_data.get("type")

            if file_type == "file":
                # Decode content from base64
                encoded_content = content_data.get("content", "")
                encoding = content_data.get("encoding", "base64")

                if encoding == "base64":
                    try:
                        # Remove newlines that GitHub adds in base64 content
                        clean_content = encoded_content.replace("\n", "")
                        decoded_bytes = base64.b64decode(clean_content)
                        try:
                            decoded_content = decoded_bytes.decode("utf-8")
                            content_encoding = "utf-8"
                        except UnicodeDecodeError:
                            # Binary file, return as base64
                            decoded_content = clean_content
                            content_encoding = "base64"
                    except Exception as e:
                        return {"ok": False, "error": f"Failed to decode content: {str(e)}"}
                else:
                    decoded_content = encoded_content
                    content_encoding = encoding

                return {
                    "ok": True,
                    "result": {
                        "type": "file",
                        "name": content_data.get("name"),
                        "path": content_data.get("path"),
                        "sha": content_data.get("sha"),
                        "size": content_data.get("size"),
                        "content": decoded_content,
                        "encoding": content_encoding,
                        "html_url": content_data.get("html_url"),
                        "download_url": content_data.get("download_url")
                    }
                }
            else:
                # Symlink or submodule
                return {
                    "ok": True,
                    "result": {
                        "type": file_type,
                        "name": content_data.get("name"),
                        "path": content_data.get("path"),
                        "sha": content_data.get("sha"),
                        "target": content_data.get("target"),
                        "submodule_git_url": content_data.get("submodule_git_url")
                    }
                }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_repos": list_repos,
    "get_repo": get_repo,
    "create_issue": create_issue,
    "list_issues": list_issues,
    "create_pr": create_pr,
    "add_comment": add_comment,
    "trigger_workflow": trigger_workflow,
    "create_release": create_release,
    "get_file": get_file,
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
        return {"ok": False, "error": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"}

    try:
        logger.info(f"Executing github.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
