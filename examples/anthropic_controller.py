"""
Anthropic Controller for TinyHive

A controller for integrating with Anthropic Claude API.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Anthropic profile:
{
    "api_key_env": "ANTHROPIC_API_KEY",
    "default_model": "claude-sonnet-4-20250514",
    "default_max_tokens": 1024
}

Features:
---------
- Message creation (chat completions)
- Streaming message support
- Token counting
- Tool use (function calling)
- Vision (image content blocks)
- System prompts

Dependencies:
------------
- None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger("tinyhive.controller.anthropic")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Anthropic API base URL
BASE_URL = "https://api.anthropic.com/v1"

# Required Anthropic API version header
ANTHROPIC_VERSION = "2023-06-01"

DEFAULT_TIMEOUT = 120


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
    """Get the Anthropic API key from environment variable."""
    env_var = profile.get("api_key_env", "ANTHROPIC_API_KEY")
    api_key = os.environ.get(env_var)
    if not api_key:
        raise ValueError(
            f"Environment variable '{env_var}' not set. "
            "Set your Anthropic API key in this environment variable."
        )
    return api_key


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    api_key: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    stream: bool = False
) -> Dict[str, Any]:
    """
    Make an authenticated Anthropic API call.

    Anthropic API uses:
    - x-api-key header for authentication
    - anthropic-version header for API versioning

    Args:
        api_key: Anthropic API key
        endpoint: API endpoint (e.g., 'messages')
        method: HTTP method
        data: Request payload
        timeout: Request timeout in seconds
        stream: Whether to enable streaming

    Returns:
        Response dict with 'ok' field and result/error
    """
    url = f"{BASE_URL}/{endpoint}"

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

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
            # Anthropic error format: {"type": "error", "error": {"type": "...", "message": "..."}}
            error_msg = error_json.get("error", {}).get("message", error_body[:500])
        except json.JSONDecodeError:
            error_msg = error_body[:500]
        logger.error("Anthropic HTTP error %d: %s", e.code, error_msg)
        return {"ok": False, "error": f"HTTP {e.code}: {error_msg}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Anthropic API call")
        return {"ok": False, "error": str(e)}


def _api_call_stream(
    api_key: str,
    endpoint: str,
    data: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT
) -> Generator[Dict[str, Any], None, None]:
    """
    Make a streaming Anthropic API call.

    Yields Server-Sent Events (SSE) as parsed dicts.

    Args:
        api_key: Anthropic API key
        endpoint: API endpoint
        data: Request payload (should include "stream": true)
        timeout: Request timeout in seconds

    Yields:
        Parsed SSE event dicts
    """
    url = f"{BASE_URL}/{endpoint}"

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }

    body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=timeout) as response:
            buffer = ""
            for chunk in iter(lambda: response.read(1024), b""):
                buffer += chunk.decode("utf-8")

                # Process complete SSE lines
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)

                    # Parse SSE format
                    event_type = None
                    event_data = None

                    for line in event_str.split("\n"):
                        if line.startswith("event: "):
                            event_type = line[7:]
                        elif line.startswith("data: "):
                            event_data = line[6:]

                    if event_data:
                        try:
                            parsed_data = json.loads(event_data)
                            yield {"event": event_type, "data": parsed_data}
                        except json.JSONDecodeError:
                            yield {"event": event_type, "data": event_data}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("error", {}).get("message", error_body[:500])
        except json.JSONDecodeError:
            error_msg = error_body[:500]
        yield {"error": f"HTTP {e.code}: {error_msg}"}
    except Exception as e:
        yield {"error": str(e)}


# =============================================================================
# Message Content Helpers
# =============================================================================

def _format_content_block(content: Any) -> Any:
    """
    Format a content block for the Anthropic API.

    Supports:
    - String content (converted to text block)
    - List of content blocks (text, image, tool_use, tool_result)
    - Image blocks with base64 or URL sources

    Args:
        content: String or list of content blocks

    Returns:
        Formatted content for API
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        formatted_blocks = []
        for block in content:
            if isinstance(block, str):
                formatted_blocks.append({"type": "text", "text": block})
            elif isinstance(block, dict):
                # Handle image blocks
                if block.get("type") == "image":
                    image_block = {"type": "image", "source": block.get("source", {})}
                    formatted_blocks.append(image_block)
                else:
                    # Pass through other block types (text, tool_use, tool_result)
                    formatted_blocks.append(block)
        return formatted_blocks

    return content


