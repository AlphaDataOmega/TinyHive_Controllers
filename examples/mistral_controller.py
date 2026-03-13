"""
Mistral AI Controller for TinyHive

A controller for interacting with Mistral AI's API endpoints.

Method IDs:
  controller.mistral.{profile}.chat_complete
  controller.mistral.{profile}.create_embedding
  controller.mistral.{profile}.list_models
  controller.mistral.{profile}.create_fim_completion
  controller.mistral.{profile}.moderate
  controller.mistral.{profile}.upload_file
  controller.mistral.{profile}.list_files
  controller.mistral.{profile}.create_fine_tuning_job

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "api_key_env": "MISTRAL_API_KEY",
    "default_model": "mistral-large-latest",
    "default_embedding_model": "mistral-embed",
    "timeout": 120
}

Dependencies:
------------
- None (standard library only)
"""

import base64
import json
import logging
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger("tinyhive.controller.mistral")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Mistral API base URL
MISTRAL_API_BASE = "https://api.mistral.ai/v1"

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
    """Get the API key from environment variable specified in profile."""
    env_var = profile.get("api_key_env", "MISTRAL_API_KEY")
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
    """Make an authenticated Mistral API call."""
    url = f"{MISTRAL_API_BASE}/{endpoint}"

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
            if isinstance(error_message, dict):
                error_message = error_message.get("message", str(error_message))
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Mistral API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Mistral API call")
        return {"ok": False, "error": str(e)}


