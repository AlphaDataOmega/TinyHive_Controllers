"""
Asana Controller for TinyHive

A controller for interacting with Asana REST API for task management
and project collaboration.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "token_env": "ASANA_TOKEN"
}

Required Permissions (Asana Personal Access Token):
---------------------------------------------------
- list_workspaces: read access to user workspaces
- list_projects: read access to projects
- get_project: read access to projects
- list_tasks: read access to tasks
- create_task: write access to tasks
- update_task: write access to tasks
- add_comment: write access to stories/comments
- complete_task: write access to tasks

Dependencies:
------------
None (standard library only)

Method IDs:
  controller.asana.{profile}.list_workspaces
  controller.asana.{profile}.list_projects
  controller.asana.{profile}.get_project
  controller.asana.{profile}.list_tasks
  controller.asana.{profile}.create_task
  controller.asana.{profile}.update_task
  controller.asana.{profile}.add_comment
  controller.asana.{profile}.complete_task
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger("tinyhive.controller.asana")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

BASE_URL = "https://app.asana.com/api/1.0"
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
    """Get Asana personal access token from environment variable specified in profile."""
    token_env = profile.get("token_env", "ASANA_TOKEN")
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
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated Asana API call.

    Args:
        token: Asana personal access token
        endpoint: API endpoint path (e.g., "/workspaces")
        method: HTTP method
        data: Request body data (will be JSON encoded)
        timeout: Request timeout in seconds

    Returns:
        Dict with 'ok' boolean and either 'result' or 'error'
    """
    url = f"{BASE_URL}{endpoint}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    body = None
    if data is not None:
        body = json.dumps({"data": data}).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                result = json.loads(response_body)
                # Asana wraps responses in a "data" field
                return {"ok": True, "result": result.get("data", result)}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            # Asana returns errors in "errors" array
            if "errors" in error_data:
                error_messages = [err.get("message", str(err)) for err in error_data["errors"]]
                error_message = "; ".join(error_messages)
            elif "message" in error_data:
                error_message = error_data["message"]
            else:
                error_message = error_body[:500]
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Asana API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Asana API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def list_workspaces(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all workspaces accessible to the user.

    Params:
        limit (int): Maximum number of results (optional, default: 100)
        offset (str): Pagination offset token (optional)

    Returns:
        List of workspaces with gid, name, and is_organization
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    # Build query parameters
    query_parts = []
    limit = params.get("limit", 100)
    query_parts.append(f"limit={limit}")

    offset = params.get("offset")
    if offset:
        query_parts.append(f"offset={offset}")

    endpoint = "/workspaces"
    if query_parts:
        endpoint += "?" + "&".join(query_parts)

    result = _api_call(token, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        workspaces = result["result"]
        if isinstance(workspaces, list):
            return {
                "ok": True,
                "result": {
                    "workspaces": [
                        {
                            "gid": ws.get("gid"),
                            "name": ws.get("name"),
                            "is_organization": ws.get("is_organization"),
                        }
                        for ws in workspaces
                    ],
                    "count": len(workspaces),
                }
            }
    return result


def list_projects(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List projects in a workspace.

    Params:
        workspace_gid (str): The workspace GID (required)
        archived (bool): Filter by archived status (optional)
        limit (int): Maximum number of results (optional, default: 100)
        offset (str): Pagination offset token (optional)

    Returns:
        List of projects with gid, name, and other details
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    workspace_gid = params.get("workspace_gid")
    if not workspace_gid:
        return {"ok": False, "error": "workspace_gid is required"}

    # Build query parameters
    query_parts = [f"workspace={workspace_gid}"]

    limit = params.get("limit", 100)
    query_parts.append(f"limit={limit}")

    archived = params.get("archived")
    if archived is not None:
        query_parts.append(f"archived={str(archived).lower()}")

    offset = params.get("offset")
    if offset:
        query_parts.append(f"offset={offset}")

    endpoint = "/projects?" + "&".join(query_parts)

    result = _api_call(token, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        projects = result["result"]
        if isinstance(projects, list):
            return {
                "ok": True,
                "result": {
                    "projects": [
                        {
                            "gid": proj.get("gid"),
                            "name": proj.get("name"),
                            "resource_type": proj.get("resource_type"),
                        }
                        for proj in projects
                    ],
                    "count": len(projects),
                }
            }
    return result


def get_project(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get detailed information about a project.

    Params:
        project_gid (str): The project GID (required)
        opt_fields (list): Optional fields to include (optional)

    Returns:
        Project details
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    project_gid = params.get("project_gid")
    if not project_gid:
        return {"ok": False, "error": "project_gid is required"}

    # Build query parameters
    query_parts = []

    opt_fields = params.get("opt_fields")
    if opt_fields:
        if isinstance(opt_fields, list):
            query_parts.append(f"opt_fields={','.join(opt_fields)}")
        else:
            query_parts.append(f"opt_fields={opt_fields}")

    endpoint = f"/projects/{project_gid}"
    if query_parts:
        endpoint += "?" + "&".join(query_parts)

    result = _api_call(token, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        project = result["result"]
        return {
            "ok": True,
            "result": {
                "gid": project.get("gid"),
                "name": project.get("name"),
                "notes": project.get("notes"),
                "color": project.get("color"),
                "archived": project.get("archived"),
                "public": project.get("public"),
                "created_at": project.get("created_at"),
                "modified_at": project.get("modified_at"),
                "due_date": project.get("due_date"),
                "due_on": project.get("due_on"),
                "start_on": project.get("start_on"),
                "owner": project.get("owner"),
                "team": project.get("team"),
                "workspace": project.get("workspace"),
                "members": project.get("members"),
                "followers": project.get("followers"),
            }
        }
    return result


def list_tasks(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List tasks in a project.

    Params:
        project_gid (str): The project GID (required)
        completed_since (str): Only return tasks completed since this time (ISO 8601, optional)
            Use "now" to get only incomplete tasks
        limit (int): Maximum number of results (optional, default: 100)
        offset (str): Pagination offset token (optional)
        opt_fields (list): Optional fields to include (optional)

    Returns:
        List of tasks with gid, name, and other details
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    project_gid = params.get("project_gid")
    if not project_gid:
        return {"ok": False, "error": "project_gid is required"}

    # Build query parameters
    query_parts = []

    limit = params.get("limit", 100)
    query_parts.append(f"limit={limit}")

    completed_since = params.get("completed_since")
    if completed_since:
        query_parts.append(f"completed_since={completed_since}")

    offset = params.get("offset")
    if offset:
        query_parts.append(f"offset={offset}")

    opt_fields = params.get("opt_fields")
    if opt_fields:
        if isinstance(opt_fields, list):
            query_parts.append(f"opt_fields={','.join(opt_fields)}")
        else:
            query_parts.append(f"opt_fields={opt_fields}")

    endpoint = f"/projects/{project_gid}/tasks"
    if query_parts:
        endpoint += "?" + "&".join(query_parts)

    result = _api_call(token, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        tasks = result["result"]
        if isinstance(tasks, list):
            return {
                "ok": True,
                "result": {
                    "tasks": [
                        {
                            "gid": task.get("gid"),
                            "name": task.get("name"),
                            "resource_type": task.get("resource_type"),
                            "completed": task.get("completed"),
                            "due_on": task.get("due_on"),
                            "due_at": task.get("due_at"),
                            "assignee": task.get("assignee"),
                        }
                        for task in tasks
                    ],
                    "count": len(tasks),
                }
            }
    return result


def create_task(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new task.

    Params:
        workspace_gid (str): The workspace GID (required if no projects specified)
        name (str): Task name (required)
        notes (str): Task description/notes (optional)
        due_on (str): Due date in YYYY-MM-DD format (optional)
        assignee (str): Assignee GID or email (optional)
        projects (list): List of project GIDs to add task to (optional)
        tags (list): List of tag GIDs (optional)
        parent (str): Parent task GID for subtasks (optional)

    Returns:
        Created task details
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    name = params.get("name")
    if not name:
        return {"ok": False, "error": "name is required"}

    workspace_gid = params.get("workspace_gid")
    projects = params.get("projects")

    if not workspace_gid and not projects:
        return {"ok": False, "error": "Either workspace_gid or projects is required"}

    # Build task data
    task_data: Dict[str, Any] = {"name": name}

    if workspace_gid:
        task_data["workspace"] = workspace_gid

    notes = params.get("notes")
    if notes:
        task_data["notes"] = notes

    due_on = params.get("due_on")
    if due_on:
        task_data["due_on"] = due_on

    assignee = params.get("assignee")
    if assignee:
        task_data["assignee"] = assignee

    if projects:
        if isinstance(projects, list):
            task_data["projects"] = projects
        else:
            task_data["projects"] = [projects]

    tags = params.get("tags")
    if tags:
        if isinstance(tags, list):
            task_data["tags"] = tags
        else:
            task_data["tags"] = [tags]

    parent = params.get("parent")
    if parent:
        task_data["parent"] = parent

    result = _api_call(token, "/tasks", method="POST", data=task_data)

    if result.get("ok") and "result" in result:
        task = result["result"]
        return {
            "ok": True,
            "result": {
                "gid": task.get("gid"),
                "name": task.get("name"),
                "notes": task.get("notes"),
                "due_on": task.get("due_on"),
                "assignee": task.get("assignee"),
                "completed": task.get("completed"),
                "created_at": task.get("created_at"),
                "permalink_url": task.get("permalink_url"),
            }
        }
    return result


def update_task(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing task.

    Params:
        task_gid (str): The task GID (required)
        fields (dict): Fields to update (required)
            Supported fields: name, notes, due_on, due_at, assignee, completed,
            start_on, start_at, liked, html_notes

    Returns:
        Updated task details
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    task_gid = params.get("task_gid")
    if not task_gid:
        return {"ok": False, "error": "task_gid is required"}

    fields = params.get("fields")
    if not fields:
        return {"ok": False, "error": "fields is required"}

    if not isinstance(fields, dict):
        return {"ok": False, "error": "fields must be a dictionary"}

    result = _api_call(token, f"/tasks/{task_gid}", method="PUT", data=fields)

    if result.get("ok") and "result" in result:
        task = result["result"]
        return {
            "ok": True,
            "result": {
                "gid": task.get("gid"),
                "name": task.get("name"),
                "notes": task.get("notes"),
                "due_on": task.get("due_on"),
                "assignee": task.get("assignee"),
                "completed": task.get("completed"),
                "modified_at": task.get("modified_at"),
            }
        }
    return result


def add_comment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a comment (story) to a task.

    Params:
        task_gid (str): The task GID (required)
        text (str): Comment text (required)

    Returns:
        Created comment/story details
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    task_gid = params.get("task_gid")
    if not task_gid:
        return {"ok": False, "error": "task_gid is required"}

    text = params.get("text")
    if not text:
        return {"ok": False, "error": "text is required"}

    story_data = {"text": text}

    result = _api_call(token, f"/tasks/{task_gid}/stories", method="POST", data=story_data)

    if result.get("ok") and "result" in result:
        story = result["result"]
        return {
            "ok": True,
            "result": {
                "gid": story.get("gid"),
                "text": story.get("text"),
                "created_at": story.get("created_at"),
                "created_by": story.get("created_by"),
                "resource_type": story.get("resource_type"),
                "type": story.get("type"),
            }
        }
    return result


def complete_task(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mark a task as complete.

    Params:
        task_gid (str): The task GID (required)

    Returns:
        Updated task showing completed status
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    task_gid = params.get("task_gid")
    if not task_gid:
        return {"ok": False, "error": "task_gid is required"}

    result = _api_call(token, f"/tasks/{task_gid}", method="PUT", data={"completed": True})

    if result.get("ok") and "result" in result:
        task = result["result"]
        return {
            "ok": True,
            "result": {
                "gid": task.get("gid"),
                "name": task.get("name"),
                "completed": task.get("completed"),
                "completed_at": task.get("completed_at"),
                "modified_at": task.get("modified_at"),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_workspaces": list_workspaces,
    "list_projects": list_projects,
    "get_project": get_project,
    "list_tasks": list_tasks,
    "create_task": create_task,
    "update_task": update_task,
    "add_comment": add_comment,
    "complete_task": complete_task,
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
        logger.info(f"Executing asana.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
