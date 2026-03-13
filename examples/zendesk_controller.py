"""
Zendesk Controller for TinyHive

A controller for interacting with Zendesk Support API for ticket management
and user operations.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "subdomain": "yourcompany",
    "email_env": "ZENDESK_EMAIL",
    "token_env": "ZENDESK_API_TOKEN"
}

Required Permissions:
--------------------
- create_ticket: Tickets > Add
- update_ticket: Tickets > Edit
- get_ticket: Tickets > View
- list_tickets: Tickets > View
- add_comment: Tickets > Edit
- search_tickets: Tickets > View
- list_users: Users > View
- create_user: Users > Add

Dependencies:
------------
None (standard library only)

Method IDs:
  controller.zendesk.{profile}.create_ticket
  controller.zendesk.{profile}.update_ticket
  controller.zendesk.{profile}.get_ticket
  controller.zendesk.{profile}.list_tickets
  controller.zendesk.{profile}.add_comment
  controller.zendesk.{profile}.search_tickets
  controller.zendesk.{profile}.list_users
  controller.zendesk.{profile}.create_user
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

logger = logging.getLogger("tinyhive.controller.zendesk")

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
    """List available Zendesk profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# Authentication
# =============================================================================

def _get_auth_header(profile: Dict[str, Any]) -> str:
    """
    Get Basic Auth header for Zendesk API.

    Zendesk uses Basic Auth with email/token:api_token base64 encoded.
    """
    email_env = profile.get("email_env", "ZENDESK_EMAIL")
    token_env = profile.get("token_env", "ZENDESK_API_TOKEN")

    email = os.environ.get(email_env)
    token = os.environ.get(token_env)

    if not email:
        raise ValueError(f"Environment variable '{email_env}' not set")
    if not token:
        raise ValueError(f"Environment variable '{token_env}' not set")

    # Zendesk uses email/token:api_token format for API token auth
    credentials = f"{email}/token:{token}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


def _get_base_url(profile: Dict[str, Any]) -> str:
    """Get the Zendesk API base URL from profile subdomain."""
    subdomain = profile.get("subdomain")
    if not subdomain:
        raise ValueError("subdomain not configured in profile")
    return f"https://{subdomain}.zendesk.com/api/v2"


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
    Make an authenticated Zendesk API call.

    Args:
        profile: Profile configuration dict
        endpoint: API endpoint path (e.g., "/tickets.json")
        method: HTTP method
        data: Request body data (will be JSON encoded)
        timeout: Request timeout in seconds

    Returns:
        Dict with 'ok' boolean and either 'result' or 'error'
    """
    try:
        base_url = _get_base_url(profile)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    url = f"{base_url}{endpoint}"

    try:
        auth_header = _get_auth_header(profile)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    headers = {
        "Authorization": auth_header,
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
            # Zendesk returns errors in various formats
            if "error" in error_data:
                if isinstance(error_data["error"], dict):
                    error_message = error_data["error"].get("message", str(error_data["error"]))
                else:
                    error_message = str(error_data["error"])
                if "description" in error_data:
                    error_message += f": {error_data['description']}"
            elif "errors" in error_data:
                error_message = "; ".join(str(e) for e in error_data["errors"])
            elif "message" in error_data:
                error_message = error_data["message"]
            else:
                error_message = error_body[:500]
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Zendesk API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Zendesk API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def create_ticket(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new Zendesk ticket.

    Params:
        subject (str): Ticket subject - required
        description (str): Ticket description/first comment - required
        requester_id (int): Requester user ID - optional
        priority (str): Priority (low, normal, high, urgent) - optional
        type (str): Ticket type (problem, incident, question, task) - optional

    Returns:
        Created ticket details
    """
    profile = load_profile(profile_name)

    subject = params.get("subject")
    description = params.get("description")

    if not subject:
        return {"ok": False, "error": "subject is required"}
    if not description:
        return {"ok": False, "error": "description is required"}

    # Build ticket object
    ticket: Dict[str, Any] = {
        "subject": subject,
        "comment": {
            "body": description
        }
    }

    # Optional requester_id
    requester_id = params.get("requester_id")
    if requester_id is not None:
        ticket["requester_id"] = requester_id

    # Optional priority
    priority = params.get("priority")
    if priority:
        valid_priorities = ["low", "normal", "high", "urgent"]
        if priority.lower() not in valid_priorities:
            return {"ok": False, "error": f"Invalid priority. Must be one of: {valid_priorities}"}
        ticket["priority"] = priority.lower()

    # Optional type
    ticket_type = params.get("type")
    if ticket_type:
        valid_types = ["problem", "incident", "question", "task"]
        if ticket_type.lower() not in valid_types:
            return {"ok": False, "error": f"Invalid type. Must be one of: {valid_types}"}
        ticket["type"] = ticket_type.lower()

    result = _api_call(profile, "/tickets.json", method="POST", data={"ticket": ticket})

    if result.get("ok") and "result" in result:
        ticket_data = result["result"].get("ticket", {})
        return {
            "ok": True,
            "result": {
                "id": ticket_data.get("id"),
                "subject": ticket_data.get("subject"),
                "status": ticket_data.get("status"),
                "priority": ticket_data.get("priority"),
                "type": ticket_data.get("type"),
                "requester_id": ticket_data.get("requester_id"),
                "created_at": ticket_data.get("created_at"),
                "url": ticket_data.get("url"),
            }
        }
    return result


