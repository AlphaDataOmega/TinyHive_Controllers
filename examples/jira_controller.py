"""
Jira Controller for TinyHive

A controller for interacting with Jira REST API for issue tracking
and project management.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "base_url": "https://yoursite.atlassian.net",
    "email_env": "JIRA_EMAIL",
    "token_env": "JIRA_API_TOKEN"
}

Required Permissions:
--------------------
- create_issue: Browse projects, Create issues
- update_issue: Edit issues
- get_issue: Browse projects
- search_issues: Browse projects
- add_comment: Add comments
- transition_issue: Transition issues
- assign_issue: Assign issues
- list_projects: Browse projects

Dependencies:
------------
None (standard library only)

Method IDs:
  controller.jira.{profile}.create_issue
  controller.jira.{profile}.update_issue
  controller.jira.{profile}.get_issue
  controller.jira.{profile}.search_issues
  controller.jira.{profile}.add_comment
  controller.jira.{profile}.transition_issue
  controller.jira.{profile}.assign_issue
  controller.jira.{profile}.list_projects
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

logger = logging.getLogger("tinyhive.controller.jira")

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


def list_profiles() -> List[str]:
    """List available Jira profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# Authentication
# =============================================================================

def _get_auth_header(profile: Dict[str, Any]) -> str:
    """
    Get Basic Auth header for Jira API.

    Jira Cloud uses Basic Auth with email:api_token base64 encoded.
    """
    email_env = profile.get("email_env", "JIRA_EMAIL")
    token_env = profile.get("token_env", "JIRA_API_TOKEN")

    email = os.environ.get(email_env)
    token = os.environ.get(token_env)

    if not email:
        raise ValueError(f"Environment variable '{email_env}' not set")
    if not token:
        raise ValueError(f"Environment variable '{token_env}' not set")

    credentials = f"{email}:{token}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


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
    """
    Make an authenticated Jira API call.

    Args:
        profile: Profile configuration dict
        endpoint: API endpoint path (e.g., "/rest/api/3/issue")
        method: HTTP method
        data: Request body data (will be JSON encoded)
        timeout: Request timeout in seconds

    Returns:
        Dict with 'ok' boolean and either 'result' or 'error'
    """
    base_url = profile.get("base_url", "").rstrip("/")
    if not base_url:
        return {"ok": False, "error": "base_url not configured in profile"}

    url = f"{base_url}{endpoint}"

    headers = {
        "Authorization": _get_auth_header(profile),
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
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            # Jira returns errors in various formats
            if "errorMessages" in error_data:
                error_message = "; ".join(error_data["errorMessages"])
            elif "errors" in error_data:
                error_message = "; ".join(f"{k}: {v}" for k, v in error_data["errors"].items())
            elif "message" in error_data:
                error_message = error_data["message"]
            else:
                error_message = error_body[:500]
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Jira API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Jira API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def create_issue(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new Jira issue.

    Params:
        project_key (str): Project key (e.g., "PROJ") - required
        summary (str): Issue summary/title - required
        description (str): Issue description (optional)
        issue_type (str): Issue type name (e.g., "Bug", "Task", "Story") - default: "Task"
        priority (str): Priority name (e.g., "High", "Medium", "Low") - optional
        assignee (str): Account ID of assignee - optional
        labels (list): List of label strings - optional

    Returns:
        Created issue key and details
    """
    profile = load_profile(profile_name)

    project_key = params.get("project_key")
    summary = params.get("summary")

    if not project_key:
        return {"ok": False, "error": "project_key is required"}
    if not summary:
        return {"ok": False, "error": "summary is required"}

    # Build issue fields
    fields: Dict[str, Any] = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": params.get("issue_type", "Task")},
    }

    # Optional description (Jira Cloud uses ADF format)
    description = params.get("description")
    if description:
        fields["description"] = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": description}
                    ]
                }
            ]
        }

    # Optional priority
    priority = params.get("priority")
    if priority:
        fields["priority"] = {"name": priority}

    # Optional assignee
    assignee = params.get("assignee")
    if assignee:
        fields["assignee"] = {"accountId": assignee}

    # Optional labels
    labels = params.get("labels")
    if labels:
        fields["labels"] = labels if isinstance(labels, list) else [labels]

    result = _api_call(profile, "/rest/api/3/issue", method="POST", data={"fields": fields})

    if result.get("ok") and "result" in result:
        issue = result["result"]
        return {
            "ok": True,
            "result": {
                "id": issue.get("id"),
                "key": issue.get("key"),
                "self": issue.get("self"),
            }
        }
    return result


def update_issue(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing Jira issue.

    Params:
        issue_key (str): Issue key (e.g., "PROJ-123") - required
        fields (dict): Fields to update - required
            Supported fields: summary, description, priority, labels, assignee, etc.

    Returns:
        Success status
    """
    profile = load_profile(profile_name)

    issue_key = params.get("issue_key")
    fields = params.get("fields")

    if not issue_key:
        return {"ok": False, "error": "issue_key is required"}
    if not fields:
        return {"ok": False, "error": "fields is required"}

    # Convert description to ADF format if provided as string
    if "description" in fields and isinstance(fields["description"], str):
        fields["description"] = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": fields["description"]}
                    ]
                }
            ]
        }

    # Convert priority to object format if provided as string
    if "priority" in fields and isinstance(fields["priority"], str):
        fields["priority"] = {"name": fields["priority"]}

    # Convert assignee to object format if provided as string
    if "assignee" in fields and isinstance(fields["assignee"], str):
        fields["assignee"] = {"accountId": fields["assignee"]}

    endpoint = f"/rest/api/3/issue/{quote(issue_key)}"
    result = _api_call(profile, endpoint, method="PUT", data={"fields": fields})

    if result.get("ok"):
        return {"ok": True, "result": {"issue_key": issue_key, "updated": True}}
    return result


