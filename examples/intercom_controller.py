"""Intercom Controller for TinyHive

A controller for Intercom API integration supporting contacts, conversations,
messages, and tags.

Method IDs:
  controller.intercom.{profile}.create_contact
  controller.intercom.{profile}.update_contact
  controller.intercom.{profile}.search_contacts
  controller.intercom.{profile}.send_message
  controller.intercom.{profile}.create_conversation
  controller.intercom.{profile}.reply_conversation
  controller.intercom.{profile}.list_conversations
  controller.intercom.{profile}.add_tag

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "token_env": "INTERCOM_ACCESS_TOKEN"
}

Required Scopes:
---------------
- Read and write contacts
- Read and write conversations
- Read and write messages
- Read and write tags

Dependencies:
------------
None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger("tinyhive.controller.intercom")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Intercom API base URL
INTERCOM_API_BASE = "https://api.intercom.io"

# Intercom API version
INTERCOM_VERSION = "2.10"

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
    """Get the Intercom access token from environment variable."""
    token_env = profile.get("token_env", "INTERCOM_ACCESS_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(
            f"Environment variable '{token_env}' not set. "
            "Set your Intercom access token in this environment variable."
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
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated Intercom API call.

    Args:
        token: Intercom access token
        endpoint: API endpoint (e.g., '/contacts')
        method: HTTP method (GET, POST, PUT, DELETE)
        data: Request payload
        timeout: Request timeout in seconds

    Returns:
        Response dict with 'ok' field and result/error
    """
    url = f"{INTERCOM_API_BASE}{endpoint}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Intercom-Version": INTERCOM_VERSION,
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
            error_message = error_data.get("message", error_body[:500])
            errors = error_data.get("errors", [])
            if errors:
                error_message = "; ".join(
                    err.get("message", str(err)) for err in errors
                )
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Intercom API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Intercom API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Contact Actions
# =============================================================================