def _format_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Format messages for the Anthropic API.

    Handles content formatting for each message.

    Args:
        messages: List of message dicts with role and content

    Returns:
        Formatted messages list
    """
    formatted = []
    for msg in messages:
        formatted_msg = {
            "role": msg["role"],
            "content": _format_content_block(msg.get("content", ""))
        }
        formatted.append(formatted_msg)
    return formatted


# =============================================================================
# Actions
# =============================================================================

def create_message(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a message (completion) using Claude.

    Params:
        model (str): Model to use (e.g., 'claude-sonnet-4-20250514') (optional, uses profile default)
        messages (list): List of message dicts with 'role' and 'content' (required)
            - role: 'user' or 'assistant'
            - content: String or list of content blocks
            - Content blocks can be:
                - {"type": "text", "text": "..."}
                - {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}}
                - {"type": "image", "source": {"type": "url", "url": "..."}}
                - {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
                - {"type": "tool_result", "tool_use_id": "...", "content": "..."}
        max_tokens (int): Maximum tokens to generate (optional, uses profile default or 1024)
        temperature (float): Sampling temperature 0-1 (optional)
        system (str): System prompt (optional)
        stop_sequences (list): Stop sequences (optional)
        tools (list): Tool definitions for function calling (optional)
            - Each tool: {"name": "...", "description": "...", "input_schema": {...}}
        tool_choice (dict): Tool choice configuration (optional)
            - {"type": "auto"} - Model decides whether to use tools
            - {"type": "any"} - Model must use a tool
            - {"type": "tool", "name": "..."} - Model must use specific tool
        top_p (float): Nucleus sampling parameter (optional)
        top_k (int): Top-k sampling parameter (optional)
        metadata (dict): Request metadata, e.g., {"user_id": "..."} (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response including id, type, role, content, model, stop_reason, usage
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)

        messages = params.get("messages")
        if not messages:
            return {"ok": False, "error": "messages is required"}

        # Build request payload
        request_data: Dict[str, Any] = {
            "model": params.get("model", profile.get("default_model", "claude-sonnet-4-20250514")),
            "messages": _format_messages(messages),
            "max_tokens": params.get("max_tokens", profile.get("default_max_tokens", 1024)),
        }

        # Optional parameters
        if params.get("temperature") is not None:
            request_data["temperature"] = float(params["temperature"])

        if params.get("system") is not None:
            request_data["system"] = params["system"]

        if params.get("stop_sequences") is not None:
            request_data["stop_sequences"] = params["stop_sequences"]

        if params.get("tools") is not None:
            request_data["tools"] = params["tools"]

        if params.get("tool_choice") is not None:
            request_data["tool_choice"] = params["tool_choice"]

        if params.get("top_p") is not None:
            request_data["top_p"] = float(params["top_p"])

        if params.get("top_k") is not None:
            request_data["top_k"] = int(params["top_k"])

        if params.get("metadata") is not None:
            request_data["metadata"] = params["metadata"]

        return _api_call(api_key, "messages", method="POST", data=request_data)

    except Exception as e:
        logger.exception("create_message failed")
        return {"ok": False, "error": str(e)}


def create_message_stream(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a streaming message using Claude.

    Same parameters as create_message, but returns streaming information.

    Note: This returns information about how to consume the stream.
    The actual streaming requires iterating over the generator returned
    by _api_call_stream.

    Params:
        (Same as create_message)

    Returns:
        ok (bool): Success status
        data (dict): Stream configuration info including:
            - stream_type: 'sse' (Server-Sent Events)
            - events: List of event types to expect
            - request_data: The request that would be sent

    For actual streaming, use the internal _api_call_stream function directly
    or implement SSE consumption in your application.
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)

        messages = params.get("messages")
        if not messages:
            return {"ok": False, "error": "messages is required"}

        # Build request payload with streaming enabled
        request_data: Dict[str, Any] = {
            "model": params.get("model", profile.get("default_model", "claude-sonnet-4-20250514")),
            "messages": _format_messages(messages),
            "max_tokens": params.get("max_tokens", profile.get("default_max_tokens", 1024)),
            "stream": True,
        }

        # Optional parameters
        if params.get("temperature") is not None:
            request_data["temperature"] = float(params["temperature"])

        if params.get("system") is not None:
            request_data["system"] = params["system"]

        if params.get("stop_sequences") is not None:
            request_data["stop_sequences"] = params["stop_sequences"]

        if params.get("tools") is not None:
            request_data["tools"] = params["tools"]

        if params.get("tool_choice") is not None:
            request_data["tool_choice"] = params["tool_choice"]

        if params.get("top_p") is not None:
            request_data["top_p"] = float(params["top_p"])

        if params.get("top_k") is not None:
            request_data["top_k"] = int(params["top_k"])

        if params.get("metadata") is not None:
            request_data["metadata"] = params["metadata"]

        # Collect all streamed events and reconstruct the full response
        events = []
        full_content = []
        final_message = None
        usage_info = {}

        for event in _api_call_stream(api_key, "messages", request_data):
            if "error" in event:
                return {"ok": False, "error": event["error"]}

            events.append(event)
            event_type = event.get("event")
            data = event.get("data", {})

            # Handle different event types
            if event_type == "message_start":
                final_message = data.get("message", {})
            elif event_type == "content_block_start":
                content_block = data.get("content_block", {})
                full_content.append(content_block)
            elif event_type == "content_block_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "text_delta" and full_content:
                    # Append text to the last content block
                    if "text" not in full_content[-1]:
                        full_content[-1]["text"] = ""
                    full_content[-1]["text"] += delta.get("text", "")
            elif event_type == "message_delta":
                delta = data.get("delta", {})
                if delta.get("stop_reason") and final_message:
                    final_message["stop_reason"] = delta["stop_reason"]
                usage = data.get("usage", {})
                if usage:
                    usage_info.update(usage)
            elif event_type == "message_stop":
                pass  # Stream complete

        # Construct final response
        if final_message:
            final_message["content"] = full_content
            if usage_info:
                final_message["usage"] = {**final_message.get("usage", {}), **usage_info}
            return {"ok": True, "data": final_message}
        else:
            return {
                "ok": True,
                "data": {
                    "stream_type": "sse",
                    "events_received": len(events),
                    "content": full_content,
                }
            }

    except Exception as e:
        logger.exception("create_message_stream failed")
        return {"ok": False, "error": str(e)}


def count_tokens(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Count tokens in messages.

    Uses the Anthropic token counting endpoint to count tokens
    without creating a completion.

    Params:
        model (str): Model to use for tokenization (optional, uses profile default)
        messages (list): List of message dicts to count tokens for (required)
        system (str): System prompt to include in count (optional)
        tools (list): Tool definitions to include in count (optional)

    Returns:
        ok (bool): Success status
        data (dict): Token count information including input_tokens
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)

        messages = params.get("messages")
        if not messages:
            return {"ok": False, "error": "messages is required"}

        request_data: Dict[str, Any] = {
            "model": params.get("model", profile.get("default_model", "claude-sonnet-4-20250514")),
            "messages": _format_messages(messages),
        }

        if params.get("system") is not None:
            request_data["system"] = params["system"]

        if params.get("tools") is not None:
            request_data["tools"] = params["tools"]

        return _api_call(api_key, "messages/count_tokens", method="POST", data=request_data)

    except Exception as e:
        logger.exception("count_tokens failed")
        return {"ok": False, "error": str(e)}


def list_models(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List available Anthropic models.

    Params:
        limit (int): Maximum number of models to return (optional, default: 20)
        before_id (str): Cursor for pagination - get models before this ID (optional)
        after_id (str): Cursor for pagination - get models after this ID (optional)

    Returns:
        ok (bool): Success status
        data (dict): Response including:
            - data: List of model objects with id, display_name, created_at
            - has_more: Whether more models are available
            - first_id, last_id: Pagination cursors
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)

        # Build query parameters
        query_params = []

        if params.get("limit") is not None:
            query_params.append(f"limit={int(params['limit'])}")

        if params.get("before_id") is not None:
            query_params.append(f"before_id={params['before_id']}")

        if params.get("after_id") is not None:
            query_params.append(f"after_id={params['after_id']}")

        endpoint = "models"
        if query_params:
            endpoint += "?" + "&".join(query_params)

        return _api_call(api_key, endpoint, method="GET")

    except Exception as e:
        logger.exception("list_models failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "create_message": create_message,
    "create_message_stream": create_message_stream,
    "count_tokens": count_tokens,
    "list_models": list_models,
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

    logger.info(f"Executing anthropic.{profile}.{action}")
    return ACTIONS[action](profile, params)