def update_ticket(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing Zendesk ticket.

    Params:
        ticket_id (int): Ticket ID - required
        status (str): New status (new, open, pending, hold, solved, closed) - optional
        priority (str): New priority (low, normal, high, urgent) - optional
        assignee_id (int): New assignee user ID - optional
        comment (str): Comment to add with the update - optional

    Returns:
        Updated ticket details
    """
    profile = load_profile(profile_name)

    ticket_id = params.get("ticket_id")
    if not ticket_id:
        return {"ok": False, "error": "ticket_id is required"}

    # Build ticket update object
    ticket: Dict[str, Any] = {}

    # Optional status
    status = params.get("status")
    if status:
        valid_statuses = ["new", "open", "pending", "hold", "solved", "closed"]
        if status.lower() not in valid_statuses:
            return {"ok": False, "error": f"Invalid status. Must be one of: {valid_statuses}"}
        ticket["status"] = status.lower()

    # Optional priority
    priority = params.get("priority")
    if priority:
        valid_priorities = ["low", "normal", "high", "urgent"]
        if priority.lower() not in valid_priorities:
            return {"ok": False, "error": f"Invalid priority. Must be one of: {valid_priorities}"}
        ticket["priority"] = priority.lower()

    # Optional assignee_id
    assignee_id = params.get("assignee_id")
    if assignee_id is not None:
        ticket["assignee_id"] = assignee_id

    # Optional comment
    comment = params.get("comment")
    if comment:
        ticket["comment"] = {"body": comment}

    if not ticket:
        return {"ok": False, "error": "At least one field to update is required"}

    endpoint = f"/tickets/{ticket_id}.json"
    result = _api_call(profile, endpoint, method="PUT", data={"ticket": ticket})

    if result.get("ok") and "result" in result:
        ticket_data = result["result"].get("ticket", {})
        return {
            "ok": True,
            "result": {
                "id": ticket_data.get("id"),
                "subject": ticket_data.get("subject"),
                "status": ticket_data.get("status"),
                "priority": ticket_data.get("priority"),
                "assignee_id": ticket_data.get("assignee_id"),
                "updated_at": ticket_data.get("updated_at"),
            }
        }
    return result


def get_ticket(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a Zendesk ticket.

    Params:
        ticket_id (int): Ticket ID - required

    Returns:
        Ticket details
    """
    profile = load_profile(profile_name)

    ticket_id = params.get("ticket_id")
    if not ticket_id:
        return {"ok": False, "error": "ticket_id is required"}

    endpoint = f"/tickets/{ticket_id}.json"
    result = _api_call(profile, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        ticket_data = result["result"].get("ticket", {})
        return {
            "ok": True,
            "result": {
                "id": ticket_data.get("id"),
                "subject": ticket_data.get("subject"),
                "description": ticket_data.get("description"),
                "status": ticket_data.get("status"),
                "priority": ticket_data.get("priority"),
                "type": ticket_data.get("type"),
                "requester_id": ticket_data.get("requester_id"),
                "submitter_id": ticket_data.get("submitter_id"),
                "assignee_id": ticket_data.get("assignee_id"),
                "organization_id": ticket_data.get("organization_id"),
                "group_id": ticket_data.get("group_id"),
                "tags": ticket_data.get("tags", []),
                "created_at": ticket_data.get("created_at"),
                "updated_at": ticket_data.get("updated_at"),
                "url": ticket_data.get("url"),
            }
        }
    return result


def list_tickets(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List Zendesk tickets.

    Params:
        status (str): Filter by status (new, open, pending, hold, solved, closed) - optional
        assignee_id (int): Filter by assignee user ID - optional
        per_page (int): Results per page (default: 25, max: 100) - optional

    Returns:
        List of tickets
    """
    profile = load_profile(profile_name)

    # Build query parameters
    query_params: Dict[str, Any] = {}

    per_page = params.get("per_page", 25)
    query_params["per_page"] = min(per_page, 100)

    # Determine endpoint based on filters
    status = params.get("status")
    assignee_id = params.get("assignee_id")

    if status:
        valid_statuses = ["new", "open", "pending", "hold", "solved", "closed"]
        if status.lower() not in valid_statuses:
            return {"ok": False, "error": f"Invalid status. Must be one of: {valid_statuses}"}
        # Use search endpoint for status filter
        query_params["query"] = f"type:ticket status:{status.lower()}"
        if assignee_id is not None:
            query_params["query"] += f" assignee:{assignee_id}"
        endpoint = f"/search.json?{urlencode(query_params)}"
    elif assignee_id is not None:
        query_params["query"] = f"type:ticket assignee:{assignee_id}"
        endpoint = f"/search.json?{urlencode(query_params)}"
    else:
        endpoint = f"/tickets.json?{urlencode(query_params)}"

    result = _api_call(profile, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        response_data = result["result"]
        # Handle both tickets list and search results
        tickets_data = response_data.get("tickets") or response_data.get("results", [])
        tickets = []

        for ticket in tickets_data:
            tickets.append({
                "id": ticket.get("id"),
                "subject": ticket.get("subject"),
                "status": ticket.get("status"),
                "priority": ticket.get("priority"),
                "type": ticket.get("type"),
                "requester_id": ticket.get("requester_id"),
                "assignee_id": ticket.get("assignee_id"),
                "created_at": ticket.get("created_at"),
                "updated_at": ticket.get("updated_at"),
            })

        return {
            "ok": True,
            "result": {
                "tickets": tickets,
                "count": response_data.get("count", len(tickets)),
                "next_page": response_data.get("next_page"),
                "previous_page": response_data.get("previous_page"),
            }
        }
    return result


def add_comment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a comment to a Zendesk ticket.

    Params:
        ticket_id (int): Ticket ID - required
        body (str): Comment body text - required
        public (bool): Whether the comment is public (default: True) - optional

    Returns:
        Updated ticket details
    """
    profile = load_profile(profile_name)

    ticket_id = params.get("ticket_id")
    body = params.get("body")

    if not ticket_id:
        return {"ok": False, "error": "ticket_id is required"}
    if not body:
        return {"ok": False, "error": "body is required"}

    # Build comment object
    public = params.get("public", True)
    comment = {
        "body": body,
        "public": public
    }

    endpoint = f"/tickets/{ticket_id}.json"
    result = _api_call(profile, endpoint, method="PUT", data={"ticket": {"comment": comment}})

    if result.get("ok") and "result" in result:
        ticket_data = result["result"].get("ticket", {})
        return {
            "ok": True,
            "result": {
                "ticket_id": ticket_data.get("id"),
                "subject": ticket_data.get("subject"),
                "status": ticket_data.get("status"),
                "updated_at": ticket_data.get("updated_at"),
                "comment_added": True,
            }
        }
    return result


def search_tickets(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for Zendesk tickets using the Search API.

    Params:
        query (str): Search query string - required
            Examples:
            - "status:open priority:high"
            - "assignee:me created>2024-01-01"
            - "subject:refund"

    Returns:
        List of matching tickets
    """
    profile = load_profile(profile_name)

    query = params.get("query")
    if not query:
        return {"ok": False, "error": "query is required"}

    # Ensure we're searching for tickets
    if "type:ticket" not in query.lower():
        query = f"type:ticket {query}"

    query_params = {
        "query": query
    }

    endpoint = f"/search.json?{urlencode(query_params)}"
    result = _api_call(profile, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        response_data = result["result"]
        tickets = []

        for ticket in response_data.get("results", []):
            tickets.append({
                "id": ticket.get("id"),
                "subject": ticket.get("subject"),
                "description": ticket.get("description"),
                "status": ticket.get("status"),
                "priority": ticket.get("priority"),
                "type": ticket.get("type"),
                "requester_id": ticket.get("requester_id"),
                "assignee_id": ticket.get("assignee_id"),
                "created_at": ticket.get("created_at"),
                "updated_at": ticket.get("updated_at"),
            })

        return {
            "ok": True,
            "result": {
                "tickets": tickets,
                "count": response_data.get("count", len(tickets)),
                "next_page": response_data.get("next_page"),
                "previous_page": response_data.get("previous_page"),
            }
        }
    return result


def list_users(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List Zendesk users.

    Params:
        role (str): Filter by role (end-user, agent, admin) - optional
        per_page (int): Results per page (default: 25, max: 100) - optional

    Returns:
        List of users
    """
    profile = load_profile(profile_name)

    # Build query parameters
    query_params: Dict[str, Any] = {}

    per_page = params.get("per_page", 25)
    query_params["per_page"] = min(per_page, 100)

    role = params.get("role")
    if role:
        valid_roles = ["end-user", "agent", "admin"]
        if role.lower() not in valid_roles:
            return {"ok": False, "error": f"Invalid role. Must be one of: {valid_roles}"}
        query_params["role"] = role.lower()

    endpoint = f"/users.json?{urlencode(query_params)}"
    result = _api_call(profile, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        response_data = result["result"]
        users = []

        for user in response_data.get("users", []):
            users.append({
                "id": user.get("id"),
                "name": user.get("name"),
                "email": user.get("email"),
                "role": user.get("role"),
                "active": user.get("active"),
                "verified": user.get("verified"),
                "created_at": user.get("created_at"),
                "updated_at": user.get("updated_at"),
            })

        return {
            "ok": True,
            "result": {
                "users": users,
                "count": response_data.get("count", len(users)),
                "next_page": response_data.get("next_page"),
                "previous_page": response_data.get("previous_page"),
            }
        }
    return result


def create_user(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new Zendesk user.

    Params:
        name (str): User name - required
        email (str): User email address - required
        role (str): User role (end-user, agent, admin) - optional, default: end-user

    Returns:
        Created user details
    """
    profile = load_profile(profile_name)

    name = params.get("name")
    email = params.get("email")

    if not name:
        return {"ok": False, "error": "name is required"}
    if not email:
        return {"ok": False, "error": "email is required"}

    # Build user object
    user: Dict[str, Any] = {
        "name": name,
        "email": email,
    }

    # Optional role
    role = params.get("role")
    if role:
        valid_roles = ["end-user", "agent", "admin"]
        if role.lower() not in valid_roles:
            return {"ok": False, "error": f"Invalid role. Must be one of: {valid_roles}"}
        user["role"] = role.lower()

    result = _api_call(profile, "/users.json", method="POST", data={"user": user})

    if result.get("ok") and "result" in result:
        user_data = result["result"].get("user", {})
        return {
            "ok": True,
            "result": {
                "id": user_data.get("id"),
                "name": user_data.get("name"),
                "email": user_data.get("email"),
                "role": user_data.get("role"),
                "active": user_data.get("active"),
                "verified": user_data.get("verified"),
                "created_at": user_data.get("created_at"),
                "url": user_data.get("url"),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "create_ticket": create_ticket,
    "update_ticket": update_ticket,
    "get_ticket": get_ticket,
    "list_tickets": list_tickets,
    "add_comment": add_comment,
    "search_tickets": search_tickets,
    "list_users": list_users,
    "create_user": create_user,
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
        logger.info(f"Executing zendesk.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
