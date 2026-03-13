"""
Vonage Controller for TinyHive

A controller for Vonage Communications APIs supporting SMS, Voice, Verify, and Number Insight.

Method IDs:
    controller.vonage.{profile}.send_sms
    controller.vonage.{profile}.get_message
    controller.vonage.{profile}.create_call
    controller.vonage.{profile}.get_call
    controller.vonage.{profile}.send_verification
    controller.vonage.{profile}.check_verification
    controller.vonage.{profile}.lookup_number
    controller.vonage.{profile}.list_messages

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "api_key_env": "VONAGE_API_KEY",
    "api_secret_env": "VONAGE_API_SECRET",
    "application_id": "optional-app-id-for-voice",
    "private_key_path": "/path/to/private.key",
    "default_from": "+15551234567",
    "webhook_base_url": "https://example.com/webhooks"
}

Environment Variables:
---------------------
- VONAGE_API_KEY: Your Vonage API key
- VONAGE_API_SECRET: Your Vonage API secret

API Endpoints:
-------------
- SMS API: https://rest.nexmo.com/sms
- Messages API: https://api.nexmo.com/v1/messages
- Voice API: https://api.nexmo.com/v1/calls
- Verify API: https://api.nexmo.com/verify
- Number Insight API: https://api.nexmo.com/ni

Dependencies:
------------
- None (standard library only)
- For Voice API with JWT: requires private key file
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.vonage")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Vonage API endpoints
SMS_API_BASE = "https://rest.nexmo.com/sms"
MESSAGES_API_BASE = "https://api.nexmo.com/v1/messages"
VOICE_API_BASE = "https://api.nexmo.com/v1/calls"
VERIFY_API_BASE = "https://api.nexmo.com/verify"
NUMBER_INSIGHT_API_BASE = "https://api.nexmo.com/ni"

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
    """Get API key and secret from environment variables."""
    api_key_env = profile.get("api_key_env", "VONAGE_API_KEY")
    api_secret_env = profile.get("api_secret_env", "VONAGE_API_SECRET")

    api_key = os.environ.get(api_key_env)
    api_secret = os.environ.get(api_secret_env)

    if not api_key:
        raise ValueError(f"Missing environment variable: {api_key_env}")
    if not api_secret:
        raise ValueError(f"Missing environment variable: {api_secret_env}")

    return api_key, api_secret


# =============================================================================
# JWT Authentication (for Voice API)
# =============================================================================

def _base64url_encode(data: bytes) -> str:
    """Base64url encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _create_jwt(application_id: str, private_key_path: str) -> str:
    """Create a JWT for Vonage Voice API authentication."""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend
    except ImportError:
        raise ImportError(
            "cryptography library required for Voice API JWT auth. "
            "Install with: pip install cryptography"
        )

    # Load private key
    key_path = Path(private_key_path).expanduser()
    if not key_path.exists():
        raise ValueError(f"Private key file not found: {private_key_path}")

    private_key_pem = key_path.read_bytes()
    private_key = serialization.load_pem_private_key(
        private_key_pem,
        password=None,
        backend=default_backend()
    )

    now = int(time.time())

    header = {
        "alg": "RS256",
        "typ": "JWT"
    }

    claims = {
        "iat": now,
        "exp": now + 3600,
        "jti": f"{now}-{os.urandom(8).hex()}",
        "application_id": application_id
    }

    header_b64 = _base64url_encode(json.dumps(header).encode("utf-8"))
    claims_b64 = _base64url_encode(json.dumps(claims).encode("utf-8"))
    signing_input = f"{header_b64}.{claims_b64}".encode("utf-8")

    signature = private_key.sign(
        signing_input,
        padding.PKCS1v15(),
        hashes.SHA256()
    )

    signature_b64 = _base64url_encode(signature)
    return f"{header_b64}.{claims_b64}.{signature_b64}"


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an API call and return the result."""
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if headers:
        request_headers.update(headers)

    try:
        req = Request(url, data=data, headers=request_headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("title", error_data.get("error-text", error_body[:500]))
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Vonage API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Vonage API call")
        return {"ok": False, "error": str(e)}


def _api_call_basic_auth(
    url: str,
    api_key: str,
    api_secret: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an API call with Basic Auth."""
    auth_string = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode("ascii")
    headers = {
        "Authorization": f"Basic {auth_string}"
    }
    return _api_call(url, method=method, data=data, headers=headers, timeout=timeout)