def _multipart_api_call(
    api_key: str,
    endpoint: str,
    fields: Dict[str, Any],
    file_field: str,
    file_path: str,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make a multipart/form-data API call for file uploads."""
    url = f"{MISTRAL_API_BASE}/{endpoint}"

    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"

    body_parts = []

    # Add regular fields
    for key, value in fields.items():
        body_parts.append(f"--{boundary}".encode("utf-8"))
        body_parts.append(f'Content-Disposition: form-data; name="{key}"'.encode("utf-8"))
        body_parts.append(b"")
        body_parts.append(str(value).encode("utf-8"))

    # Add file field
    path = Path(file_path)
    if not path.exists():
        return {"ok": False, "error": f"File not found: {file_path}"}

    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type is None:
        mime_type = "application/octet-stream"

    file_content = path.read_bytes()
    body_parts.append(f"--{boundary}".encode("utf-8"))
    body_parts.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{path.name}"'.encode("utf-8")
    )
    body_parts.append(f"Content-Type: {mime_type}".encode("utf-8"))
    body_parts.append(b"")
    body_parts.append(file_content)

    # End boundary
    body_parts.append(f"--{boundary}--".encode("utf-8"))
    body_parts.append(b"")

    body = b"\r\n".join(body_parts)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }

    try:
        req = Request(url, data=body, headers=headers, method="POST")
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
        logger.error("Mistral API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Mistral API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def chat_complete(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a chat completion.

    Params:
        model (str): Model to use (default: from profile or mistral-large-latest)
        messages (list): List of message objects with 'role' and 'content'
        temperature (float): Sampling temperature (0.0-1.0, optional)
        max_tokens (int): Maximum tokens to generate (optional)
        top_p (float): Nucleus sampling (optional)
        stream (bool): Whether to stream (default: false, not supported)
        safe_prompt (bool): Whether to inject safety prompt (optional)
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        messages = params.get("messages")
        if not messages:
            return {"ok": False, "error": "messages is required"}

        model = params.get("model", profile.get("default_model", "mistral-large-latest"))

        request_body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        if "temperature" in params:
            request_body["temperature"] = params["temperature"]
        if "max_tokens" in params:
            request_body["max_tokens"] = params["max_tokens"]
        if "top_p" in params:
            request_body["top_p"] = params["top_p"]
        if "safe_prompt" in params:
            request_body["safe_prompt"] = params["safe_prompt"]

        data = json.dumps(request_body).encode("utf-8")
        result = _api_call(api_key, "chat/completions", method="POST", data=data, timeout=timeout)

        if result.get("ok") and "data" in result:
            response_data = result["data"]
            choices = response_data.get("choices", [])
            return {
                "ok": True,
                "data": {
                    "id": response_data.get("id"),
                    "model": response_data.get("model"),
                    "choices": [
                        {
                            "index": c.get("index"),
                            "message": c.get("message"),
                            "finish_reason": c.get("finish_reason"),
                        }
                        for c in choices
                    ],
                    "usage": response_data.get("usage"),
                }
            }
        return result
    except Exception as e:
        logger.exception("chat_complete failed")
        return {"ok": False, "error": str(e)}


def create_embedding(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate embeddings for input text.

    Params:
        model (str): Embedding model (default: from profile or mistral-embed)
        input (str|list): Text or list of texts to embed
        encoding_format (str): Format ('float' or 'base64', optional)
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        input_text = params.get("input")
        if not input_text:
            return {"ok": False, "error": "input is required"}

        model = params.get("model", profile.get("default_embedding_model", "mistral-embed"))

        request_body: Dict[str, Any] = {
            "model": model,
            "input": input_text if isinstance(input_text, list) else [input_text],
        }

        if "encoding_format" in params:
            request_body["encoding_format"] = params["encoding_format"]

        data = json.dumps(request_body).encode("utf-8")
        result = _api_call(api_key, "embeddings", method="POST", data=data, timeout=timeout)

        if result.get("ok") and "data" in result:
            response_data = result["data"]
            return {
                "ok": True,
                "data": {
                    "model": response_data.get("model"),
                    "embeddings": [
                        {
                            "index": e.get("index"),
                            "embedding": e.get("embedding"),
                        }
                        for e in response_data.get("data", [])
                    ],
                    "usage": response_data.get("usage"),
                }
            }
        return result
    except Exception as e:
        logger.exception("create_embedding failed")
        return {"ok": False, "error": str(e)}


def list_models(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List available models.

    Params:
        None required
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        result = _api_call(api_key, "models", method="GET", timeout=timeout)

        if result.get("ok") and "data" in result:
            response_data = result["data"]
            models = response_data.get("data", [])
            return {
                "ok": True,
                "data": {
                    "models": [
                        {
                            "id": m.get("id"),
                            "object": m.get("object"),
                            "created": m.get("created"),
                            "owned_by": m.get("owned_by"),
                        }
                        for m in models
                    ]
                }
            }
        return result
    except Exception as e:
        logger.exception("list_models failed")
        return {"ok": False, "error": str(e)}


def create_fim_completion(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a fill-in-the-middle (FIM) completion.

    Params:
        model (str): Model to use (default: codestral-latest)
        prompt (str): The text before the completion (required)
        suffix (str): The text after the completion (optional)
        temperature (float): Sampling temperature (optional)
        max_tokens (int): Maximum tokens to generate (optional)
        top_p (float): Nucleus sampling (optional)
        stop (list): Stop sequences (optional)
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        prompt = params.get("prompt")
        if not prompt:
            return {"ok": False, "error": "prompt is required"}

        model = params.get("model", profile.get("default_fim_model", "codestral-latest"))

        request_body: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
        }

        if "suffix" in params:
            request_body["suffix"] = params["suffix"]
        if "temperature" in params:
            request_body["temperature"] = params["temperature"]
        if "max_tokens" in params:
            request_body["max_tokens"] = params["max_tokens"]
        if "top_p" in params:
            request_body["top_p"] = params["top_p"]
        if "stop" in params:
            request_body["stop"] = params["stop"]

        data = json.dumps(request_body).encode("utf-8")
        result = _api_call(api_key, "fim/completions", method="POST", data=data, timeout=timeout)

        if result.get("ok") and "data" in result:
            response_data = result["data"]
            choices = response_data.get("choices", [])
            return {
                "ok": True,
                "data": {
                    "id": response_data.get("id"),
                    "model": response_data.get("model"),
                    "choices": [
                        {
                            "index": c.get("index"),
                            "message": c.get("message"),
                            "finish_reason": c.get("finish_reason"),
                        }
                        for c in choices
                    ],
                    "usage": response_data.get("usage"),
                }
            }
        return result
    except Exception as e:
        logger.exception("create_fim_completion failed")
        return {"ok": False, "error": str(e)}


def moderate(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform content moderation on input text.

    Params:
        model (str): Moderation model (default: mistral-moderation-latest)
        input (str|list): Text or list of texts to moderate
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        input_text = params.get("input")
        if not input_text:
            return {"ok": False, "error": "input is required"}

        model = params.get("model", profile.get("default_moderation_model", "mistral-moderation-latest"))

        request_body: Dict[str, Any] = {
            "model": model,
            "input": input_text if isinstance(input_text, list) else [input_text],
        }

        data = json.dumps(request_body).encode("utf-8")
        result = _api_call(api_key, "moderations", method="POST", data=data, timeout=timeout)

        if result.get("ok") and "data" in result:
            response_data = result["data"]
            return {
                "ok": True,
                "data": {
                    "id": response_data.get("id"),
                    "model": response_data.get("model"),
                    "results": response_data.get("results", []),
                }
            }
        return result
    except Exception as e:
        logger.exception("moderate failed")
        return {"ok": False, "error": str(e)}


def upload_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upload a file for fine-tuning.

    Params:
        file_path (str): Path to the local file to upload (required)
        purpose (str): Purpose of the file (default: fine-tune)
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        file_path = params.get("file_path")
        if not file_path:
            return {"ok": False, "error": "file_path is required"}

        purpose = params.get("purpose", "fine-tune")

        fields = {"purpose": purpose}
        result = _multipart_api_call(
            api_key, "files", fields, "file", file_path, timeout=timeout
        )

        if result.get("ok") and "data" in result:
            response_data = result["data"]
            return {
                "ok": True,
                "data": {
                    "id": response_data.get("id"),
                    "object": response_data.get("object"),
                    "bytes": response_data.get("bytes"),
                    "created_at": response_data.get("created_at"),
                    "filename": response_data.get("filename"),
                    "purpose": response_data.get("purpose"),
                }
            }
        return result
    except Exception as e:
        logger.exception("upload_file failed")
        return {"ok": False, "error": str(e)}


def list_files(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List uploaded files.

    Params:
        purpose (str): Filter by purpose (optional)
        page (int): Page number (optional)
        page_size (int): Number of items per page (optional)
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        query_params = {}
        if "purpose" in params:
            query_params["purpose"] = params["purpose"]
        if "page" in params:
            query_params["page"] = params["page"]
        if "page_size" in params:
            query_params["page_size"] = params["page_size"]

        endpoint = "files"
        if query_params:
            endpoint += "?" + urlencode(query_params)

        result = _api_call(api_key, endpoint, method="GET", timeout=timeout)

        if result.get("ok") and "data" in result:
            response_data = result["data"]
            files = response_data.get("data", [])
            return {
                "ok": True,
                "data": {
                    "files": [
                        {
                            "id": f.get("id"),
                            "object": f.get("object"),
                            "bytes": f.get("bytes"),
                            "created_at": f.get("created_at"),
                            "filename": f.get("filename"),
                            "purpose": f.get("purpose"),
                        }
                        for f in files
                    ],
                    "total": response_data.get("total"),
                }
            }
        return result
    except Exception as e:
        logger.exception("list_files failed")
        return {"ok": False, "error": str(e)}


def create_fine_tuning_job(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a fine-tuning job.

    Params:
        model (str): Base model to fine-tune (required)
        training_files (list): List of training file IDs (required)
        validation_files (list): List of validation file IDs (optional)
        hyperparameters (dict): Training hyperparameters (optional)
            - learning_rate (float)
            - training_steps (int)
            - weight_decay (float)
            - warmup_fraction (float)
        suffix (str): Suffix for the fine-tuned model name (optional)
        integrations (list): List of integrations (optional)
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        timeout = profile.get("timeout", DEFAULT_TIMEOUT)

        model = params.get("model")
        if not model:
            return {"ok": False, "error": "model is required"}

        training_files = params.get("training_files")
        if not training_files:
            return {"ok": False, "error": "training_files is required"}

        request_body: Dict[str, Any] = {
            "model": model,
            "training_files": training_files,
        }

        if "validation_files" in params:
            request_body["validation_files"] = params["validation_files"]
        if "hyperparameters" in params:
            request_body["hyperparameters"] = params["hyperparameters"]
        if "suffix" in params:
            request_body["suffix"] = params["suffix"]
        if "integrations" in params:
            request_body["integrations"] = params["integrations"]

        data = json.dumps(request_body).encode("utf-8")
        result = _api_call(api_key, "fine_tuning/jobs", method="POST", data=data, timeout=timeout)

        if result.get("ok") and "data" in result:
            response_data = result["data"]
            return {
                "ok": True,
                "data": {
                    "id": response_data.get("id"),
                    "object": response_data.get("object"),
                    "model": response_data.get("model"),
                    "fine_tuned_model": response_data.get("fine_tuned_model"),
                    "status": response_data.get("status"),
                    "created_at": response_data.get("created_at"),
                    "training_files": response_data.get("training_files"),
                    "validation_files": response_data.get("validation_files"),
                    "hyperparameters": response_data.get("hyperparameters"),
                }
            }
        return result
    except Exception as e:
        logger.exception("create_fine_tuning_job failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "chat_complete": chat_complete,
    "create_embedding": create_embedding,
    "list_models": list_models,
    "create_fim_completion": create_fim_completion,
    "moderate": moderate,
    "upload_file": upload_file,
    "list_files": list_files,
    "create_fine_tuning_job": create_fine_tuning_job,
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

    logger.info(f"Executing mistral.{profile}.{action}")
    return ACTIONS[action](profile, params)
