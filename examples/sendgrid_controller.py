"""SendGrid Controller for TinyHive

A controller for SendGrid API v3 integration supporting transactional email,
templates, contacts, lists, and analytics.

Method IDs:
  controller.sendgrid.{profile}.send_email
  controller.sendgrid.{profile}.send_template
  controller.sendgrid.{profile}.add_contact
  controller.sendgrid.{profile}.list_contacts
  controller.sendgrid.{profile}.create_list
  controller.sendgrid.{profile}.get_stats
  controller.sendgrid.{profile}.validate_email
  controller.sendgrid.{profile}.list_templates

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "api_key_env": "SENDGRID_API_KEY"
}

Environment Variables:
---------------------
- SENDGRID_API_KEY: SendGrid API key

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

logger = logging.getLogger("tinyhive.controller.sendgrid")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

BASE_URL = "https://api.sendgrid.com/v3"

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
    """Get the SendGrid API key from environment variable."""
    env_var = profile.get("api_key_env", "SENDGRID_API_KEY")
    api_key = os.environ.get(env_var)
    if not api_key:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return api_key


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    api_key: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated SendGrid API call using Bearer token auth.

    Args:
        api_key: SendGrid API key
        endpoint: API endpoint (appended to base URL)
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        data: Request payload for POST/PUT/PATCH requests (JSON-encoded)
        timeout: Request timeout in seconds

    Returns:
        Response dict with 'ok' field and result/error
    """
    url = f"{BASE_URL}{endpoint}"

    headers = {
        "Authorization": f"Bearer {api_key}",
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
            # Some endpoints return empty body on success (e.g., 202 Accepted)
            return {"ok": True, "result": {"status": "success"}}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            # SendGrid returns errors in various formats
            if "errors" in error_data:
                error_messages = [err.get("message", str(err)) for err in error_data["errors"]]
                error_message = "; ".join(error_messages)
            else:
                error_message = error_data.get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("SendGrid API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in SendGrid API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Email Actions
# =============================================================================

def send_email(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a transactional email via SendGrid.

    Params:
        to (str or list): Recipient email(s) - single email or list of emails (required)
        from_email (str): Sender email address (required)
        from_name (str): Sender display name (optional)
        subject (str): Email subject line (required)
        content (str): Email body content (required)
        content_type (str): Content type - "text/plain" or "text/html" (default: "text/html")
        cc (str or list): CC recipient(s) (optional)
        bcc (str or list): BCC recipient(s) (optional)
        reply_to (str): Reply-to email address (optional)
        attachments (list): List of attachment dicts with keys:
            - content (str): Base64-encoded file content
            - filename (str): Attachment filename
            - type (str): MIME type (optional)
            - disposition (str): "attachment" or "inline" (optional)

    Returns:
        ok (bool): Success status
        result (dict): Response with message ID on success
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    to = params.get("to")
    from_email = params.get("from_email")
    subject = params.get("subject")
    content = params.get("content")

    if not to:
        return {"ok": False, "error": "to is required"}
    if not from_email:
        return {"ok": False, "error": "from_email is required"}
    if not subject:
        return {"ok": False, "error": "subject is required"}
    if not content:
        return {"ok": False, "error": "content is required"}

    # Build recipient list
    def _build_email_list(emails):
        if isinstance(emails, str):
            return [{"email": emails}]
        elif isinstance(emails, list):
            return [{"email": e} if isinstance(e, str) else e for e in emails]
        return []

    personalizations = [{
        "to": _build_email_list(to)
    }]

    if params.get("cc"):
        personalizations[0]["cc"] = _build_email_list(params["cc"])
    if params.get("bcc"):
        personalizations[0]["bcc"] = _build_email_list(params["bcc"])

    # Build from field
    from_field = {"email": from_email}
    if params.get("from_name"):
        from_field["name"] = params["from_name"]

    # Build content
    content_type = params.get("content_type", "text/html")
    contents = [{"type": content_type, "value": content}]

    email_data: Dict[str, Any] = {
        "personalizations": personalizations,
        "from": from_field,
        "subject": subject,
        "content": contents,
    }

    if params.get("reply_to"):
        email_data["reply_to"] = {"email": params["reply_to"]}

    # Handle attachments
    if params.get("attachments"):
        attachments_list = []
        for attachment in params["attachments"]:
            att = {
                "content": attachment.get("content"),
                "filename": attachment.get("filename"),
            }
            if attachment.get("type"):
                att["type"] = attachment["type"]
            if attachment.get("disposition"):
                att["disposition"] = attachment["disposition"]
            attachments_list.append(att)
        email_data["attachments"] = attachments_list

    result = _api_call(api_key, "/mail/send", method="POST", data=email_data)

    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "status": "accepted",
                "message": "Email has been queued for delivery",
            }
        }
    return result


def send_template(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send an email using a dynamic template.

    Params:
        to (str or list): Recipient email(s) - single email or list of emails (required)
        from_email (str): Sender email address (required)
        from_name (str): Sender display name (optional)
        template_id (str): SendGrid dynamic template ID (required)
        dynamic_data (dict): Template variables/substitutions (optional)
        cc (str or list): CC recipient(s) (optional)
        bcc (str or list): BCC recipient(s) (optional)
        reply_to (str): Reply-to email address (optional)

    Returns:
        ok (bool): Success status
        result (dict): Response with message ID on success
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    to = params.get("to")
    from_email = params.get("from_email")
    template_id = params.get("template_id")

    if not to:
        return {"ok": False, "error": "to is required"}
    if not from_email:
        return {"ok": False, "error": "from_email is required"}
    if not template_id:
        return {"ok": False, "error": "template_id is required"}

    # Build recipient list
    def _build_email_list(emails):
        if isinstance(emails, str):
            return [{"email": emails}]
        elif isinstance(emails, list):
            return [{"email": e} if isinstance(e, str) else e for e in emails]
        return []

    personalizations = [{
        "to": _build_email_list(to)
    }]

    if params.get("cc"):
        personalizations[0]["cc"] = _build_email_list(params["cc"])
    if params.get("bcc"):
        personalizations[0]["bcc"] = _build_email_list(params["bcc"])
    if params.get("dynamic_data"):
        personalizations[0]["dynamic_template_data"] = params["dynamic_data"]

    # Build from field
    from_field = {"email": from_email}
    if params.get("from_name"):
        from_field["name"] = params["from_name"]

    email_data: Dict[str, Any] = {
        "personalizations": personalizations,
        "from": from_field,
        "template_id": template_id,
    }

    if params.get("reply_to"):
        email_data["reply_to"] = {"email": params["reply_to"]}

    result = _api_call(api_key, "/mail/send", method="POST", data=email_data)

    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "status": "accepted",
                "message": "Template email has been queued for delivery",
            }
        }
    return result