def create_contact(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new contact in Intercom.

    Params:
        email (str): Contact email address (required for leads, optional for users)
        name (str): Contact name (optional)
        role (str): Contact role - 'user' or 'lead' (default: 'user')
        custom_attributes (dict): Custom attributes to set (optional)
        phone (str): Contact phone number (optional)
        external_id (str): External ID for the contact (optional)

    Returns:
        Contact ID and details on success.
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    role = params.get("role", "user")
    if role not in ["user", "lead"]:
        return {"ok": False, "error": "role must be 'user' or 'lead'"}

    email = params.get("email")
    if role == "lead" and not email:
        return {"ok": False, "error": "email is required for leads"}

    # Build request data
    data: Dict[str, Any] = {
        "role": role,
    }

    if email:
        data["email"] = email
    if params.get("name"):
        data["name"] = params["name"]
    if params.get("phone"):
        data["phone"] = params["phone"]
    if params.get("external_id"):
        data["external_id"] = params["external_id"]
    if params.get("custom_attributes"):
        data["custom_attributes"] = params["custom_attributes"]

    result = _api_call(token, "/contacts", method="POST", data=data)

    if result.get("ok") and "result" in result:
        contact = result["result"]
        return {
            "ok": True,
            "data": {
                "id": contact.get("id"),
                "external_id": contact.get("external_id"),
                "email": contact.get("email"),
                "name": contact.get("name"),
                "role": contact.get("role"),
                "custom_attributes": contact.get("custom_attributes", {}),
                "created_at": contact.get("created_at"),
            }
        }
    return result


def update_contact(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing contact in Intercom.

    Params:
        contact_id (str): Intercom contact ID (required)
        fields (dict): Fields to update (required)
            Supported fields: email, name, phone, custom_attributes, etc.

    Returns:
        Updated contact details on success.
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    contact_id = params.get("contact_id")
    if not contact_id:
        return {"ok": False, "error": "contact_id is required"}

    fields = params.get("fields")
    if not fields:
        return {"ok": False, "error": "fields is required"}

    result = _api_call(
        token,
        f"/contacts/{contact_id}",
        method="PUT",
        data=fields
    )

    if result.get("ok") and "result" in result:
        contact = result["result"]
        return {
            "ok": True,
            "data": {
                "id": contact.get("id"),
                "external_id": contact.get("external_id"),
                "email": contact.get("email"),
                "name": contact.get("name"),
                "role": contact.get("role"),
                "custom_attributes": contact.get("custom_attributes", {}),
                "updated_at": contact.get("updated_at"),
            }
        }
    return result


def search_contacts(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for contacts in Intercom.

    Params:
        query (dict): Search query object (required)
            Simple query: {"field": "email", "operator": "=", "value": "user@example.com"}
            Compound query: {"operator": "AND", "value": [<query>, <query>]}
            Operators: =, !=, IN, NIN, <, >, ~, !~, ^, $
        per_page (int): Results per page (default: 50, max: 150)
        starting_after (str): Pagination cursor (optional)

    Returns:
        List of matching contacts.
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    query = params.get("query")
    if not query:
        return {"ok": False, "error": "query is required"}

    data: Dict[str, Any] = {
        "query": query,
    }

    pagination: Dict[str, Any] = {}
    per_page = params.get("per_page", 50)
    pagination["per_page"] = min(per_page, 150)

    if params.get("starting_after"):
        pagination["starting_after"] = params["starting_after"]

    if pagination:
        data["pagination"] = pagination

    result = _api_call(token, "/contacts/search", method="POST", data=data)

    if result.get("ok") and "result" in result:
        response = result["result"]
        contacts = []
        for contact in response.get("data", []):
            contacts.append({
                "id": contact.get("id"),
                "external_id": contact.get("external_id"),
                "email": contact.get("email"),
                "name": contact.get("name"),
                "role": contact.get("role"),
                "custom_attributes": contact.get("custom_attributes", {}),
            })

        return {
            "ok": True,
            "data": {
                "contacts": contacts,
                "total_count": response.get("total_count", len(contacts)),
                "pages": response.get("pages"),
            }
        }
    return result


# =============================================================================
# Message Actions
# =============================================================================

def send_message(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a message in Intercom.

    Params:
        message_type (str): Type of message - 'in_app' or 'email' (required)
        body (str): Message body (required)
        from (dict): Sender info (required)
            For admin: {"type": "admin", "id": "admin_id"}
        to (dict): Recipient info (required)
            For user: {"type": "user", "id": "user_id"} or {"type": "user", "email": "email"}
        subject (str): Email subject (required for email type)
        template (str): Email template - 'plain' or 'personal' (optional, for email)

    Returns:
        Message details on success.
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    message_type = params.get("message_type")
    if not message_type:
        return {"ok": False, "error": "message_type is required"}
    if message_type not in ["in_app", "email"]:
        return {"ok": False, "error": "message_type must be 'in_app' or 'email'"}

    body = params.get("body")
    if not body:
        return {"ok": False, "error": "body is required"}

    from_data = params.get("from")
    if not from_data:
        return {"ok": False, "error": "from is required"}

    to_data = params.get("to")
    if not to_data:
        return {"ok": False, "error": "to is required"}

    if message_type == "email" and not params.get("subject"):
        return {"ok": False, "error": "subject is required for email messages"}

    data: Dict[str, Any] = {
        "message_type": message_type,
        "body": body,
        "from": from_data,
        "to": to_data,
    }

    if params.get("subject"):
        data["subject"] = params["subject"]
    if params.get("template"):
        data["template"] = params["template"]

    result = _api_call(token, "/messages", method="POST", data=data)

    if result.get("ok") and "result" in result:
        message = result["result"]
        return {
            "ok": True,
            "data": {
                "type": message.get("type"),
                "id": message.get("id"),
                "body": message.get("body"),
                "message_type": message.get("message_type"),
                "created_at": message.get("created_at"),
            }
        }
    return result


# =============================================================================
# Conversation Actions
# =============================================================================

def create_conversation(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new conversation in Intercom (user-initiated).

    Params:
        user_id (str): Intercom user/contact ID (required)
        body (str): Initial message body (required)

    Returns:
        Conversation details on success.
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    user_id = params.get("user_id")
    if not user_id:
        return {"ok": False, "error": "user_id is required"}

    body = params.get("body")
    if not body:
        return {"ok": False, "error": "body is required"}

    data: Dict[str, Any] = {
        "from": {
            "type": "user",
            "id": user_id,
        },
        "body": body,
    }

    result = _api_call(token, "/conversations", method="POST", data=data)

    if result.get("ok") and "result" in result:
        conversation = result["result"]
        return {
            "ok": True,
            "data": {
                "type": conversation.get("type"),
                "id": conversation.get("id"),
                "created_at": conversation.get("created_at"),
                "state": conversation.get("state"),
                "source": conversation.get("source"),
            }
        }
    return result


def reply_conversation(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reply to an existing conversation in Intercom.

    Params:
        conversation_id (str): Conversation ID (required)
        body (str): Reply message body (required)
        type (str): Reply type - 'admin' or 'user' (required)
        admin_id (str): Admin ID (required if type is 'admin')
        user_id (str): User/contact ID (required if type is 'user')
        message_type (str): Message type - 'comment' or 'note' (default: 'comment')
        attachment_urls (list): List of attachment URLs (optional)

    Returns:
        Conversation details on success.
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    conversation_id = params.get("conversation_id")
    if not conversation_id:
        return {"ok": False, "error": "conversation_id is required"}

    body = params.get("body")
    if not body:
        return {"ok": False, "error": "body is required"}

    reply_type = params.get("type")
    if not reply_type:
        return {"ok": False, "error": "type is required"}
    if reply_type not in ["admin", "user"]:
        return {"ok": False, "error": "type must be 'admin' or 'user'"}

    data: Dict[str, Any] = {
        "body": body,
        "type": reply_type,
        "message_type": params.get("message_type", "comment"),
    }

    if reply_type == "admin":
        admin_id = params.get("admin_id")
        if not admin_id:
            return {"ok": False, "error": "admin_id is required when type is 'admin'"}
        data["admin_id"] = admin_id
    else:
        user_id = params.get("user_id")
        if not user_id:
            return {"ok": False, "error": "user_id is required when type is 'user'"}
        data["intercom_user_id"] = user_id

    if params.get("attachment_urls"):
        data["attachment_urls"] = params["attachment_urls"]

    result = _api_call(
        token,
        f"/conversations/{conversation_id}/reply",
        method="POST",
        data=data
    )

    if result.get("ok") and "result" in result:
        conversation = result["result"]
        return {
            "ok": True,
            "data": {
                "type": conversation.get("type"),
                "id": conversation.get("id"),
                "state": conversation.get("state"),
                "conversation_parts": conversation.get("conversation_parts"),
            }
        }
    return result


def list_conversations(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List conversations in Intercom.

    Params:
        state (str): Filter by state - 'open', 'closed', 'snoozed' (optional)
        per_page (int): Results per page (default: 20, max: 150)
        starting_after (str): Pagination cursor (optional)

    Returns:
        List of conversations.
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    # Build query parameters
    query_parts = []

    state = params.get("state")
    if state:
        if state not in ["open", "closed", "snoozed"]:
            return {"ok": False, "error": "state must be 'open', 'closed', or 'snoozed'"}
        query_parts.append(f"state={state}")

    per_page = params.get("per_page", 20)
    per_page = min(per_page, 150)
    query_parts.append(f"per_page={per_page}")

    if params.get("starting_after"):
        query_parts.append(f"starting_after={params['starting_after']}")

    endpoint = "/conversations"
    if query_parts:
        endpoint += "?" + "&".join(query_parts)

    result = _api_call(token, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        response = result["result"]
        conversations = []
        for conv in response.get("conversations", []):
            conversations.append({
                "id": conv.get("id"),
                "state": conv.get("state"),
                "created_at": conv.get("created_at"),
                "updated_at": conv.get("updated_at"),
                "title": conv.get("title"),
                "source": conv.get("source"),
                "contacts": conv.get("contacts"),
            })

        return {
            "ok": True,
            "data": {
                "conversations": conversations,
                "total_count": response.get("total_count", len(conversations)),
                "pages": response.get("pages"),
            }
        }
    return result


# =============================================================================
# Tag Actions
# =============================================================================

def add_tag(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a tag to a contact in Intercom.

    Params:
        contact_id (str): Contact ID to tag (required)
        tag_name (str): Name of the tag to add (required)

    Returns:
        Tag details on success.
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    contact_id = params.get("contact_id")
    if not contact_id:
        return {"ok": False, "error": "contact_id is required"}

    tag_name = params.get("tag_name")
    if not tag_name:
        return {"ok": False, "error": "tag_name is required"}

    data: Dict[str, Any] = {
        "name": tag_name,
        "users": [{"id": contact_id}],
    }

    result = _api_call(token, "/tags", method="POST", data=data)

    if result.get("ok") and "result" in result:
        tag = result["result"]
        return {
            "ok": True,
            "data": {
                "type": tag.get("type"),
                "id": tag.get("id"),
                "name": tag.get("name"),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "create_contact": create_contact,
    "update_contact": update_contact,
    "search_contacts": search_contacts,
    "send_message": send_message,
    "create_conversation": create_conversation,
    "reply_conversation": reply_conversation,
    "list_conversations": list_conversations,
    "add_tag": add_tag,
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
        logger.info(f"Executing intercom.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
