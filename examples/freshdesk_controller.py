"""
Freshdesk Controller for TinyHive

A controller for integrating with Freshdesk helpdesk API.

Method IDs:
  controller.freshdesk.{profile}.list_tickets
  controller.freshdesk.{profile}.get_ticket
  controller.freshdesk.{profile}.create_ticket
  controller.freshdesk.{profile}.update_ticket
  controller.freshdesk.{profile}.add_reply
  controller.freshdesk.{profile}.list_contacts
  controller.freshdesk.{profile}.create_contact
  controller.freshdesk.{profile}.list_agents

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "domain": "yourcompany.freshdesk.com",
    "api_key_env": "FRESHDESK_API_KEY"
}

Required API Permissions:
------------------------
- Tickets: Read/Write access to tickets
- Contacts: Read/Write access to contacts
- Agents: Read access to agents

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
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.freshdesk")

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


# =============================================================================
# HTTP Helpers
# =============================================================================

def _get_auth_header(profile: Dict[str, Any]) -> str:
    """Get Basic auth header value from profile configuration."""
    api_key_env = profile.get("api_key_env", "FRESHDESK_API_KEY")
    api_key = os.environ.get(api_key_env)

    if not api_key:
        raise ValueError(f"Missing API key: {api_key_env} environment variable not set")

    # Freshdesk uses Basic auth with api_key:X
    credentials = f"{api_key}:X"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


def _get_base_url(profile: Dict[str, Any]) -> str:
    """Get the base API URL from profile configuration."""
    domain = profile.get("domain")
    if not domain:
        raise ValueError("Missing 'domain' in profile configuration")

    # Ensure domain doesn't have protocol
    if domain.startswith("https://"):
        domain = domain[8:]
    elif domain.startswith("http://"):
        domain = domain[7:]

    return f"https://{domain}/api/v2"


def _api_call(
    profile: Dict[str, Any],
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Freshdesk API call."""
    base_url = _get_base_url(profile)
    url = f"{base_url}{endpoint}"

    headers = {
        "Authorization": _get_auth_header(profile),
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
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            if "errors" in error_data:
                error_message = "; ".join(
                    err.get("message", str(err)) for err in error_data["errors"]
                )
            elif "message" in error_data:
                error_message = error_data["message"]
            else:
                error_message = error_body[:500]
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Freshdesk API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Freshdesk API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Ticket Actions
# =============================================================================

def list_tickets(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List tickets with optional filtering.

    Params:
        filter (str): Filter name - 'new_and_my_open', 'watching', 'spam', 'deleted',
                      or a custom filter ID (optional)
        per_page (int): Number of tickets per page (default: 30, max: 100)
        page (int): Page number (default: 1)
    """
    try:
        profile = load_profile(profile_name)

        query_params = {}
        if params.get("filter"):
            query_params["filter"] = params["filter"]
        if params.get("per_page"):
            query_params["per_page"] = min(int(params["per_page"]), 100)
        if params.get("page"):
            query_params["page"] = int(params["page"])

        endpoint = "/tickets"
        if query_params:
            endpoint += "?" + urlencode(query_params)

        result = _api_call(profile, endpoint)

        if result.get("ok") and "result" in result:
            tickets = result["result"]
            return {
                "ok": True,
                "data": {
                    "tickets": tickets,
                    "count": len(tickets)
                }
            }
        return result
    except Exception as e:
        logger.exception("list_tickets failed")
        return {"ok": False, "error": str(e)}


def get_ticket(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a single ticket by ID.

    Params:
        ticket_id (int): The ticket ID (required)
    """
    try:
        profile = load_profile(profile_name)

        ticket_id = params.get("ticket_id")
        if not ticket_id:
            return {"ok": False, "error": "ticket_id is required"}

        endpoint = f"/tickets/{ticket_id}"
        result = _api_call(profile, endpoint)

        if result.get("ok") and "result" in result:
            return {"ok": True, "data": result["result"]}
        return result
    except Exception as e:
        logger.exception("get_ticket failed")
        return {"ok": False, "error": str(e)}


def create_ticket(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new ticket.

    Params:
        subject (str): Ticket subject (required)
        description (str): Ticket description/body in HTML (required)
        email (str): Requester email address (required)
        priority (int): Priority: 1=Low, 2=Medium, 3=High, 4=Urgent (default: 1)
        status (int): Status: 2=Open, 3=Pending, 4=Resolved, 5=Closed (default: 2)
        type (str): Ticket type (optional)
        tags (list): List of tags (optional)
        cc_emails (list): List of CC email addresses (optional)
        custom_fields (dict): Custom field values (optional)
    """
    try:
        profile = load_profile(profile_name)

        # Validate required fields
        subject = params.get("subject")
        description = params.get("description")
        email = params.get("email")

        if not subject:
            return {"ok": False, "error": "subject is required"}
        if not description:
            return {"ok": False, "error": "description is required"}
        if not email:
            return {"ok": False, "error": "email is required"}

        # Build ticket data
        ticket_data = {
            "subject": subject,
            "description": description,
            "email": email,
            "priority": params.get("priority", 1),
            "status": params.get("status", 2),
        }

        # Optional fields
        if params.get("type"):
            ticket_data["type"] = params["type"]
        if params.get("tags"):
            ticket_data["tags"] = params["tags"]
        if params.get("cc_emails"):
            ticket_data["cc_emails"] = params["cc_emails"]
        if params.get("custom_fields"):
            ticket_data["custom_fields"] = params["custom_fields"]

        result = _api_call(profile, "/tickets", method="POST", data=ticket_data)

        if result.get("ok") and "result" in result:
            return {"ok": True, "data": result["result"]}
        return result
    except Exception as e:
        logger.exception("create_ticket failed")
        return {"ok": False, "error": str(e)}


def update_ticket(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing ticket.

    Params:
        ticket_id (int): The ticket ID (required)
        fields (dict): Fields to update (required). Supported fields:
            - subject (str): Ticket subject
            - description (str): Ticket description
            - priority (int): 1=Low, 2=Medium, 3=High, 4=Urgent
            - status (int): 2=Open, 3=Pending, 4=Resolved, 5=Closed
            - type (str): Ticket type
            - tags (list): List of tags
            - custom_fields (dict): Custom field values
    """
    try:
        profile = load_profile(profile_name)

        ticket_id = params.get("ticket_id")
        fields = params.get("fields")

        if not ticket_id:
            return {"ok": False, "error": "ticket_id is required"}
        if not fields:
            return {"ok": False, "error": "fields is required"}

        endpoint = f"/tickets/{ticket_id}"
        result = _api_call(profile, endpoint, method="PUT", data=fields)

        if result.get("ok") and "result" in result:
            return {"ok": True, "data": result["result"]}
        return result
    except Exception as e:
        logger.exception("update_ticket failed")
        return {"ok": False, "error": str(e)}


def add_reply(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a reply to a ticket.

    Params:
        ticket_id (int): The ticket ID (required)
        body (str): Reply body in HTML (required)
        cc_emails (list): List of CC email addresses (optional)
        bcc_emails (list): List of BCC email addresses (optional)
    """
    try:
        profile = load_profile(profile_name)

        ticket_id = params.get("ticket_id")
        body = params.get("body")

        if not ticket_id:
            return {"ok": False, "error": "ticket_id is required"}
        if not body:
            return {"ok": False, "error": "body is required"}

        reply_data = {"body": body}

        if params.get("cc_emails"):
            reply_data["cc_emails"] = params["cc_emails"]
        if params.get("bcc_emails"):
            reply_data["bcc_emails"] = params["bcc_emails"]

        endpoint = f"/tickets/{ticket_id}/reply"
        result = _api_call(profile, endpoint, method="POST", data=reply_data)

        if result.get("ok") and "result" in result:
            return {"ok": True, "data": result["result"]}
        return result
    except Exception as e:
        logger.exception("add_reply failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Contact Actions
# =============================================================================

def list_contacts(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List contacts with optional filtering.

    Params:
        email (str): Filter by email address (optional)
        phone (str): Filter by phone number (optional)
        per_page (int): Number of contacts per page (default: 30, max: 100)
        page (int): Page number (default: 1)
    """
    try:
        profile = load_profile(profile_name)

        query_params = {}
        if params.get("email"):
            query_params["email"] = params["email"]
        if params.get("phone"):
            query_params["phone"] = params["phone"]
        if params.get("per_page"):
            query_params["per_page"] = min(int(params["per_page"]), 100)
        if params.get("page"):
            query_params["page"] = int(params["page"])

        endpoint = "/contacts"
        if query_params:
            endpoint += "?" + urlencode(query_params)

        result = _api_call(profile, endpoint)

        if result.get("ok") and "result" in result:
            contacts = result["result"]
            return {
                "ok": True,
                "data": {
                    "contacts": contacts,
                    "count": len(contacts)
                }
            }
        return result
    except Exception as e:
        logger.exception("list_contacts failed")
        return {"ok": False, "error": str(e)}


def create_contact(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new contact.

    Params:
        name (str): Contact name (required)
        email (str): Contact email address (required)
        phone (str): Contact phone number (optional)
        mobile (str): Contact mobile number (optional)
        twitter_id (str): Twitter handle (optional)
        company_id (int): Company ID to associate (optional)
        description (str): Description/notes (optional)
        job_title (str): Job title (optional)
        custom_fields (dict): Custom field values (optional)
    """
    try:
        profile = load_profile(profile_name)

        name = params.get("name")
        email = params.get("email")

        if not name:
            return {"ok": False, "error": "name is required"}
        if not email:
            return {"ok": False, "error": "email is required"}

        contact_data = {
            "name": name,
            "email": email,
        }

        # Optional fields
        optional_fields = ["phone", "mobile", "twitter_id", "company_id",
                          "description", "job_title", "custom_fields"]
        for field in optional_fields:
            if params.get(field):
                contact_data[field] = params[field]

        result = _api_call(profile, "/contacts", method="POST", data=contact_data)

        if result.get("ok") and "result" in result:
            return {"ok": True, "data": result["result"]}
        return result
    except Exception as e:
        logger.exception("create_contact failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Agent Actions
# =============================================================================

def list_agents(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all agents.

    Params:
        email (str): Filter by email address (optional)
        per_page (int): Number of agents per page (default: 30, max: 100)
        page (int): Page number (default: 1)
    """
    try:
        profile = load_profile(profile_name)

        query_params = {}
        if params.get("email"):
            query_params["email"] = params["email"]
        if params.get("per_page"):
            query_params["per_page"] = min(int(params["per_page"]), 100)
        if params.get("page"):
            query_params["page"] = int(params["page"])

        endpoint = "/agents"
        if query_params:
            endpoint += "?" + urlencode(query_params)

        result = _api_call(profile, endpoint)

        if result.get("ok") and "result" in result:
            agents = result["result"]
            return {
                "ok": True,
                "data": {
                    "agents": agents,
                    "count": len(agents)
                }
            }
        return result
    except Exception as e:
        logger.exception("list_agents failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_tickets": list_tickets,
    "get_ticket": get_ticket,
    "create_ticket": create_ticket,
    "update_ticket": update_ticket,
    "add_reply": add_reply,
    "list_contacts": list_contacts,
    "create_contact": create_contact,
    "list_agents": list_agents,
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

    logger.info(f"Executing freshdesk.{profile}.{action}")
    return ACTIONS[action](profile, params)
