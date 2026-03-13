"""
Linear Controller for TinyHive

A controller for interacting with Linear GraphQL API for issue tracking
and project management.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "api_key_env": "LINEAR_API_KEY"
}

Required Permissions (Linear API Key):
--------------------------------------
- list_issues: read access to issues
- get_issue: read access to issues
- create_issue: write access to issues
- update_issue: write access to issues
- add_comment: write access to comments
- list_teams: read access to teams
- list_projects: read access to projects
- list_cycles: read access to cycles

Dependencies:
------------
None (standard library only)

Method IDs:
  controller.linear.{profile}.list_issues
  controller.linear.{profile}.get_issue
  controller.linear.{profile}.create_issue
  controller.linear.{profile}.update_issue
  controller.linear.{profile}.add_comment
  controller.linear.{profile}.list_teams
  controller.linear.{profile}.list_projects
  controller.linear.{profile}.list_cycles
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger("tinyhive.controller.linear")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

LINEAR_API_URL = "https://api.linear.app/graphql"
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


def _get_api_key(profile: Dict[str, Any]) -> str:
    """Get Linear API key from environment variable specified in profile."""
    api_key_env = profile.get("api_key_env", "LINEAR_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ValueError(f"Environment variable '{api_key_env}' not set")
    return api_key


# =============================================================================
# GraphQL Helper
# =============================================================================

def _graphql_call(
    api_key: str,
    query: str,
    variables: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated Linear GraphQL API call.

    Args:
        api_key: Linear API key
        query: GraphQL query string
        variables: GraphQL variables dict
        timeout: Request timeout in seconds

    Returns:
        Dict with 'ok' boolean and either 'data' or 'error'
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    body = json.dumps(payload).encode("utf-8")

    try:
        req = Request(LINEAR_API_URL, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            result = json.loads(response_body)

            # GraphQL can return errors even with 200 status
            if "errors" in result:
                error_messages = [e.get("message", str(e)) for e in result["errors"]]
                error_str = "; ".join(error_messages)
                logger.error("Linear GraphQL error: %s", error_str)
                return {"ok": False, "error": f"GraphQL error: {error_str}"}

            return {"ok": True, "data": result.get("data", {})}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            if "errors" in error_data:
                error_messages = [err.get("message", str(err)) for err in error_data["errors"]]
                error_message = "; ".join(error_messages)
            else:
                error_message = error_data.get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Linear API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Linear API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def list_issues(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List issues with optional filtering.

    Params:
        team_id (str): Filter by team ID (optional)
        state (str): Filter by state name (e.g., "In Progress", "Done") (optional)
        assignee_id (str): Filter by assignee user ID (optional)
        limit (int): Maximum number of issues to return (default: 50, max: 250)

    Returns:
        List of issues with basic details
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    limit = min(params.get("limit", 50), 250)

    # Build filter conditions
    filter_parts = []
    if params.get("team_id"):
        filter_parts.append(f'team: {{ id: {{ eq: "{params["team_id"]}" }} }}')
    if params.get("state"):
        filter_parts.append(f'state: {{ name: {{ eq: "{params["state"]}" }} }}')
    if params.get("assignee_id"):
        filter_parts.append(f'assignee: {{ id: {{ eq: "{params["assignee_id"]}" }} }}')

    filter_clause = ""
    if filter_parts:
        filter_clause = f"filter: {{ {', '.join(filter_parts)} }}"

    query = f"""
    query ListIssues {{
        issues(first: {limit}, {filter_clause}) {{
            nodes {{
                id
                identifier
                title
                description
                priority
                priorityLabel
                state {{
                    id
                    name
                    color
                }}
                assignee {{
                    id
                    name
                    email
                }}
                team {{
                    id
                    name
                    key
                }}
                project {{
                    id
                    name
                }}
                labels {{
                    nodes {{
                        id
                        name
                        color
                    }}
                }}
                createdAt
                updatedAt
                url
            }}
            pageInfo {{
                hasNextPage
                endCursor
            }}
        }}
    }}
    """

    result = _graphql_call(api_key, query)

    if result.get("ok") and "data" in result:
        issues_data = result["data"].get("issues", {})
        nodes = issues_data.get("nodes", [])
        page_info = issues_data.get("pageInfo", {})

        issues = []
        for node in nodes:
            issues.append({
                "id": node.get("id"),
                "identifier": node.get("identifier"),
                "title": node.get("title"),
                "description": node.get("description"),
                "priority": node.get("priority"),
                "priority_label": node.get("priorityLabel"),
                "state": node.get("state"),
                "assignee": node.get("assignee"),
                "team": node.get("team"),
                "project": node.get("project"),
                "labels": [l for l in node.get("labels", {}).get("nodes", [])],
                "created_at": node.get("createdAt"),
                "updated_at": node.get("updatedAt"),
                "url": node.get("url"),
            })

        return {
            "ok": True,
            "result": {
                "issues": issues,
                "count": len(issues),
                "has_next_page": page_info.get("hasNextPage", False),
                "end_cursor": page_info.get("endCursor"),
            }
        }
    return result


def get_issue(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get detailed information about a specific issue.

    Params:
        issue_id (str): The issue ID (required)

    Returns:
        Issue details including comments
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    issue_id = params.get("issue_id")
    if not issue_id:
        return {"ok": False, "error": "issue_id is required"}

    query = """
    query GetIssue($id: String!) {
        issue(id: $id) {
            id
            identifier
            title
            description
            priority
            priorityLabel
            estimate
            state {
                id
                name
                color
                type
            }
            assignee {
                id
                name
                email
            }
            creator {
                id
                name
                email
            }
            team {
                id
                name
                key
            }
            project {
                id
                name
            }
            cycle {
                id
                name
                number
            }
            parent {
                id
                identifier
                title
            }
            labels {
                nodes {
                    id
                    name
                    color
                }
            }
            comments {
                nodes {
                    id
                    body
                    createdAt
                    user {
                        id
                        name
                    }
                }
            }
            createdAt
            updatedAt
            completedAt
            canceledAt
            dueDate
            url
        }
    }
    """

    result = _graphql_call(api_key, query, {"id": issue_id})

    if result.get("ok") and "data" in result:
        issue = result["data"].get("issue")
        if not issue:
            return {"ok": False, "error": f"Issue not found: {issue_id}"}

        return {
            "ok": True,
            "result": {
                "id": issue.get("id"),
                "identifier": issue.get("identifier"),
                "title": issue.get("title"),
                "description": issue.get("description"),
                "priority": issue.get("priority"),
                "priority_label": issue.get("priorityLabel"),
                "estimate": issue.get("estimate"),
                "state": issue.get("state"),
                "assignee": issue.get("assignee"),
                "creator": issue.get("creator"),
                "team": issue.get("team"),
                "project": issue.get("project"),
                "cycle": issue.get("cycle"),
                "parent": issue.get("parent"),
                "labels": [l for l in issue.get("labels", {}).get("nodes", [])],
                "comments": [c for c in issue.get("comments", {}).get("nodes", [])],
                "created_at": issue.get("createdAt"),
                "updated_at": issue.get("updatedAt"),
                "completed_at": issue.get("completedAt"),
                "canceled_at": issue.get("canceledAt"),
                "due_date": issue.get("dueDate"),
                "url": issue.get("url"),
            }
        }
    return result


def create_issue(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new issue.

    Params:
        team_id (str): Team ID to create the issue in (required)
        title (str): Issue title (required)
        description (str): Issue description/body (optional)
        priority (int): Priority level 0-4 (0=none, 1=urgent, 2=high, 3=medium, 4=low) (optional)
        assignee_id (str): User ID to assign the issue to (optional)
        labels (list): List of label IDs to apply (optional)
        project_id (str): Project ID to add the issue to (optional)
        cycle_id (str): Cycle ID to add the issue to (optional)
        state_id (str): Initial state ID (optional)
        estimate (int): Story points estimate (optional)
        due_date (str): Due date in ISO format YYYY-MM-DD (optional)
        parent_id (str): Parent issue ID for sub-issues (optional)

    Returns:
        Created issue details
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    team_id = params.get("team_id")
    title = params.get("title")

    if not team_id:
        return {"ok": False, "error": "team_id is required"}
    if not title:
        return {"ok": False, "error": "title is required"}

    # Build input object
    input_fields = [
        f'teamId: "{team_id}"',
        f'title: "{_escape_graphql_string(title)}"',
    ]

    if params.get("description"):
        input_fields.append(f'description: "{_escape_graphql_string(params["description"])}"')
    if params.get("priority") is not None:
        input_fields.append(f'priority: {params["priority"]}')
    if params.get("assignee_id"):
        input_fields.append(f'assigneeId: "{params["assignee_id"]}"')
    if params.get("project_id"):
        input_fields.append(f'projectId: "{params["project_id"]}"')
    if params.get("cycle_id"):
        input_fields.append(f'cycleId: "{params["cycle_id"]}"')
    if params.get("state_id"):
        input_fields.append(f'stateId: "{params["state_id"]}"')
    if params.get("estimate") is not None:
        input_fields.append(f'estimate: {params["estimate"]}')
    if params.get("due_date"):
        input_fields.append(f'dueDate: "{params["due_date"]}"')
    if params.get("parent_id"):
        input_fields.append(f'parentId: "{params["parent_id"]}"')
    if params.get("labels"):
        label_ids = ", ".join(f'"{lid}"' for lid in params["labels"])
        input_fields.append(f'labelIds: [{label_ids}]')

    input_str = ", ".join(input_fields)

    query = f"""
    mutation CreateIssue {{
        issueCreate(input: {{ {input_str} }}) {{
            success
            issue {{
                id
                identifier
                title
                url
                state {{
                    id
                    name
                }}
                team {{
                    id
                    name
                    key
                }}
                createdAt
            }}
        }}
    }}
    """

    result = _graphql_call(api_key, query)

    if result.get("ok") and "data" in result:
        create_data = result["data"].get("issueCreate", {})
        if not create_data.get("success"):
            return {"ok": False, "error": "Failed to create issue"}

        issue = create_data.get("issue", {})
        return {
            "ok": True,
            "result": {
                "id": issue.get("id"),
                "identifier": issue.get("identifier"),
                "title": issue.get("title"),
                "url": issue.get("url"),
                "state": issue.get("state"),
                "team": issue.get("team"),
                "created_at": issue.get("createdAt"),
            }
        }
    return result


def update_issue(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing issue.

    Params:
        issue_id (str): The issue ID to update (required)
        title (str): New title (optional)
        description (str): New description (optional)
        state_id (str): New state ID (optional)
        priority (int): New priority 0-4 (optional)
        assignee_id (str): New assignee user ID (optional)
        project_id (str): New project ID (optional)
        cycle_id (str): New cycle ID (optional)
        estimate (int): New estimate (optional)
        due_date (str): New due date in ISO format (optional)
        labels (list): New list of label IDs (replaces existing) (optional)

    Returns:
        Updated issue details
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    issue_id = params.get("issue_id")
    if not issue_id:
        return {"ok": False, "error": "issue_id is required"}

    # Build input object
    input_fields = []

    if params.get("title"):
        input_fields.append(f'title: "{_escape_graphql_string(params["title"])}"')
    if params.get("description"):
        input_fields.append(f'description: "{_escape_graphql_string(params["description"])}"')
    if params.get("state_id"):
        input_fields.append(f'stateId: "{params["state_id"]}"')
    if params.get("priority") is not None:
        input_fields.append(f'priority: {params["priority"]}')
    if params.get("assignee_id"):
        input_fields.append(f'assigneeId: "{params["assignee_id"]}"')
    if params.get("project_id"):
        input_fields.append(f'projectId: "{params["project_id"]}"')
    if params.get("cycle_id"):
        input_fields.append(f'cycleId: "{params["cycle_id"]}"')
    if params.get("estimate") is not None:
        input_fields.append(f'estimate: {params["estimate"]}')
    if params.get("due_date"):
        input_fields.append(f'dueDate: "{params["due_date"]}"')
    if params.get("labels"):
        label_ids = ", ".join(f'"{lid}"' for lid in params["labels"])
        input_fields.append(f'labelIds: [{label_ids}]')

    if not input_fields:
        return {"ok": False, "error": "At least one field to update is required"}

    input_str = ", ".join(input_fields)

    query = f"""
    mutation UpdateIssue {{
        issueUpdate(id: "{issue_id}", input: {{ {input_str} }}) {{
            success
            issue {{
                id
                identifier
                title
                url
                state {{
                    id
                    name
                }}
                priority
                priorityLabel
                assignee {{
                    id
                    name
                }}
                updatedAt
            }}
        }}
    }}
    """

    result = _graphql_call(api_key, query)

    if result.get("ok") and "data" in result:
        update_data = result["data"].get("issueUpdate", {})
        if not update_data.get("success"):
            return {"ok": False, "error": "Failed to update issue"}

        issue = update_data.get("issue", {})
        return {
            "ok": True,
            "result": {
                "id": issue.get("id"),
                "identifier": issue.get("identifier"),
                "title": issue.get("title"),
                "url": issue.get("url"),
                "state": issue.get("state"),
                "priority": issue.get("priority"),
                "priority_label": issue.get("priorityLabel"),
                "assignee": issue.get("assignee"),
                "updated_at": issue.get("updatedAt"),
            }
        }
    return result


def add_comment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a comment to an issue.

    Params:
        issue_id (str): The issue ID to comment on (required)
        body (str): Comment body/text (required)

    Returns:
        Created comment details
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    issue_id = params.get("issue_id")
    body = params.get("body")

    if not issue_id:
        return {"ok": False, "error": "issue_id is required"}
    if not body:
        return {"ok": False, "error": "body is required"}

    query = f"""
    mutation AddComment {{
        commentCreate(input: {{
            issueId: "{issue_id}",
            body: "{_escape_graphql_string(body)}"
        }}) {{
            success
            comment {{
                id
                body
                createdAt
                user {{
                    id
                    name
                    email
                }}
                issue {{
                    id
                    identifier
                }}
            }}
        }}
    }}
    """

    result = _graphql_call(api_key, query)

    if result.get("ok") and "data" in result:
        create_data = result["data"].get("commentCreate", {})
        if not create_data.get("success"):
            return {"ok": False, "error": "Failed to add comment"}

        comment = create_data.get("comment", {})
        return {
            "ok": True,
            "result": {
                "id": comment.get("id"),
                "body": comment.get("body"),
                "created_at": comment.get("createdAt"),
                "user": comment.get("user"),
                "issue": comment.get("issue"),
            }
        }
    return result


def list_teams(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all teams in the workspace.

    Params:
        limit (int): Maximum number of teams to return (default: 50)

    Returns:
        List of teams
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    limit = min(params.get("limit", 50), 250)

    query = f"""
    query ListTeams {{
        teams(first: {limit}) {{
            nodes {{
                id
                name
                key
                description
                icon
                color
                private
                timezone
                states {{
                    nodes {{
                        id
                        name
                        color
                        type
                        position
                    }}
                }}
                labels {{
                    nodes {{
                        id
                        name
                        color
                    }}
                }}
                createdAt
            }}
            pageInfo {{
                hasNextPage
                endCursor
            }}
        }}
    }}
    """

    result = _graphql_call(api_key, query)

    if result.get("ok") and "data" in result:
        teams_data = result["data"].get("teams", {})
        nodes = teams_data.get("nodes", [])
        page_info = teams_data.get("pageInfo", {})

        teams = []
        for node in nodes:
            teams.append({
                "id": node.get("id"),
                "name": node.get("name"),
                "key": node.get("key"),
                "description": node.get("description"),
                "icon": node.get("icon"),
                "color": node.get("color"),
                "private": node.get("private"),
                "timezone": node.get("timezone"),
                "states": [s for s in node.get("states", {}).get("nodes", [])],
                "labels": [l for l in node.get("labels", {}).get("nodes", [])],
                "created_at": node.get("createdAt"),
            })

        return {
            "ok": True,
            "result": {
                "teams": teams,
                "count": len(teams),
                "has_next_page": page_info.get("hasNextPage", False),
                "end_cursor": page_info.get("endCursor"),
            }
        }
    return result


def list_projects(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List projects, optionally filtered by team.

    Params:
        team_id (str): Filter by team ID (optional)
        limit (int): Maximum number of projects to return (default: 50)

    Returns:
        List of projects
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    limit = min(params.get("limit", 50), 250)

    # Build filter clause
    filter_clause = ""
    if params.get("team_id"):
        filter_clause = f'filter: {{ accessibleTeams: {{ id: {{ eq: "{params["team_id"]}" }} }} }}'

    query = f"""
    query ListProjects {{
        projects(first: {limit}, {filter_clause}) {{
            nodes {{
                id
                name
                description
                icon
                color
                state
                progress
                startDate
                targetDate
                lead {{
                    id
                    name
                    email
                }}
                teams {{
                    nodes {{
                        id
                        name
                        key
                    }}
                }}
                createdAt
                updatedAt
                url
            }}
            pageInfo {{
                hasNextPage
                endCursor
            }}
        }}
    }}
    """

    result = _graphql_call(api_key, query)

    if result.get("ok") and "data" in result:
        projects_data = result["data"].get("projects", {})
        nodes = projects_data.get("nodes", [])
        page_info = projects_data.get("pageInfo", {})

        projects = []
        for node in nodes:
            projects.append({
                "id": node.get("id"),
                "name": node.get("name"),
                "description": node.get("description"),
                "icon": node.get("icon"),
                "color": node.get("color"),
                "state": node.get("state"),
                "progress": node.get("progress"),
                "start_date": node.get("startDate"),
                "target_date": node.get("targetDate"),
                "lead": node.get("lead"),
                "teams": [t for t in node.get("teams", {}).get("nodes", [])],
                "created_at": node.get("createdAt"),
                "updated_at": node.get("updatedAt"),
                "url": node.get("url"),
            })

        return {
            "ok": True,
            "result": {
                "projects": projects,
                "count": len(projects),
                "has_next_page": page_info.get("hasNextPage", False),
                "end_cursor": page_info.get("endCursor"),
            }
        }
    return result


def list_cycles(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List cycles (sprints) for a team.

    Params:
        team_id (str): Team ID to list cycles for (required)
        limit (int): Maximum number of cycles to return (default: 50)

    Returns:
        List of cycles/sprints
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    team_id = params.get("team_id")
    if not team_id:
        return {"ok": False, "error": "team_id is required"}

    limit = min(params.get("limit", 50), 250)

    query = f"""
    query ListCycles {{
        cycles(first: {limit}, filter: {{ team: {{ id: {{ eq: "{team_id}" }} }} }}) {{
            nodes {{
                id
                name
                number
                description
                startsAt
                endsAt
                completedAt
                progress
                scopeProgress
                team {{
                    id
                    name
                    key
                }}
                issues {{
                    nodes {{
                        id
                        identifier
                        title
                    }}
                }}
                createdAt
                updatedAt
            }}
            pageInfo {{
                hasNextPage
                endCursor
            }}
        }}
    }}
    """

    result = _graphql_call(api_key, query)

    if result.get("ok") and "data" in result:
        cycles_data = result["data"].get("cycles", {})
        nodes = cycles_data.get("nodes", [])
        page_info = cycles_data.get("pageInfo", {})

        cycles = []
        for node in nodes:
            cycles.append({
                "id": node.get("id"),
                "name": node.get("name"),
                "number": node.get("number"),
                "description": node.get("description"),
                "starts_at": node.get("startsAt"),
                "ends_at": node.get("endsAt"),
                "completed_at": node.get("completedAt"),
                "progress": node.get("progress"),
                "scope_progress": node.get("scopeProgress"),
                "team": node.get("team"),
                "issues": [i for i in node.get("issues", {}).get("nodes", [])],
                "created_at": node.get("createdAt"),
                "updated_at": node.get("updatedAt"),
            })

        return {
            "ok": True,
            "result": {
                "cycles": cycles,
                "count": len(cycles),
                "has_next_page": page_info.get("hasNextPage", False),
                "end_cursor": page_info.get("endCursor"),
            }
        }
    return result


# =============================================================================
# Helper Functions
# =============================================================================

def _escape_graphql_string(s: str) -> str:
    """Escape a string for safe inclusion in a GraphQL query."""
    if not s:
        return ""
    # Escape backslashes first, then quotes, then newlines
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_issues": list_issues,
    "get_issue": get_issue,
    "create_issue": create_issue,
    "update_issue": update_issue,
    "add_comment": add_comment,
    "list_teams": list_teams,
    "list_projects": list_projects,
    "list_cycles": list_cycles,
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
        logger.info(f"Executing linear.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
