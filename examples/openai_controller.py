"""Example: OpenAI controller — Chat, Embeddings, Images, Audio, Moderation.

This is an example of how to build an OpenAI controller.
Copy to controllers/controller_openai/ and customize.

Method IDs:
  controller.openai.{profile}.chat_completion
  controller.openai.{profile}.create_embedding
  controller.openai.{profile}.create_image
  controller.openai.{profile}.transcribe_audio
  controller.openai.{profile}.text_to_speech
  controller.openai.{profile}.list_models
  controller.openai.{profile}.moderate
"""

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict
from urllib.request import Request, urlopen
from urllib.error import HTTPError

log = logging.getLogger("tinyhive.controller.openai")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

BASE_URL = "https://api.openai.com/v1"


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'")
    return json.loads(path.read_text())


def _get_api_key(profile: Dict[str, Any]) -> str:
    """Get OpenAI API key from environment variable."""
    env_var = profile.get("api_key_env", "OPENAI_API_KEY")
    api_key = os.environ.get(env_var, "")
    if not api_key:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return api_key


def _api_call(
    api_key: str,
    endpoint: str,
    method: str = "GET",
    data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Make an OpenAI API call using Bearer token auth.

    OpenAI API uses JSON for request/response bodies and
    Bearer token authentication.
    """
    url = f"{BASE_URL}/{endpoint}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body = None
    if data:
        body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=60) as response:
            return {"ok": True, "data": json.loads(response.read().decode("utf-8"))}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("error", {}).get("message", error_body[:500])
        except json.JSONDecodeError:
            error_msg = error_body[:500]
        return {"ok": False, "error": f"HTTP {e.code}: {error_msg}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _multipart_api_call(
    api_key: str,
    endpoint: str,
    fields: Dict[str, Any],
    file_field: str = None,
    file_path: str = None,
    file_content_type: str = "application/octet-stream"
) -> Dict[str, Any]:
    """Make a multipart/form-data API call for file uploads.

    Used for audio transcription and other file-based endpoints.
    """
    url = f"{BASE_URL}/{endpoint}"
    boundary = f"----TinyHiveBoundary{uuid.uuid4().hex}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }

    # Build multipart body
    body_parts = []

    # Add regular form fields
    for key, value in fields.items():
        if value is not None:
            body_parts.append(f"--{boundary}".encode("utf-8"))
            body_parts.append(
                f'Content-Disposition: form-data; name="{key}"'.encode("utf-8")
            )
            body_parts.append(b"")
            body_parts.append(str(value).encode("utf-8"))

    # Add file field if provided
    if file_field and file_path:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return {"ok": False, "error": f"File not found: {file_path}"}

        file_data = file_path_obj.read_bytes()
        filename = file_path_obj.name

        body_parts.append(f"--{boundary}".encode("utf-8"))
        body_parts.append(
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"'.encode("utf-8")
        )
        body_parts.append(f"Content-Type: {file_content_type}".encode("utf-8"))
        body_parts.append(b"")
        body_parts.append(file_data)

    # End boundary
    body_parts.append(f"--{boundary}--".encode("utf-8"))
    body_parts.append(b"")

    body = b"\r\n".join(body_parts)

    try:
        req = Request(url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=120) as response:
            content_type = response.headers.get("Content-Type", "")
            response_data = response.read()

            # Handle JSON responses
            if "application/json" in content_type:
                return {"ok": True, "data": json.loads(response_data.decode("utf-8"))}
            # Handle binary responses (e.g., audio from TTS)
            else:
                return {"ok": True, "data": {"content": response_data, "content_type": content_type}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("error", {}).get("message", error_body[:500])
        except json.JSONDecodeError:
            error_msg = error_body[:500]
        return {"ok": False, "error": f"HTTP {e.code}: {error_msg}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Chat Completions
# ---------------------------------------------------------------------------

def chat_completion(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a chat completion.

    Params:
        - model: Model to use (default: "gpt-4o")
        - messages: List of message dicts with "role" and "content" (required)
        - temperature: Sampling temperature 0-2 (default: 1.0)
        - max_tokens: Maximum tokens to generate (optional)
        - top_p: Nucleus sampling parameter (optional)
        - frequency_penalty: Frequency penalty -2.0 to 2.0 (optional)
        - presence_penalty: Presence penalty -2.0 to 2.0 (optional)
        - stop: Stop sequences (optional, string or list)
        - user: Unique user identifier (optional)
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    messages = params.get("messages")
    if not messages:
        return {"ok": False, "error": "messages is required"}

    request_data = {
        "model": params.get("model", profile.get("default_model", "gpt-4o")),
        "messages": messages,
    }

    if params.get("temperature") is not None:
        request_data["temperature"] = float(params["temperature"])
    if params.get("max_tokens") is not None:
        request_data["max_tokens"] = int(params["max_tokens"])
    if params.get("top_p") is not None:
        request_data["top_p"] = float(params["top_p"])
    if params.get("frequency_penalty") is not None:
        request_data["frequency_penalty"] = float(params["frequency_penalty"])
    if params.get("presence_penalty") is not None:
        request_data["presence_penalty"] = float(params["presence_penalty"])
    if params.get("stop") is not None:
        request_data["stop"] = params["stop"]
    if params.get("user") is not None:
        request_data["user"] = params["user"]

    return _api_call(api_key, "chat/completions", method="POST", data=request_data)


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def create_embedding(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate embeddings for input text.

    Params:
        - model: Embedding model to use (default: "text-embedding-3-small")
        - input: Text to embed (required, string or list of strings)
        - encoding_format: "float" or "base64" (default: "float")
        - dimensions: Output dimensions for models that support it (optional)
        - user: Unique user identifier (optional)
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    input_text = params.get("input")
    if not input_text:
        return {"ok": False, "error": "input is required"}

    request_data = {
        "model": params.get("model", profile.get("default_embedding_model", "text-embedding-3-small")),
        "input": input_text,
    }

    if params.get("encoding_format") is not None:
        request_data["encoding_format"] = params["encoding_format"]
    if params.get("dimensions") is not None:
        request_data["dimensions"] = int(params["dimensions"])
    if params.get("user") is not None:
        request_data["user"] = params["user"]

    return _api_call(api_key, "embeddings", method="POST", data=request_data)


# ---------------------------------------------------------------------------
# Image Generation (DALL-E)
# ---------------------------------------------------------------------------

def create_image(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate images using DALL-E.

    Params:
        - prompt: Image description (required)
        - model: Model to use (default: "dall-e-3")
        - size: Image size (default: "1024x1024")
            - dall-e-2: "256x256", "512x512", "1024x1024"
            - dall-e-3: "1024x1024", "1792x1024", "1024x1792"
        - n: Number of images to generate (default: 1, dall-e-3 only supports 1)
        - quality: "standard" or "hd" (dall-e-3 only, default: "standard")
        - style: "vivid" or "natural" (dall-e-3 only, default: "vivid")
        - response_format: "url" or "b64_json" (default: "url")
        - user: Unique user identifier (optional)
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    prompt = params.get("prompt")
    if not prompt:
        return {"ok": False, "error": "prompt is required"}

    model = params.get("model", profile.get("default_image_model", "dall-e-3"))

    request_data = {
        "model": model,
        "prompt": prompt,
        "size": params.get("size", "1024x1024"),
        "n": params.get("n", 1),
    }

    if params.get("quality") is not None:
        request_data["quality"] = params["quality"]
    if params.get("style") is not None:
        request_data["style"] = params["style"]
    if params.get("response_format") is not None:
        request_data["response_format"] = params["response_format"]
    if params.get("user") is not None:
        request_data["user"] = params["user"]

    return _api_call(api_key, "images/generations", method="POST", data=request_data)


# ---------------------------------------------------------------------------
# Audio Transcription (Whisper)
# ---------------------------------------------------------------------------

def transcribe_audio(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Transcribe audio using Whisper.

    Params:
        - file_path: Path to audio file (required)
            Supported formats: flac, mp3, mp4, mpeg, mpga, m4a, ogg, wav, webm
        - model: Model to use (default: "whisper-1")
        - language: Language code in ISO-639-1 format (optional, improves accuracy)
        - prompt: Optional text to guide the model's style (optional)
        - response_format: "json", "text", "srt", "verbose_json", "vtt" (default: "json")
        - temperature: Sampling temperature 0-1 (default: 0)
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    file_path = params.get("file_path")
    if not file_path:
        return {"ok": False, "error": "file_path is required"}

    # Determine content type from extension
    ext = Path(file_path).suffix.lower()
    content_types = {
        ".flac": "audio/flac",
        ".mp3": "audio/mpeg",
        ".mp4": "audio/mp4",
        ".mpeg": "audio/mpeg",
        ".mpga": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
        ".webm": "audio/webm",
    }
    content_type = content_types.get(ext, "application/octet-stream")

    fields = {
        "model": params.get("model", profile.get("default_whisper_model", "whisper-1")),
    }

    if params.get("language") is not None:
        fields["language"] = params["language"]
    if params.get("prompt") is not None:
        fields["prompt"] = params["prompt"]
    if params.get("response_format") is not None:
        fields["response_format"] = params["response_format"]
    if params.get("temperature") is not None:
        fields["temperature"] = params["temperature"]

    return _multipart_api_call(
        api_key,
        "audio/transcriptions",
        fields=fields,
        file_field="file",
        file_path=file_path,
        file_content_type=content_type
    )


# ---------------------------------------------------------------------------
# Text-to-Speech
# ---------------------------------------------------------------------------

def text_to_speech(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate speech from text.

    Params:
        - input: Text to convert to speech (required, max 4096 characters)
        - model: TTS model (default: "tts-1", also "tts-1-hd" for higher quality)
        - voice: Voice to use (required)
            Options: "alloy", "echo", "fable", "onyx", "nova", "shimmer"
        - response_format: Audio format (default: "mp3")
            Options: "mp3", "opus", "aac", "flac", "wav", "pcm"
        - speed: Speed of speech 0.25-4.0 (default: 1.0)
        - output_path: Path to save audio file (optional, if not provided returns bytes)
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    input_text = params.get("input")
    if not input_text:
        return {"ok": False, "error": "input is required"}

    voice = params.get("voice")
    if not voice:
        return {"ok": False, "error": "voice is required"}

    request_data = {
        "model": params.get("model", profile.get("default_tts_model", "tts-1")),
        "input": input_text,
        "voice": voice,
    }

    if params.get("response_format") is not None:
        request_data["response_format"] = params["response_format"]
    if params.get("speed") is not None:
        request_data["speed"] = float(params["speed"])

    # TTS endpoint returns binary audio data, not JSON
    url = f"{BASE_URL}/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = json.dumps(request_data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=120) as response:
            audio_data = response.read()
            content_type = response.headers.get("Content-Type", "audio/mpeg")

            # Save to file if output_path is provided
            output_path = params.get("output_path")
            if output_path:
                Path(output_path).write_bytes(audio_data)
                return {
                    "ok": True,
                    "data": {
                        "saved_to": output_path,
                        "size_bytes": len(audio_data),
                        "content_type": content_type
                    }
                }
            else:
                return {
                    "ok": True,
                    "data": {
                        "content": audio_data,
                        "size_bytes": len(audio_data),
                        "content_type": content_type
                    }
                }
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("error", {}).get("message", error_body[:500])
        except json.JSONDecodeError:
            error_msg = error_body[:500]
        return {"ok": False, "error": f"HTTP {e.code}: {error_msg}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

def list_models(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List available models.

    Params:
        - filter_prefix: Optional prefix to filter models (e.g., "gpt-4", "dall-e")

    Returns a list of available model objects with id, created, and owned_by fields.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    result = _api_call(api_key, "models")

    # Optionally filter by prefix
    filter_prefix = params.get("filter_prefix")
    if result.get("ok") and filter_prefix:
        models = result["data"].get("data", [])
        filtered = [m for m in models if m.get("id", "").startswith(filter_prefix)]
        result["data"]["data"] = filtered

    return result


# ---------------------------------------------------------------------------
# Moderation
# ---------------------------------------------------------------------------

def moderate(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Check content for policy violations.

    Params:
        - input: Text to moderate (required, string or list of strings)
        - model: Moderation model (default: "omni-moderation-latest")
            Options: "omni-moderation-latest", "text-moderation-latest", "text-moderation-stable"

    Returns moderation results including flagged status and category scores.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    input_text = params.get("input")
    if not input_text:
        return {"ok": False, "error": "input is required"}

    request_data = {
        "input": input_text,
    }

    if params.get("model") is not None:
        request_data["model"] = params["model"]

    return _api_call(api_key, "moderations", method="POST", data=request_data)


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

ACTIONS = {
    "chat_completion": chat_completion,
    "create_embedding": create_embedding,
    "create_image": create_image,
    "transcribe_audio": transcribe_audio,
    "text_to_speech": text_to_speech,
    "list_models": list_models,
    "moderate": moderate,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """Dispatch an action by name with a profile."""
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action '{action}'"}
    return ACTIONS[action](profile, params)