def get_issue(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a Jira issue.

    Params:
        issue_key (str): Issue key (e.g., "PROJ-123") - required
        fields (list): List of fields to return (optional, returns all if not specified)
        expand (list): List of expansions (optional, e.g., ["changelog", "renderedFields"])

    Returns:
        Issue details
    """
    profile = load_profile(profile_name)

    issue_key = params.get("issue_key")
    if not issue_key:
        return {"ok": False, "error": "issue_key is required"}

    # Build query parameters
    query_params = {}

    fields = params.get("fields")
    if fields:
        query_params["fields"] = ",".join(fields) if isinstance(fields, list) else fields

    expand = params.get("expand")
    if expand:
        query_params["expand"] = ",".join(expand) if isinstance(expand, list) else expand

    endpoint = f"/rest/api/3/issue/{quote(issue_key)}"
    if query_params:
        endpoint += f"?{urlencode(query_params)}"

    result = _api_call(profile, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        issue = result["result"]
        fields_data = issue.get("fields", {})

        # Extract common fields for easier access
        return {
            "ok": True,
            "result": {
                "id": issue.get("id"),
                "key": issue.get("key"),
                "self": issue.get("self"),
                "summary": fields_data.get("summary"),
                "status": fields_data.get("status", {}).get("name"),
                "issue_type": fields_data.get("issuetype", {}).get("name"),
                "priority": fields_data.get("priority", {}).get("name") if fields_data.get("priority") else None,
                "assignee": fields_data.get("assignee", {}).get("displayName") if fields_data.get("assignee") else None,
                "assignee_account_id": fields_data.get("assignee", {}).get("accountId") if fields_data.get("assignee") else None,
                "reporter": fields_data.get("reporter", {}).get("displayName") if fields_data.get("reporter") else None,
                "created": fields_data.get("created"),
                "updated": fields_data.get("updated"),
                "labels": fields_data.get("labels", []),
                "project": fields_data.get("project", {}).get("key"),
                "fields": fields_data,  # Include full fields for advanced use
            }
        }
    return result


def search_issues(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for Jira issues using JQL (Jira Query Language).

    Params:
        jql (str): JQL query string - required
        fields (list): List of fields to return (optional)
        max_results (int): Maximum number of results (default: 50, max: 100)
        start_at (int): Index of first result (for pagination, default: 0)

    Returns:
        List of matching issues
    """
    profile = load_profile(profile_name)

    jql = params.get("jql")
    if not jql:
        return {"ok": False, "error": "jql is required"}

    # Build request body
    request_data: Dict[str, Any] = {
        "jql": jql,
        "maxResults": min(params.get("max_results", 50), 100),
        "startAt": params.get("start_at", 0),
    }

    fields = params.get("fields")
    if fields:
        request_data["fields"] = fields if isinstance(fields, list) else [fields]

    result = _api_call(profile, "/rest/api/3/search", method="POST", data=request_data)

    if result.get("ok") and "result" in result:
        search_result = result["result"]
        issues = []

        for issue in search_result.get("issues", []):
            fields_data = issue.get("fields", {})
            issues.append({
                "id": issue.get("id"),
                "key": issue.get("key"),
                "summary": fields_data.get("summary"),
                "status": fields_data.get("status", {}).get("name"),
                "issue_type": fields_data.get("issuetype", {}).get("name"),
                "priority": fields_data.get("priority", {}).get("name") if fields_data.get("priority") else None,
                "assignee": fields_data.get("assignee", {}).get("displayName") if fields_data.get("assignee") else None,
                "created": fields_data.get("created"),
                "updated": fields_data.get("updated"),
            })

        return {
            "ok": True,
            "result": {
                "issues": issues,
                "total": search_result.get("total", 0),
                "start_at": search_result.get("startAt", 0),
                "max_results": search_result.get("maxResults", 0),
            }
        }
    return result


def add_comment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a comment to a Jira issue.

    Params:
        issue_key (str): Issue key (e.g., "PROJ-123") - required
        body (str): Comment text - required

    Returns:
        Created comment details
    """
    profile = load_profile(profile_name)

    issue_key = params.get("issue_key")
    body = params.get("body")

    if not issue_key:
        return {"ok": False, "error": "issue_key is required"}
    if not body:
        return {"ok": False, "error": "body is required"}

    # Jira Cloud uses ADF format for comments
    comment_data = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": body}
                    ]
                }
            ]
        }
    }

    endpoint = f"/rest/api/3/issue/{quote(issue_key)}/comment"
    result = _api_call(profile, endpoint, method="POST", data=comment_data)

    if result.get("ok") and "result" in result:
        comment = result["result"]
        return {
            "ok": True,
            "result": {
                "id": comment.get("id"),
                "issue_key": issue_key,
                "author": comment.get("author", {}).get("displayName"),
                "created": comment.get("created"),
            }
        }
    return result


def transition_issue(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transition a Jira issue to a different status.

    Params:
        issue_key (str): Issue key (e.g., "PROJ-123") - required
        transition_id (str): Transition ID - required
            Use get_issue with expand=["transitions"] to see available transitions

    Returns:
        Success status
    """
    profile = load_profile(profile_name)

    issue_key = params.get("issue_key")
    transition_id = params.get("transition_id")

    if not issue_key:
        return {"ok": False, "error": "issue_key is required"}
    if not transition_id:
        return {"ok": False, "error": "transition_id is required"}

    transition_data = {
        "transition": {"id": str(transition_id)}
    }

    endpoint = f"/rest/api/3/issue/{quote(issue_key)}/transitions"
    result = _api_call(profile, endpoint, method="POST", data=transition_data)

    if result.get("ok"):
        return {"ok": True, "result": {"issue_key": issue_key, "transitioned": True}}
    return result


def assign_issue(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assign a Jira issue to a user.

    Params:
        issue_key (str): Issue key (e.g., "PROJ-123") - required
        account_id (str): Account ID of the user to assign - required
            Use None or "-1" to unassign

    Returns:
        Success status
    """
    profile = load_profile(profile_name)

    issue_key = params.get("issue_key")
    account_id = params.get("account_id")

    if not issue_key:
        return {"ok": False, "error": "issue_key is required"}
    if account_id is None:
        return {"ok": False, "error": "account_id is required (use '-1' or null to unassign)"}

    # Handle unassign
    if account_id == "-1" or account_id == "":
        assignee_data = {"accountId": None}
    else:
        assignee_data = {"accountId": account_id}

    endpoint = f"/rest/api/3/issue/{quote(issue_key)}/assignee"
    result = _api_call(profile, endpoint, method="PUT", data=assignee_data)

    if result.get("ok"):
        return {"ok": True, "result": {"issue_key": issue_key, "assigned": True, "account_id": account_id}}
    return result


def list_projects(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List accessible Jira projects.

    Params:
        max_results (int): Maximum number of results (default: 50)
        start_at (int): Index of first result (for pagination, default: 0)
        expand (list): List of expansions (optional, e.g., ["description", "lead"])

    Returns:
        List of projects
    """
    profile = load_profile(profile_name)

    # Build query parameters
    query_params = {
        "maxResults": params.get("max_results", 50),
        "startAt": params.get("start_at", 0),
    }

    expand = params.get("expand")
    if expand:
        query_params["expand"] = ",".join(expand) if isinstance(expand, list) else expand

    endpoint = f"/rest/api/3/project/search?{urlencode(query_params)}"
    result = _api_call(profile, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        search_result = result["result"]
        projects = []

        for project in search_result.get("values", []):
            projects.append({
                "id": project.get("id"),
                "key": project.get("key"),
                "name": project.get("name"),
                "project_type": project.get("projectTypeKey"),
                "style": project.get("style"),
                "is_private": project.get("isPrivate"),
                "lead": project.get("lead", {}).get("displayName") if project.get("lead") else None,
            })

        return {
            "ok": True,
            "result": {
                "projects": projects,
                "total": search_result.get("total", len(projects)),
                "start_at": search_result.get("startAt", 0),
                "max_results": search_result.get("maxResults", 0),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "create_issue": create_issue,
    "update_issue": update_issue,
    "get_issue": get_issue,
    "search_issues": search_issues,
    "add_comment": add_comment,
    "transition_issue": transition_issue,
    "assign_issue": assign_issue,
    "list_projects": list_projects,
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
        logger.info(f"Executing jira.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
