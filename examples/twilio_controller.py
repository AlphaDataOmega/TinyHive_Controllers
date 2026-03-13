"""
Twilio Controller for TinyHive

A controller for integrating with Twilio REST API for SMS, WhatsApp, Voice, and Lookup.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Twilio profile:
{
    "account_sid_env": "TWILIO_ACCOUNT_SID",
    "auth_token_env": "TWILIO_AUTH_TOKEN",
    "default_from": "+15551234567"
}

Environment Variables:
---------------------
- TWILIO_ACCOUNT_SID: Twilio Account SID
- TWILIO_AUTH_TOKEN: Twilio Auth Token

Dependencies:
------------
- None (standard library only)

Method IDs:
  controller.twilio.{profile}.send_sms
  controller.twilio.{profile}.send_whatsapp
  controller.twilio.{profile}.make_call
  controller.twilio.{profile}.list_messages
  controller.twilio.{profile}.get_message
  controller.twilio.{profile}.lookup_phone
  controller.twilio.{profile}.list_calls
  controller.twilio.{profile}.get_recordings
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.twilio")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Twilio API base URL template
TWILIO_API_BASE = "https://api.twilio.com/2010-04-01/Accounts"

# Twilio Lookup API base URL
TWILIO_LOOKUP_BASE = "https://lookups.twilio.com/v1/PhoneNumbers"

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


def _get_credentials(profile: Dict[str, Any]) -> tuple:
    """Get the Twilio Account SID and Auth Token from environment variables.

    Returns:
        tuple: (account_sid, auth_token)
    """
    account_sid_env = profile.get("account_sid_env", "TWILIO_ACCOUNT_SID")
    auth_token_env = profile.get("auth_token_env", "TWILIO_AUTH_TOKEN")

    account_sid = os.environ.get(account_sid_env)
    if not account_sid:
        raise ValueError(
            f"Environment variable '{account_sid_env}' not set. "
            "Set your Twilio Account SID in this environment variable."
        )

    auth_token = os.environ.get(auth_token_env)
    if not auth_token:
        raise ValueError(
            f"Environment variable '{auth_token_env}' not set. "
            "Set your Twilio Auth Token in this environment variable."
        )

    return account_sid, auth_token


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    account_sid: str,
    auth_token: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    base_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Make an authenticated Twilio API call using Basic Auth.

    Args:
        account_sid: Twilio Account SID
        auth_token: Twilio Auth Token
        endpoint: API endpoint (appended to base URL)
        method: HTTP method (GET, POST, DELETE)
        data: Request payload for POST requests (form-encoded)
        timeout: Request timeout in seconds
        base_url: Override base URL (for Lookup API)

    Returns:
        Response dict with 'ok' field and result/error
    """
    if base_url:
        url = f"{base_url}/{endpoint}"
    else:
        url = f"{TWILIO_API_BASE}/{account_sid}/{endpoint}"

    # Basic Auth: account_sid:auth_token
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {credentials}",
        "Accept": "application/json",
    }

    body = None
    if data is not None and method == "POST":
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        # Filter out None values and encode
        filtered_data = {k: v for k, v in data.items() if v is not None}
        body = urlencode(filtered_data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            result = json.loads(response_body)
            return {"ok": True, "data": result}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("message", error_body[:500])
            error_code = error_json.get("code", e.code)
            logger.error("Twilio API error %s: %s", error_code, error_msg)
            return {"ok": False, "error": f"Twilio error {error_code}: {error_msg}"}
        except json.JSONDecodeError:
            logger.error("Twilio HTTP error %d: %s", e.code, error_body[:500])
            return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Twilio API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def send_sms(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send an SMS message via Twilio.

    Params:
        to (str): Destination phone number in E.164 format (e.g., '+15551234567') (required)
        from_ (str): Sender phone number in E.164 format (optional, uses profile default)
        body (str): Message body text (required, max 1600 characters)
        status_callback (str): URL for status callback webhooks (optional)
        messaging_service_sid (str): Messaging Service SID to use (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response including sid, status, date_created, etc.
    """
    try:
        profile = load_profile(profile_name)
        account_sid, auth_token = _get_credentials(profile)

        to = params.get("to")
        from_ = params.get("from_") or params.get("from") or profile.get("default_from")
        body = params.get("body")

        if not to:
            return {"ok": False, "error": "to is required"}
        if not body:
            return {"ok": False, "error": "body is required"}
        if not from_ and not params.get("messaging_service_sid"):
            return {"ok": False, "error": "from_ or messaging_service_sid is required"}

        data = {
            "To": to,
            "Body": body,
        }

        if from_:
            data["From"] = from_
        if params.get("messaging_service_sid"):
            data["MessagingServiceSid"] = params["messaging_service_sid"]
        if params.get("status_callback"):
            data["StatusCallback"] = params["status_callback"]

        return _api_call(account_sid, auth_token, "Messages.json", method="POST", data=data)

    except Exception as e:
        logger.exception("send_sms failed")
        return {"ok": False, "error": str(e)}


def send_whatsapp(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a WhatsApp message via Twilio.

    Params:
        to (str): Destination WhatsApp number in E.164 format (e.g., '+15551234567') (required)
        from_ (str): Sender WhatsApp number (optional, uses profile default)
        body (str): Message body text (required)
        media_url (str): URL of media to include (optional)
        content_sid (str): Content template SID for pre-approved templates (optional)
        content_variables (str): JSON string of template variables (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response including sid, status, date_created, etc.

    Note: WhatsApp numbers must be prefixed with 'whatsapp:' - this is handled automatically.
    """
    try:
        profile = load_profile(profile_name)
        account_sid, auth_token = _get_credentials(profile)

        to = params.get("to")
        from_ = params.get("from_") or params.get("from") or profile.get("default_from")
        body = params.get("body")

        if not to:
            return {"ok": False, "error": "to is required"}
        if not body and not params.get("content_sid"):
            return {"ok": False, "error": "body or content_sid is required"}
        if not from_:
            return {"ok": False, "error": "from_ is required"}

        # Add whatsapp: prefix if not present
        if not to.startswith("whatsapp:"):
            to = f"whatsapp:{to}"
        if not from_.startswith("whatsapp:"):
            from_ = f"whatsapp:{from_}"

        data = {
            "To": to,
            "From": from_,
        }

        if body:
            data["Body"] = body
        if params.get("media_url"):
            data["MediaUrl"] = params["media_url"]
        if params.get("content_sid"):
            data["ContentSid"] = params["content_sid"]
        if params.get("content_variables"):
            data["ContentVariables"] = params["content_variables"]

        return _api_call(account_sid, auth_token, "Messages.json", method="POST", data=data)

    except Exception as e:
        logger.exception("send_whatsapp failed")
        return {"ok": False, "error": str(e)}


def make_call(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Initiate a voice call via Twilio.

    Params:
        to (str): Destination phone number in E.164 format (required)
        from_ (str): Caller ID phone number (optional, uses profile default)
        url (str): URL returning TwiML instructions for the call (optional)
        twiml (str): TwiML instructions inline (optional, use url OR twiml)
        status_callback (str): URL for call status webhooks (optional)
        status_callback_event (list): Events to receive callbacks for (optional)
        timeout (int): Seconds to wait for answer (default: 60)
        record (bool): Whether to record the call (default: false)
        machine_detection (str): Enable answering machine detection: 'Enable' or 'DetectMessageEnd' (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response including sid, status, direction, etc.

    Note: Either url or twiml must be provided.
    """
    try:
        profile = load_profile(profile_name)
        account_sid, auth_token = _get_credentials(profile)

        to = params.get("to")
        from_ = params.get("from_") or params.get("from") or profile.get("default_from")
        url = params.get("url")
        twiml = params.get("twiml")

        if not to:
            return {"ok": False, "error": "to is required"}
        if not from_:
            return {"ok": False, "error": "from_ is required"}
        if not url and not twiml:
            return {"ok": False, "error": "url or twiml is required"}

        data = {
            "To": to,
            "From": from_,
        }

        if url:
            data["Url"] = url
        if twiml:
            data["Twiml"] = twiml
        if params.get("status_callback"):
            data["StatusCallback"] = params["status_callback"]
        if params.get("status_callback_event"):
            # Can be provided as list or comma-separated string
            events = params["status_callback_event"]
            if isinstance(events, list):
                for event in events:
                    data[f"StatusCallbackEvent"] = event
            else:
                data["StatusCallbackEvent"] = events
        if params.get("timeout"):
            data["Timeout"] = str(params["timeout"])
        if params.get("record"):
            data["Record"] = "true" if params["record"] else "false"
        if params.get("machine_detection"):
            data["MachineDetection"] = params["machine_detection"]

        return _api_call(account_sid, auth_token, "Calls.json", method="POST", data=data)

    except Exception as e:
        logger.exception("make_call failed")
        return {"ok": False, "error": str(e)}


def list_messages(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List messages from the account.

    Params:
        to (str): Filter by destination number (optional)
        from_ (str): Filter by sender number (optional)
        date_sent (str): Filter by date sent (YYYY-MM-DD) (optional)
        date_sent_after (str): Filter messages sent after date (YYYY-MM-DD) (optional)
        date_sent_before (str): Filter messages sent before date (YYYY-MM-DD) (optional)
        limit (int): Maximum messages to return (default: 50, max: 1000)
        page_size (int): Number of messages per page (default: 50)

    Returns:
        ok (bool): Success status
        data (dict): Response including messages array and pagination info
    """
    try:
        profile = load_profile(profile_name)
        account_sid, auth_token = _get_credentials(profile)

        query_params = {}

        if params.get("to"):
            query_params["To"] = params["to"]
        if params.get("from_") or params.get("from"):
            query_params["From"] = params.get("from_") or params.get("from")
        if params.get("date_sent"):
            query_params["DateSent"] = params["date_sent"]
        if params.get("date_sent_after"):
            query_params["DateSent>"] = params["date_sent_after"]
        if params.get("date_sent_before"):
            query_params["DateSent<"] = params["date_sent_before"]

        page_size = min(params.get("page_size", 50), 1000)
        query_params["PageSize"] = str(page_size)

        endpoint = "Messages.json"
        if query_params:
            endpoint = f"Messages.json?{urlencode(query_params)}"

        return _api_call(account_sid, auth_token, endpoint)

    except Exception as e:
        logger.exception("list_messages failed")
        return {"ok": False, "error": str(e)}


def get_message(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific message.

    Params:
        message_sid (str): The Message SID (starts with 'SM' or 'MM') (required)

    Returns:
        ok (bool): Success status
        data (dict): Message details including sid, body, status, date_sent, etc.
    """
    try:
        profile = load_profile(profile_name)
        account_sid, auth_token = _get_credentials(profile)

        message_sid = params.get("message_sid")
        if not message_sid:
            return {"ok": False, "error": "message_sid is required"}

        endpoint = f"Messages/{message_sid}.json"
        return _api_call(account_sid, auth_token, endpoint)

    except Exception as e:
        logger.exception("get_message failed")
        return {"ok": False, "error": str(e)}


def lookup_phone(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Look up information about a phone number using Twilio Lookup API.

    Params:
        phone_number (str): Phone number to look up in E.164 format (required)
        type (str): Type of information to retrieve: 'carrier', 'caller-name' (optional)
        country_code (str): ISO country code for national format numbers (optional)
        fields (str): Comma-separated fields for Lookup v2: 'line_type_intelligence',
                      'caller_name', 'sim_swap', 'call_forwarding', 'live_activity' (optional)

    Returns:
        ok (bool): Success status
        data (dict): Phone number information including country, carrier info, etc.

    Note: Carrier and caller-name lookups incur additional charges.
    """
    try:
        profile = load_profile(profile_name)
        account_sid, auth_token = _get_credentials(profile)

        phone_number = params.get("phone_number")
        if not phone_number:
            return {"ok": False, "error": "phone_number is required"}

        # Build query parameters
        query_params = {}

        lookup_type = params.get("type")
        if lookup_type:
            query_params["Type"] = lookup_type
        if params.get("country_code"):
            query_params["CountryCode"] = params["country_code"]
        if params.get("fields"):
            query_params["Fields"] = params["fields"]

        # URL encode the phone number for the path
        from urllib.parse import quote
        encoded_number = quote(phone_number, safe='')

        endpoint = encoded_number
        if query_params:
            endpoint = f"{encoded_number}?{urlencode(query_params)}"

        return _api_call(
            account_sid,
            auth_token,
            endpoint,
            base_url=TWILIO_LOOKUP_BASE
        )

    except Exception as e:
        logger.exception("lookup_phone failed")
        return {"ok": False, "error": str(e)}


def list_calls(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List calls from the account.

    Params:
        to (str): Filter by destination number (optional)
        from_ (str): Filter by caller number (optional)
        status (str): Filter by status: 'queued', 'ringing', 'in-progress',
                      'completed', 'busy', 'failed', 'no-answer', 'canceled' (optional)
        start_time (str): Filter by start time (YYYY-MM-DD) (optional)
        start_time_after (str): Filter calls started after date (YYYY-MM-DD) (optional)
        start_time_before (str): Filter calls started before date (YYYY-MM-DD) (optional)
        end_time (str): Filter by end time (YYYY-MM-DD) (optional)
        limit (int): Maximum calls to return (default: 50, max: 1000)
        page_size (int): Number of calls per page (default: 50)

    Returns:
        ok (bool): Success status
        data (dict): Response including calls array and pagination info
    """
    try:
        profile = load_profile(profile_name)
        account_sid, auth_token = _get_credentials(profile)

        query_params = {}

        if params.get("to"):
            query_params["To"] = params["to"]
        if params.get("from_") or params.get("from"):
            query_params["From"] = params.get("from_") or params.get("from")
        if params.get("status"):
            query_params["Status"] = params["status"]
        if params.get("start_time"):
            query_params["StartTime"] = params["start_time"]
        if params.get("start_time_after"):
            query_params["StartTime>"] = params["start_time_after"]
        if params.get("start_time_before"):
            query_params["StartTime<"] = params["start_time_before"]
        if params.get("end_time"):
            query_params["EndTime"] = params["end_time"]

        page_size = min(params.get("page_size", 50), 1000)
        query_params["PageSize"] = str(page_size)

        endpoint = "Calls.json"
        if query_params:
            endpoint = f"Calls.json?{urlencode(query_params)}"

        return _api_call(account_sid, auth_token, endpoint)

    except Exception as e:
        logger.exception("list_calls failed")
        return {"ok": False, "error": str(e)}


def get_recordings(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get recordings for a specific call.

    Params:
        call_sid (str): The Call SID (starts with 'CA') (required)
        date_created (str): Filter by date created (YYYY-MM-DD) (optional)
        date_created_after (str): Filter recordings created after date (optional)
        date_created_before (str): Filter recordings created before date (optional)
        page_size (int): Number of recordings per page (default: 50)

    Returns:
        ok (bool): Success status
        data (dict): Response including recordings array with sid, duration, etc.
    """
    try:
        profile = load_profile(profile_name)
        account_sid, auth_token = _get_credentials(profile)

        call_sid = params.get("call_sid")
        if not call_sid:
            return {"ok": False, "error": "call_sid is required"}

        query_params = {}

        if params.get("date_created"):
            query_params["DateCreated"] = params["date_created"]
        if params.get("date_created_after"):
            query_params["DateCreated>"] = params["date_created_after"]
        if params.get("date_created_before"):
            query_params["DateCreated<"] = params["date_created_before"]

        page_size = min(params.get("page_size", 50), 1000)
        query_params["PageSize"] = str(page_size)

        endpoint = f"Calls/{call_sid}/Recordings.json"
        if query_params:
            endpoint = f"Calls/{call_sid}/Recordings.json?{urlencode(query_params)}"

        return _api_call(account_sid, auth_token, endpoint)

    except Exception as e:
        logger.exception("get_recordings failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "send_sms": send_sms,
    "send_whatsapp": send_whatsapp,
    "make_call": make_call,
    "list_messages": list_messages,
    "get_message": get_message,
    "lookup_phone": lookup_phone,
    "list_calls": list_calls,
    "get_recordings": get_recordings,
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

    logger.info(f"Executing twilio.{profile}.{action}")
    return ACTIONS[action](profile, params)