# =============================================================================
# Contact Actions
# =============================================================================

def add_contact(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add or update a contact in SendGrid Marketing.

    Params:
        email (str): Contact email address (required)
        first_name (str): Contact first name (optional)
        last_name (str): Contact last name (optional)
        list_ids (list): List IDs to add the contact to (optional)
        custom_fields (dict): Custom field values (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response with job_id for async processing
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    email = params.get("email")
    if not email:
        return {"ok": False, "error": "email is required"}

    contact = {"email": email}

    if params.get("first_name"):
        contact["first_name"] = params["first_name"]
    if params.get("last_name"):
        contact["last_name"] = params["last_name"]
    if params.get("custom_fields"):
        contact["custom_fields"] = params["custom_fields"]

    contact_data: Dict[str, Any] = {
        "contacts": [contact]
    }

    if params.get("list_ids"):
        contact_data["list_ids"] = params["list_ids"]

    result = _api_call(api_key, "/marketing/contacts", method="PUT", data=contact_data)

    if result.get("ok") and "result" in result:
        response = result["result"]
        return {
            "ok": True,
            "data": {
                "job_id": response.get("job_id"),
                "message": "Contact add/update job queued",
            }
        }
    return result


def list_contacts(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List contacts from SendGrid Marketing.

    Params:
        page_size (int): Number of contacts per page (default: 50, max: 1000)
        page_token (str): Pagination token for next page (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response with contacts array and pagination info
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    query_params = {}
    page_size = min(params.get("page_size", 50), 1000)
    query_params["page_size"] = page_size

    if params.get("page_token"):
        query_params["page_token"] = params["page_token"]

    endpoint = "/marketing/contacts"
    if query_params:
        endpoint = f"/marketing/contacts?{urlencode(query_params)}"

    result = _api_call(api_key, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        response = result["result"]
        contacts = []
        for contact in response.get("result", []):
            contacts.append({
                "id": contact.get("id"),
                "email": contact.get("email"),
                "first_name": contact.get("first_name"),
                "last_name": contact.get("last_name"),
                "created_at": contact.get("created_at"),
                "updated_at": contact.get("updated_at"),
                "list_ids": contact.get("list_ids", []),
                "custom_fields": contact.get("custom_fields", {}),
            })

        return {
            "ok": True,
            "data": {
                "contacts": contacts,
                "contact_count": response.get("contact_count", len(contacts)),
                "_metadata": response.get("_metadata", {}),
            }
        }
    return result


def create_list(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a contact list in SendGrid Marketing.

    Params:
        name (str): Name of the list (required)

    Returns:
        ok (bool): Success status
        data (dict): Response with list ID and details
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    name = params.get("name")
    if not name:
        return {"ok": False, "error": "name is required"}

    list_data = {"name": name}

    result = _api_call(api_key, "/marketing/lists", method="POST", data=list_data)

    if result.get("ok") and "result" in result:
        response = result["result"]
        return {
            "ok": True,
            "data": {
                "id": response.get("id"),
                "name": response.get("name"),
                "contact_count": response.get("contact_count", 0),
            }
        }
    return result


# =============================================================================
# Stats Actions
# =============================================================================

def get_stats(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get email statistics from SendGrid.

    Params:
        start_date (str): Start date in YYYY-MM-DD format (required)
        end_date (str): End date in YYYY-MM-DD format (optional, defaults to today)
        aggregated_by (str): Aggregation period - "day", "week", "month" (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response with stats including opens, clicks, bounces, etc.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    start_date = params.get("start_date")
    if not start_date:
        return {"ok": False, "error": "start_date is required"}

    query_params = {"start_date": start_date}

    if params.get("end_date"):
        query_params["end_date"] = params["end_date"]
    if params.get("aggregated_by"):
        query_params["aggregated_by"] = params["aggregated_by"]

    endpoint = f"/stats?{urlencode(query_params)}"
    result = _api_call(api_key, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        stats_data = result["result"]
        stats_list = []
        for stat in stats_data:
            stats_list.append({
                "date": stat.get("date"),
                "stats": stat.get("stats", []),
            })

        return {
            "ok": True,
            "data": {
                "stats": stats_list,
            }
        }
    return result


# =============================================================================
# Validation Actions
# =============================================================================

def validate_email(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate an email address using SendGrid Email Validation API.

    Params:
        email (str): Email address to validate (required)
        source (str): Source identifier for tracking (optional)

    Returns:
        ok (bool): Success status
        data (dict): Validation results including verdict, score, checks

    Note: Email Validation requires a separate SendGrid add-on subscription.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    email = params.get("email")
    if not email:
        return {"ok": False, "error": "email is required"}

    validation_data: Dict[str, Any] = {"email": email}

    if params.get("source"):
        validation_data["source"] = params["source"]

    result = _api_call(api_key, "/validations/email", method="POST", data=validation_data)

    if result.get("ok") and "result" in result:
        response = result["result"]
        validation_result = response.get("result", {})
        return {
            "ok": True,
            "data": {
                "email": validation_result.get("email"),
                "verdict": validation_result.get("verdict"),
                "score": validation_result.get("score"),
                "local": validation_result.get("local"),
                "host": validation_result.get("host"),
                "checks": validation_result.get("checks", {}),
                "ip_address": validation_result.get("ip_address"),
            }
        }
    return result


# =============================================================================
# Template Actions
# =============================================================================

def list_templates(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List email templates from SendGrid.

    Params:
        generations (str): Template generation - "legacy" or "dynamic" (default: "dynamic")
        page_size (int): Number of templates per page (default: 50, max: 200)

    Returns:
        ok (bool): Success status
        data (dict): Response with templates array
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    query_params = {}

    generations = params.get("generations", "dynamic")
    query_params["generations"] = generations

    page_size = min(params.get("page_size", 50), 200)
    query_params["page_size"] = page_size

    endpoint = f"/templates?{urlencode(query_params)}"
    result = _api_call(api_key, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        response = result["result"]
        templates = []
        for template in response.get("templates", []):
            templates.append({
                "id": template.get("id"),
                "name": template.get("name"),
                "generation": template.get("generation"),
                "updated_at": template.get("updated_at"),
                "versions": template.get("versions", []),
            })

        return {
            "ok": True,
            "data": {
                "templates": templates,
                "_metadata": response.get("_metadata", {}),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "send_email": send_email,
    "send_template": send_template,
    "add_contact": add_contact,
    "list_contacts": list_contacts,
    "create_list": create_list,
    "get_stats": get_stats,
    "validate_email": validate_email,
    "list_templates": list_templates,
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
        logger.info(f"Executing sendgrid.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
