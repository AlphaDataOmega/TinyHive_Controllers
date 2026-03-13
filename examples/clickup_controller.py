"""
ClickUp Controller for TinyHive

A controller for integrating with ClickUp API v2.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

ClickUp profile:
{
    "token_env": "CLICKUP_TOKEN"
}

Required API Token:
------------------
Generate a personal API token from ClickUp Settings > Apps > API Token
Or use OAuth2 access token.

The token needs appropriate permissions for the actions you want to perform:
- Workspaces/Teams read access
- Spaces read access
- Folders read access
- Lists read access
- Tasks read/write access
- Comments write access

Dependencies:
------------
- None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.clickup")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# ClickUp API base URL
CLICKUP_API_BASE = "https://api.clickup.com/api/v2"

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


def _get_token(profile: Dict[str, Any]) -> str:
    """Get the ClickUp API token from environment variable."""
    token_env = profile.get("token_env", "CLICKUP_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(
            f"Environment variable '{token_env}' not set. "
            "Set your ClickUp API token in this environment variable."
        )
    return token


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    token: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated ClickUp API call.

    Args:
        token: ClickUp API token
        endpoint: API endpoint path (e.g., '/team')
        method: HTTP method (GET, POST, PUT, DELETE)
        data: Request body payload (for POST/PUT)
        params: Query parameters
        timeout: Request timeout in seconds

    Returns:
        Response dict with 'ok' field and result/error
    """
    url = f"{CLICKUP_API_BASE}{endpoint}"

    if params:
        # Filter out None values
        filtered_params = {k: v for k, v in params.items() if v is not None}
        if filtered_params:
            url = f"{url}?{urlencode(filtered_params)}"

    headers = {
        "Authorization": token,
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
                result = json.loads(response_body)
                return {"ok": True, "data": result}
            else:
                return {"ok": True, "data": {}}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("err", error_data.get("error", error_body[:500]))
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("ClickUp HTTP error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in ClickUp API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def list_workspaces(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List authorized workspaces (teams) for the authenticated user.

    Params:
        None required

    Returns:
        ok (bool): Success status
        data (dict): Response including teams list with id, name, color, avatar, members
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        return _api_call(token, "/team")

    except Exception as e:
        logger.exception("list_workspaces failed")
        return {"ok": False, "error": str(e)}


def list_spaces(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List spaces in a workspace (team).

    Params:
        team_id (str): Workspace/Team ID (required)
        archived (bool): Include archived spaces (default: false)

    Returns:
        ok (bool): Success status
        data (dict): Response including spaces list with id, name, private, statuses, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        team_id = params.get("team_id")
        if not team_id:
            return {"ok": False, "error": "team_id is required"}

        query_params = {}
        if params.get("archived"):
            query_params["archived"] = "true"

        return _api_call(token, f"/team/{team_id}/space", params=query_params)

    except Exception as e:
        logger.exception("list_spaces failed")
        return {"ok": False, "error": str(e)}


def list_folders(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List folders in a space.

    Params:
        space_id (str): Space ID (required)
        archived (bool): Include archived folders (default: false)

    Returns:
        ok (bool): Success status
        data (dict): Response including folders list with id, name, lists, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        space_id = params.get("space_id")
        if not space_id:
            return {"ok": False, "error": "space_id is required"}

        query_params = {}
        if params.get("archived"):
            query_params["archived"] = "true"

        return _api_call(token, f"/space/{space_id}/folder", params=query_params)

    except Exception as e:
        logger.exception("list_folders failed")
        return {"ok": False, "error": str(e)}


def list_lists(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List lists in a folder.

    Params:
        folder_id (str): Folder ID (required)
        archived (bool): Include archived lists (default: false)

    Returns:
        ok (bool): Success status
        data (dict): Response including lists with id, name, content, status, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        folder_id = params.get("folder_id")
        if not folder_id:
            return {"ok": False, "error": "folder_id is required"}

        query_params = {}
        if params.get("archived"):
            query_params["archived"] = "true"

        return _api_call(token, f"/folder/{folder_id}/list", params=query_params)

    except Exception as e:
        logger.exception("list_lists failed")
        return {"ok": False, "error": str(e)}


def list_tasks(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List tasks in a list.

    Params:
        list_id (str): List ID (required)
        include_closed (bool): Include closed tasks (default: false)
        subtasks (bool): Include subtasks (default: false)
        page (int): Page number for pagination (default: 0)
        order_by (str): Order by field: id, created, updated, due_date (optional)
        reverse (bool): Reverse order (default: false)
        statuses (list): Filter by status names (optional)
        assignees (list): Filter by assignee user IDs (optional)
        due_date_gt (int): Filter tasks with due date greater than (unix ms) (optional)
        due_date_lt (int): Filter tasks with due date less than (unix ms) (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response including tasks list with id, name, status, assignees, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        list_id = params.get("list_id")
        if not list_id:
            return {"ok": False, "error": "list_id is required"}

        query_params: Dict[str, Any] = {}

        if params.get("include_closed"):
            query_params["include_closed"] = "true"

        if params.get("subtasks"):
            query_params["subtasks"] = "true"

        if params.get("page") is not None:
            query_params["page"] = params["page"]

        if params.get("order_by"):
            query_params["order_by"] = params["order_by"]

        if params.get("reverse"):
            query_params["reverse"] = "true"

        # Handle array parameters
        if params.get("statuses"):
            statuses = params["statuses"]
            if isinstance(statuses, list):
                for status in statuses:
                    query_params[f"statuses[]"] = status
            else:
                query_params["statuses[]"] = statuses

        if params.get("assignees"):
            assignees = params["assignees"]
            if isinstance(assignees, list):
                for assignee in assignees:
                    query_params[f"assignees[]"] = assignee
            else:
                query_params["assignees[]"] = assignees

        if params.get("due_date_gt") is not None:
            query_params["due_date_gt"] = params["due_date_gt"]

        if params.get("due_date_lt") is not None:
            query_params["due_date_lt"] = params["due_date_lt"]

        return _api_call(token, f"/list/{list_id}/task", params=query_params)

    except Exception as e:
        logger.exception("list_tasks failed")
        return {"ok": False, "error": str(e)}


def create_task(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new task in a list.

    Params:
        list_id (str): List ID to create task in (required)
        name (str): Task name (required)
        description (str): Task description in markdown format (optional)
        assignees (list): List of user IDs to assign (optional)
        due_date (int): Due date as Unix timestamp in milliseconds (optional)
        due_date_time (bool): Whether due_date includes time (default: false)
        priority (int): Priority level: 1=urgent, 2=high, 3=normal, 4=low (optional)
        status (str): Status name to set (optional)
        tags (list): List of tag names (optional)
        parent (str): Parent task ID to create as subtask (optional)
        notify_all (bool): Notify all assignees (default: true)
        custom_fields (list): List of custom field objects with id and value (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response including created task with id, name, status, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        list_id = params.get("list_id")
        name = params.get("name")

        if not list_id:
            return {"ok": False, "error": "list_id is required"}
        if not name:
            return {"ok": False, "error": "name is required"}

        payload: Dict[str, Any] = {"name": name}

        if params.get("description"):
            payload["description"] = params["description"]

        if params.get("assignees"):
            assignees = params["assignees"]
            if isinstance(assignees, list):
                payload["assignees"] = assignees
            else:
                payload["assignees"] = [assignees]

        if params.get("due_date") is not None:
            payload["due_date"] = params["due_date"]
            if params.get("due_date_time"):
                payload["due_date_time"] = True

        if params.get("priority") is not None:
            payload["priority"] = params["priority"]

        if params.get("status"):
            payload["status"] = params["status"]

        if params.get("tags"):
            tags = params["tags"]
            if isinstance(tags, list):
                payload["tags"] = tags
            else:
                payload["tags"] = [tags]

        if params.get("parent"):
            payload["parent"] = params["parent"]

        if "notify_all" in params:
            payload["notify_all"] = params["notify_all"]

        if params.get("custom_fields"):
            payload["custom_fields"] = params["custom_fields"]

        return _api_call(token, f"/list/{list_id}/task", method="POST", data=payload)

    except Exception as e:
        logger.exception("create_task failed")
        return {"ok": False, "error": str(e)}


def update_task(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing task.

    Params:
        task_id (str): Task ID to update (required)
        name (str): New task name (optional)
        description (str): New description in markdown (optional)
        status (str): New status name (optional)
        priority (int): New priority: 1=urgent, 2=high, 3=normal, 4=low, null=none (optional)
        due_date (int): New due date as Unix timestamp in ms, null to clear (optional)
        due_date_time (bool): Whether due_date includes time (optional)
        start_date (int): Start date as Unix timestamp in ms (optional)
        start_date_time (bool): Whether start_date includes time (optional)
        assignees (dict): {"add": [user_ids], "rem": [user_ids]} (optional)
        archived (bool): Archive/unarchive task (optional)
        parent (str): Move to different parent task (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response including updated task details
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        task_id = params.get("task_id")
        if not task_id:
            return {"ok": False, "error": "task_id is required"}

        # Build payload from optional fields
        payload: Dict[str, Any] = {}

        if "name" in params:
            payload["name"] = params["name"]

        if "description" in params:
            payload["description"] = params["description"]

        if "status" in params:
            payload["status"] = params["status"]

        if "priority" in params:
            payload["priority"] = params["priority"]

        if "due_date" in params:
            payload["due_date"] = params["due_date"]
            if params.get("due_date_time"):
                payload["due_date_time"] = True

        if "start_date" in params:
            payload["start_date"] = params["start_date"]
            if params.get("start_date_time"):
                payload["start_date_time"] = True

        if "assignees" in params:
            payload["assignees"] = params["assignees"]

        if "archived" in params:
            payload["archived"] = params["archived"]

        if "parent" in params:
            payload["parent"] = params["parent"]

        if not payload:
            return {"ok": False, "error": "At least one field to update is required"}

        return _api_call(token, f"/task/{task_id}", method="PUT", data=payload)

    except Exception as e:
        logger.exception("update_task failed")
        return {"ok": False, "error": str(e)}


def add_comment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a comment to a task.

    Params:
        task_id (str): Task ID to comment on (required)
        comment_text (str): Comment text content (required)
        assignee (int): User ID to assign with comment (optional)
        notify_all (bool): Notify all task watchers (default: true)

    Returns:
        ok (bool): Success status
        data (dict): Response including comment id, hist_id, date
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        task_id = params.get("task_id")
        comment_text = params.get("comment_text")

        if not task_id:
            return {"ok": False, "error": "task_id is required"}
        if not comment_text:
            return {"ok": False, "error": "comment_text is required"}

        payload: Dict[str, Any] = {"comment_text": comment_text}

        if params.get("assignee") is not None:
            payload["assignee"] = params["assignee"]

        if "notify_all" in params:
            payload["notify_all"] = params["notify_all"]

        return _api_call(token, f"/task/{task_id}/comment", method="POST", data=payload)

    except Exception as e:
        logger.exception("add_comment failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_workspaces": list_workspaces,
    "list_spaces": list_spaces,
    "list_folders": list_folders,
    "list_lists": list_lists,
    "list_tasks": list_tasks,
    "create_task": create_task,
    "update_task": update_task,
    "add_comment": add_comment,
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

    logger.info(f"Executing clickup.{profile}.{action}")
    return ACTIONS[action](profile, params)
