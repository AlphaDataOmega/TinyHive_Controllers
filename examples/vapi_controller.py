"""
VAPI Controller for TinyHive

A controller for VAPI.ai - the Voice AI platform for building voice agents.
Supports creating assistants, managing calls, and uploading knowledge base files.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "api_key_env": "VAPI_API_KEY",
    "default_model": "gpt-4",
    "default_voice": "jennifer-playht"
}

Method IDs:
  controller.vapi.{profile}.create_assistant
  controller.vapi.{profile}.list_assistants
  controller.vapi.{profile}.get_assistant
  controller.vapi.{profile}.update_assistant
  controller.vapi.{profile}.create_call
  controller.vapi.{profile}.list_calls
  controller.vapi.{profile}.get_call
  controller.vapi.{profile}.upload_file

Dependencies:
------------
None (standard library only)
"""

import base64
import json
import logging
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.vapi")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# VAPI API configuration
VAPI_API_BASE = "https://api.vapi.ai"
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
    """Get the VAPI API key from environment variable."""
    env_var = profile.get("api_key_env", "VAPI_API_KEY")
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
    data: Optional[bytes] = None,
    content_type: str = "application/json",
    timeout: int = DEFAULT_TIMEOUT,
    extra_headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Make an authenticated VAPI API call."""
    url = f"{VAPI_API_BASE}/{endpoint.lstrip('/')}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": content_type,
    }
    if extra_headers:
        headers.update(extra_headers)

    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "data": json.loads(response_body)}
            return {"ok": True, "data": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_data.get("error", error_body[:500]))
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("VAPI API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in VAPI API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Assistant Actions
# =============================================================================

def create_assistant(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new voice AI assistant.

    Params:
        name (str): Assistant name (required)
        first_message (str): Initial greeting message (optional)
        system_prompt (str): System prompt/instructions (optional)
        model (str): LLM model to use (default: from profile or gpt-4)
        voice (str): Voice ID to use (default: from profile or jennifer-playht)

    Returns:
        {"ok": True, "data": {"id": "...", "name": "...", ...}}
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    name = params.get("name")
    if not name:
        return {"ok": False, "error": "name is required"}

    # Build assistant configuration
    assistant_config: Dict[str, Any] = {
        "name": name,
    }

    # First message configuration
    first_message = params.get("first_message")
    if first_message:
        assistant_config["firstMessage"] = first_message

    # System prompt / instructions
    system_prompt = params.get("system_prompt")
    if system_prompt:
        assistant_config["instructions"] = system_prompt

    # Model configuration
    model = params.get("model", profile.get("default_model", "gpt-4"))
    assistant_config["model"] = {
        "provider": "openai",
        "model": model,
    }

    # Voice configuration
    voice = params.get("voice", profile.get("default_voice", "jennifer-playht"))
    assistant_config["voice"] = {
        "provider": "playht",
        "voiceId": voice,
    }

    data = json.dumps(assistant_config).encode("utf-8")
    return _api_call(api_key, "/assistant", method="POST", data=data)


def list_assistants(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all assistants.

    Params:
        limit (int): Maximum number of assistants to return (optional)

    Returns:
        {"ok": True, "data": [{"id": "...", "name": "...", ...}, ...]}
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    query_params = {}
    if params.get("limit"):
        query_params["limit"] = params["limit"]

    endpoint = "/assistant"
    if query_params:
        endpoint += f"?{urlencode(query_params)}"

    return _api_call(api_key, endpoint, method="GET")


def get_assistant(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get assistant details.

    Params:
        assistant_id (str): Assistant ID (required)

    Returns:
        {"ok": True, "data": {"id": "...", "name": "...", ...}}
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    assistant_id = params.get("assistant_id")
    if not assistant_id:
        return {"ok": False, "error": "assistant_id is required"}

    return _api_call(api_key, f"/assistant/{assistant_id}", method="GET")


def update_assistant(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update assistant configuration.

    Params:
        assistant_id (str): Assistant ID (required)
        fields (dict): Fields to update (required)
            - name (str): Assistant name
            - first_message (str): Initial greeting message
            - system_prompt (str): System prompt/instructions
            - model (str): LLM model to use
            - voice (str): Voice ID to use

    Returns:
        {"ok": True, "data": {"id": "...", "name": "...", ...}}
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    assistant_id = params.get("assistant_id")
    if not assistant_id:
        return {"ok": False, "error": "assistant_id is required"}

    fields = params.get("fields", {})
    if not fields:
        return {"ok": False, "error": "fields is required"}

    # Build update payload with VAPI field names
    update_data: Dict[str, Any] = {}

    if "name" in fields:
        update_data["name"] = fields["name"]
    if "first_message" in fields:
        update_data["firstMessage"] = fields["first_message"]
    if "system_prompt" in fields:
        update_data["instructions"] = fields["system_prompt"]
    if "model" in fields:
        update_data["model"] = {
            "provider": "openai",
            "model": fields["model"],
        }
    if "voice" in fields:
        update_data["voice"] = {
            "provider": "playht",
            "voiceId": fields["voice"],
        }

    data = json.dumps(update_data).encode("utf-8")
    return _api_call(api_key, f"/assistant/{assistant_id}", method="PATCH", data=data)


# =============================================================================
# Call Actions
# =============================================================================

def create_call(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Initiate an outbound call.

    Params:
        assistant_id (str): Assistant ID to use for the call (required)
        phone_number_id (str): VAPI phone number ID to call from (required)
        customer_number (str): Customer phone number to call (required, E.164 format)

    Returns:
        {"ok": True, "data": {"id": "...", "status": "...", ...}}
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    assistant_id = params.get("assistant_id")
    phone_number_id = params.get("phone_number_id")
    customer_number = params.get("customer_number")

    if not assistant_id:
        return {"ok": False, "error": "assistant_id is required"}
    if not phone_number_id:
        return {"ok": False, "error": "phone_number_id is required"}
    if not customer_number:
        return {"ok": False, "error": "customer_number is required"}

    call_config = {
        "assistantId": assistant_id,
        "phoneNumberId": phone_number_id,
        "customer": {
            "number": customer_number,
        },
    }

    data = json.dumps(call_config).encode("utf-8")
    return _api_call(api_key, "/call/phone", method="POST", data=data)


def list_calls(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List calls with optional filters.

    Params:
        assistant_id (str): Filter by assistant ID (optional)
        limit (int): Maximum number of calls to return (optional)

    Returns:
        {"ok": True, "data": [{"id": "...", "status": "...", ...}, ...]}
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    query_params = {}
    if params.get("assistant_id"):
        query_params["assistantId"] = params["assistant_id"]
    if params.get("limit"):
        query_params["limit"] = params["limit"]

    endpoint = "/call"
    if query_params:
        endpoint += f"?{urlencode(query_params)}"

    return _api_call(api_key, endpoint, method="GET")


def get_call(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get call details including transcript.

    Params:
        call_id (str): Call ID (required)

    Returns:
        {"ok": True, "data": {"id": "...", "status": "...", "transcript": "...", ...}}
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    call_id = params.get("call_id")
    if not call_id:
        return {"ok": False, "error": "call_id is required"}

    return _api_call(api_key, f"/call/{call_id}", method="GET")


# =============================================================================
# File Actions
# =============================================================================

def upload_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upload a file for knowledge base.

    Params:
        file_path (str): Path to the local file to upload (required)

    Returns:
        {"ok": True, "data": {"id": "...", "name": "...", ...}}
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    file_path = params.get("file_path")
    if not file_path:
        return {"ok": False, "error": "file_path is required"}

    path = Path(file_path).expanduser()
    if not path.exists():
        return {"ok": False, "error": f"File not found: {file_path}"}

    # Read file content
    file_content = path.read_bytes()
    file_name = path.name

    # Determine content type
    content_type, _ = mimetypes.guess_type(file_name)
    if not content_type:
        content_type = "application/octet-stream"

    # Build multipart/form-data request
    boundary = f"----TinyHiveBoundary{uuid.uuid4().hex}"

    body_parts = []
    body_parts.append(f"--{boundary}".encode())
    body_parts.append(f'Content-Disposition: form-data; name="file"; filename="{file_name}"'.encode())
    body_parts.append(f"Content-Type: {content_type}".encode())
    body_parts.append(b"")
    body_parts.append(file_content)
    body_parts.append(f"--{boundary}--".encode())

    body = b"\r\n".join(body_parts)

    return _api_call(
        api_key,
        "/file",
        method="POST",
        data=body,
        content_type=f"multipart/form-data; boundary={boundary}"
    )


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "create_assistant": create_assistant,
    "list_assistants": list_assistants,
    "get_assistant": get_assistant,
    "update_assistant": update_assistant,
    "create_call": create_call,
    "list_calls": list_calls,
    "get_call": get_call,
    "upload_file": upload_file,
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
        logger.info(f"Executing vapi.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