def _api_call_jwt(
    url: str,
    jwt_token: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an API call with JWT Bearer auth."""
    headers = {
        "Authorization": f"Bearer {jwt_token}"
    }
    return _api_call(url, method=method, data=data, headers=headers, timeout=timeout)


# =============================================================================
# SMS Actions
# =============================================================================

def send_sms(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send an SMS message using the Vonage SMS API.

    Params:
        from (str): Sender ID or phone number (required, or uses profile default)
        to (str): Recipient phone number in E.164 format (required)
        text (str): Message text (required)
        type (str): Message type: 'text' or 'unicode' (default: 'text')
        ttl (int): Time-to-live in milliseconds (optional)
        callback (str): Webhook URL for delivery receipts (optional)
    """
    try:
        profile = load_profile(profile_name)
        api_key, api_secret = _get_credentials(profile)

        sender = params.get("from", profile.get("default_from"))
        recipient = params.get("to")
        text = params.get("text")

        if not sender:
            return {"ok": False, "error": "'from' is required (or set default_from in profile)"}
        if not recipient:
            return {"ok": False, "error": "'to' is required"}
        if not text:
            return {"ok": False, "error": "'text' is required"}

        # Build request payload
        payload = {
            "api_key": api_key,
            "api_secret": api_secret,
            "from": sender,
            "to": recipient,
            "text": text
        }

        if params.get("type"):
            payload["type"] = params["type"]
        if params.get("ttl"):
            payload["ttl"] = params["ttl"]
        if params.get("callback"):
            payload["callback"] = params["callback"]

        url = f"{SMS_API_BASE}/json"
        data = json.dumps(payload).encode("utf-8")

        result = _api_call(url, method="POST", data=data)

        if result.get("ok") and "result" in result:
            messages = result["result"].get("messages", [])
            if messages:
                first_msg = messages[0]
                status = first_msg.get("status", "")
                if status == "0":
                    return {
                        "ok": True,
                        "result": {
                            "message_id": first_msg.get("message-id"),
                            "to": first_msg.get("to"),
                            "remaining_balance": first_msg.get("remaining-balance"),
                            "message_price": first_msg.get("message-price"),
                            "network": first_msg.get("network")
                        }
                    }
                else:
                    return {
                        "ok": False,
                        "error": first_msg.get("error-text", f"SMS failed with status {status}")
                    }
            return {"ok": False, "error": "No messages in response"}
        return result

    except Exception as e:
        logger.exception("send_sms failed")
        return {"ok": False, "error": str(e)}


def get_message(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the status of a message using the Messages API.

    Params:
        message_id (str): The message UUID to look up (required)
    """
    try:
        profile = load_profile(profile_name)
        api_key, api_secret = _get_credentials(profile)

        message_id = params.get("message_id")
        if not message_id:
            return {"ok": False, "error": "'message_id' is required"}

        url = f"{MESSAGES_API_BASE}/{message_id}"

        result = _api_call_basic_auth(url, api_key, api_secret, method="GET")

        if result.get("ok") and "result" in result:
            msg = result["result"]
            return {
                "ok": True,
                "result": {
                    "message_uuid": msg.get("message_uuid"),
                    "status": msg.get("status"),
                    "to": msg.get("to"),
                    "from": msg.get("from"),
                    "timestamp": msg.get("timestamp"),
                    "channel": msg.get("channel"),
                    "usage": msg.get("usage")
                }
            }
        return result

    except Exception as e:
        logger.exception("get_message failed")
        return {"ok": False, "error": str(e)}


def list_messages(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List messages within a date range using the Messages API.

    Params:
        date_start (str): Start date in ISO 8601 format (required)
        date_end (str): End date in ISO 8601 format (required)
        status (str): Filter by status: 'submitted', 'delivered', 'rejected', etc. (optional)
        to (str): Filter by recipient number (optional)
        from (str): Filter by sender (optional)
        page_size (int): Number of results per page (default: 10, max: 100)
        order (str): Sort order: 'asc' or 'desc' (default: 'desc')
    """
    try:
        profile = load_profile(profile_name)
        api_key, api_secret = _get_credentials(profile)

        date_start = params.get("date_start")
        date_end = params.get("date_end")

        if not date_start:
            return {"ok": False, "error": "'date_start' is required"}
        if not date_end:
            return {"ok": False, "error": "'date_end' is required"}

        query_params = {
            "date_start": date_start,
            "date_end": date_end
        }

        if params.get("status"):
            query_params["status"] = params["status"]
        if params.get("to"):
            query_params["to"] = params["to"]
        if params.get("from"):
            query_params["from"] = params["from"]
        if params.get("page_size"):
            query_params["page_size"] = params["page_size"]
        if params.get("order"):
            query_params["order"] = params["order"]

        url = f"{MESSAGES_API_BASE}?{urlencode(query_params)}"

        result = _api_call_basic_auth(url, api_key, api_secret, method="GET")

        if result.get("ok") and "result" in result:
            data = result["result"]
            return {
                "ok": True,
                "result": {
                    "messages": data.get("items", []),
                    "count": len(data.get("items", [])),
                    "page_size": data.get("page_size"),
                    "total_items": data.get("total_items"),
                    "total_pages": data.get("total_pages")
                }
            }
        return result

    except Exception as e:
        logger.exception("list_messages failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Voice Actions
# =============================================================================

def create_call(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an outbound voice call using the Vonage Voice API.

    Requires application_id and private_key_path in profile for JWT auth.

    Params:
        to (str): Recipient phone number in E.164 format (required)
        from (str): Caller ID phone number (required, or uses profile default)
        answer_url (str): URL for call control NCCO (required if ncco not provided)
        ncco (list): NCCO actions array (required if answer_url not provided)
        event_url (str): Webhook URL for call events (optional)
        machine_detection (str): 'continue' or 'hangup' (optional)
        length_timer (int): Max call length in seconds (optional)
        ringing_timer (int): Max ring time in seconds (optional)
    """
    try:
        profile = load_profile(profile_name)

        # Voice API requires JWT auth
        application_id = profile.get("application_id")
        private_key_path = profile.get("private_key_path")

        if not application_id:
            return {"ok": False, "error": "'application_id' required in profile for Voice API"}
        if not private_key_path:
            return {"ok": False, "error": "'private_key_path' required in profile for Voice API"}

        jwt_token = _create_jwt(application_id, private_key_path)

        recipient = params.get("to")
        sender = params.get("from", profile.get("default_from"))
        answer_url = params.get("answer_url")
        ncco = params.get("ncco")

        if not recipient:
            return {"ok": False, "error": "'to' is required"}
        if not sender:
            return {"ok": False, "error": "'from' is required (or set default_from in profile)"}
        if not answer_url and not ncco:
            return {"ok": False, "error": "Either 'answer_url' or 'ncco' is required"}

        # Build request payload
        payload = {
            "to": [{"type": "phone", "number": recipient}],
            "from": {"type": "phone", "number": sender}
        }

        if ncco:
            payload["ncco"] = ncco
        else:
            payload["answer_url"] = [answer_url] if isinstance(answer_url, str) else answer_url

        if params.get("event_url"):
            event_url = params["event_url"]
            payload["event_url"] = [event_url] if isinstance(event_url, str) else event_url
        if params.get("machine_detection"):
            payload["machine_detection"] = params["machine_detection"]
        if params.get("length_timer"):
            payload["length_timer"] = params["length_timer"]
        if params.get("ringing_timer"):
            payload["ringing_timer"] = params["ringing_timer"]

        url = VOICE_API_BASE
        data = json.dumps(payload).encode("utf-8")

        result = _api_call_jwt(url, jwt_token, method="POST", data=data)

        if result.get("ok") and "result" in result:
            call = result["result"]
            return {
                "ok": True,
                "result": {
                    "uuid": call.get("uuid"),
                    "conversation_uuid": call.get("conversation_uuid"),
                    "status": call.get("status"),
                    "direction": call.get("direction")
                }
            }
        return result

    except Exception as e:
        logger.exception("create_call failed")
        return {"ok": False, "error": str(e)}


def get_call(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a voice call using the Vonage Voice API.

    Requires application_id and private_key_path in profile for JWT auth.

    Params:
        call_uuid (str): The call UUID to look up (required)
    """
    try:
        profile = load_profile(profile_name)

        application_id = profile.get("application_id")
        private_key_path = profile.get("private_key_path")

        if not application_id:
            return {"ok": False, "error": "'application_id' required in profile for Voice API"}
        if not private_key_path:
            return {"ok": False, "error": "'private_key_path' required in profile for Voice API"}

        jwt_token = _create_jwt(application_id, private_key_path)

        call_uuid = params.get("call_uuid")
        if not call_uuid:
            return {"ok": False, "error": "'call_uuid' is required"}

        url = f"{VOICE_API_BASE}/{call_uuid}"

        result = _api_call_jwt(url, jwt_token, method="GET")

        if result.get("ok") and "result" in result:
            call = result["result"]
            return {
                "ok": True,
                "result": {
                    "uuid": call.get("uuid"),
                    "conversation_uuid": call.get("conversation_uuid"),
                    "status": call.get("status"),
                    "direction": call.get("direction"),
                    "to": call.get("to"),
                    "from": call.get("from"),
                    "start_time": call.get("start_time"),
                    "end_time": call.get("end_time"),
                    "duration": call.get("duration"),
                    "rate": call.get("rate"),
                    "price": call.get("price"),
                    "network": call.get("network")
                }
            }
        return result

    except Exception as e:
        logger.exception("get_call failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Verify (2FA) Actions
# =============================================================================

def send_verification(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Start a verification (2FA) request using the Vonage Verify API.

    Params:
        number (str): Phone number to verify in E.164 format (required)
        brand (str): Brand name shown in SMS/voice (required)
        code_length (int): Verification code length: 4 or 6 (default: 4)
        pin_expiry (int): Code expiry time in seconds (default: 300)
        next_event_wait (int): Wait time before retry in seconds (default: 300)
        workflow_id (int): Workflow: 1=SMS->TTS->TTS, 2=SMS->SMS->TTS, etc. (default: 1)
        lg (str): Language code for message (default: 'en-us')
    """
    try:
        profile = load_profile(profile_name)
        api_key, api_secret = _get_credentials(profile)

        number = params.get("number")
        brand = params.get("brand")

        if not number:
            return {"ok": False, "error": "'number' is required"}
        if not brand:
            return {"ok": False, "error": "'brand' is required"}

        # Build request payload
        payload = {
            "api_key": api_key,
            "api_secret": api_secret,
            "number": number,
            "brand": brand
        }

        if params.get("code_length"):
            payload["code_length"] = params["code_length"]
        if params.get("pin_expiry"):
            payload["pin_expiry"] = params["pin_expiry"]
        if params.get("next_event_wait"):
            payload["next_event_wait"] = params["next_event_wait"]
        if params.get("workflow_id"):
            payload["workflow_id"] = params["workflow_id"]
        if params.get("lg"):
            payload["lg"] = params["lg"]

        url = f"{VERIFY_API_BASE}/json"
        data = json.dumps(payload).encode("utf-8")

        result = _api_call(url, method="POST", data=data)

        if result.get("ok") and "result" in result:
            resp = result["result"]
            status = resp.get("status", "")
            if status == "0":
                return {
                    "ok": True,
                    "result": {
                        "request_id": resp.get("request_id"),
                        "status": "sent"
                    }
                }
            else:
                return {
                    "ok": False,
                    "error": resp.get("error_text", f"Verify failed with status {status}")
                }
        return result

    except Exception as e:
        logger.exception("send_verification failed")
        return {"ok": False, "error": str(e)}


def check_verification(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check a verification code using the Vonage Verify API.

    Params:
        request_id (str): The verification request ID (required)
        code (str): The code entered by the user (required)
    """
    try:
        profile = load_profile(profile_name)
        api_key, api_secret = _get_credentials(profile)

        request_id = params.get("request_id")
        code = params.get("code")

        if not request_id:
            return {"ok": False, "error": "'request_id' is required"}
        if not code:
            return {"ok": False, "error": "'code' is required"}

        # Build request payload
        payload = {
            "api_key": api_key,
            "api_secret": api_secret,
            "request_id": request_id,
            "code": code
        }

        url = f"{VERIFY_API_BASE}/check/json"
        data = json.dumps(payload).encode("utf-8")

        result = _api_call(url, method="POST", data=data)

        if result.get("ok") and "result" in result:
            resp = result["result"]
            status = resp.get("status", "")
            if status == "0":
                return {
                    "ok": True,
                    "result": {
                        "request_id": resp.get("request_id"),
                        "event_id": resp.get("event_id"),
                        "price": resp.get("price"),
                        "currency": resp.get("currency"),
                        "verified": True
                    }
                }
            else:
                return {
                    "ok": False,
                    "error": resp.get("error_text", f"Verification failed with status {status}"),
                    "data": {
                        "request_id": request_id,
                        "verified": False
                    }
                }
        return result

    except Exception as e:
        logger.exception("check_verification failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Number Insight Actions
# =============================================================================

def lookup_number(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Look up information about a phone number using the Vonage Number Insight API.

    Params:
        number (str): Phone number to look up in E.164 format (required)
        type (str): Insight level: 'basic', 'standard', or 'advanced' (default: 'basic')
        country (str): ISO 3166-1 alpha-2 country code hint (optional)
        cnam (bool): Include CNAM lookup for US numbers (optional, advanced only)
    """
    try:
        profile = load_profile(profile_name)
        api_key, api_secret = _get_credentials(profile)

        number = params.get("number")
        insight_type = params.get("type", "basic")

        if not number:
            return {"ok": False, "error": "'number' is required"}

        if insight_type not in ("basic", "standard", "advanced"):
            return {"ok": False, "error": "'type' must be 'basic', 'standard', or 'advanced'"}

        # Build query params
        query_params = {
            "api_key": api_key,
            "api_secret": api_secret,
            "number": number
        }

        if params.get("country"):
            query_params["country"] = params["country"]
        if params.get("cnam") and insight_type == "advanced":
            query_params["cnam"] = "true"

        url = f"{NUMBER_INSIGHT_API_BASE}/{insight_type}/json?{urlencode(query_params)}"

        result = _api_call(url, method="GET")

        if result.get("ok") and "result" in result:
            resp = result["result"]
            status = resp.get("status", 0)
            if status == 0:
                # Build response based on insight level
                insight_result = {
                    "status": "success",
                    "status_message": resp.get("status_message"),
                    "request_id": resp.get("request_id"),
                    "international_format_number": resp.get("international_format_number"),
                    "national_format_number": resp.get("national_format_number"),
                    "country_code": resp.get("country_code"),
                    "country_code_iso3": resp.get("country_code_iso3"),
                    "country_name": resp.get("country_name"),
                    "country_prefix": resp.get("country_prefix")
                }

                # Standard and advanced include more fields
                if insight_type in ("standard", "advanced"):
                    insight_result.update({
                        "current_carrier": resp.get("current_carrier"),
                        "original_carrier": resp.get("original_carrier"),
                        "ported": resp.get("ported"),
                        "roaming": resp.get("roaming")
                    })

                # Advanced includes even more
                if insight_type == "advanced":
                    insight_result.update({
                        "lookup_outcome": resp.get("lookup_outcome"),
                        "lookup_outcome_message": resp.get("lookup_outcome_message"),
                        "valid_number": resp.get("valid_number"),
                        "reachable": resp.get("reachable"),
                        "caller_name": resp.get("caller_name"),
                        "caller_type": resp.get("caller_type"),
                        "first_name": resp.get("first_name"),
                        "last_name": resp.get("last_name")
                    })

                return {"ok": True, "result": insight_result}
            else:
                return {
                    "ok": False,
                    "error": resp.get("status_message", f"Lookup failed with status {status}")
                }
        return result

    except Exception as e:
        logger.exception("lookup_number failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "send_sms": send_sms,
    "get_message": get_message,
    "create_call": create_call,
    "get_call": get_call,
    "send_verification": send_verification,
    "check_verification": check_verification,
    "lookup_number": lookup_number,
    "list_messages": list_messages,
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

    logger.info(f"Executing vonage.{profile}.{action}")
    return ACTIONS[action](profile, params)
