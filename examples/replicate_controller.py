"""
Replicate Controller for TinyHive

A controller for interacting with the Replicate API to run machine learning models.

Method IDs:
  controller.replicate.{profile}.create_prediction
  controller.replicate.{profile}.get_prediction
  controller.replicate.{profile}.cancel_prediction
  controller.replicate.{profile}.list_predictions
  controller.replicate.{profile}.list_models
  controller.replicate.{profile}.get_model
  controller.replicate.{profile}.get_model_versions
  controller.replicate.{profile}.list_collections

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "token_env": "REPLICATE_API_TOKEN",
    "default_timeout": 60,
    "webhook_url": null  // Optional webhook for prediction completion
}

Required Permissions:
--------------------
- API token with appropriate scopes from https://replicate.com/account/api-tokens

Dependencies:
------------
- None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.replicate")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Replicate API base URL
API_BASE_URL = "https://api.replicate.com/v1"

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


def _get_api_token(profile: Dict[str, Any]) -> str:
    """Get the API token from environment variable specified in profile."""
    token_env = profile.get("token_env", "REPLICATE_API_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(
            f"Environment variable '{token_env}' not set. "
            "Get your API token from https://replicate.com/account/api-tokens"
        )
    return token


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Replicate API call."""
    url = f"{API_BASE_URL}{endpoint}"

    headers = {
        "Authorization": f"Bearer {token}",
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
                return {"ok": True, "data": json.loads(response_body)}
            return {"ok": True, "data": {}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("detail", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Replicate API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Replicate API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Prediction Actions
# =============================================================================

def create_prediction(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new prediction (run a model).

    Params:
        version (str): The model version ID to run (required)
        input (dict): Input parameters for the model (required)
        webhook (str): Webhook URL for completion notification (optional)
        webhook_events_filter (list): Events to send to webhook (optional)
            Options: "start", "output", "logs", "completed"

    Returns:
        Prediction object with id, status, urls, etc.
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    timeout = profile.get("default_timeout", DEFAULT_TIMEOUT)

    version = params.get("version")
    model_input = params.get("input")

    if not version:
        return {"ok": False, "error": "version is required"}
    if not model_input:
        return {"ok": False, "error": "input is required"}

    data: Dict[str, Any] = {
        "version": version,
        "input": model_input,
    }

    # Add optional webhook configuration
    webhook = params.get("webhook") or profile.get("webhook_url")
    if webhook:
        data["webhook"] = webhook

    webhook_events = params.get("webhook_events_filter")
    if webhook_events:
        data["webhook_events_filter"] = webhook_events

    result = _api_call(token, "/predictions", method="POST", data=data, timeout=timeout)

    if result.get("ok") and "data" in result:
        prediction = result["data"]
        return {
            "ok": True,
            "result": {
                "id": prediction.get("id"),
                "status": prediction.get("status"),
                "version": prediction.get("version"),
                "urls": prediction.get("urls", {}),
                "created_at": prediction.get("created_at"),
            }
        }
    return result


def get_prediction(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the status and result of a prediction.

    Params:
        prediction_id (str): The prediction ID (required)

    Returns:
        Prediction object with status, output, logs, metrics, etc.
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    timeout = profile.get("default_timeout", DEFAULT_TIMEOUT)

    prediction_id = params.get("prediction_id")
    if not prediction_id:
        return {"ok": False, "error": "prediction_id is required"}

    result = _api_call(token, f"/predictions/{prediction_id}", timeout=timeout)

    if result.get("ok") and "data" in result:
        prediction = result["data"]
        return {
            "ok": True,
            "result": {
                "id": prediction.get("id"),
                "status": prediction.get("status"),
                "version": prediction.get("version"),
                "input": prediction.get("input"),
                "output": prediction.get("output"),
                "error": prediction.get("error"),
                "logs": prediction.get("logs"),
                "metrics": prediction.get("metrics"),
                "created_at": prediction.get("created_at"),
                "started_at": prediction.get("started_at"),
                "completed_at": prediction.get("completed_at"),
                "urls": prediction.get("urls", {}),
            }
        }
    return result


def cancel_prediction(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cancel a running prediction.

    Params:
        prediction_id (str): The prediction ID to cancel (required)

    Returns:
        Updated prediction object with canceled status.
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    timeout = profile.get("default_timeout", DEFAULT_TIMEOUT)

    prediction_id = params.get("prediction_id")
    if not prediction_id:
        return {"ok": False, "error": "prediction_id is required"}

    result = _api_call(
        token,
        f"/predictions/{prediction_id}/cancel",
        method="POST",
        timeout=timeout
    )

    if result.get("ok") and "data" in result:
        prediction = result["data"]
        return {
            "ok": True,
            "result": {
                "id": prediction.get("id"),
                "status": prediction.get("status"),
                "canceled_at": prediction.get("completed_at"),
            }
        }
    return result


def list_predictions(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List recent predictions.

    Params:
        cursor (str): Pagination cursor for next page (optional)

    Returns:
        List of predictions with pagination info.
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    timeout = profile.get("default_timeout", DEFAULT_TIMEOUT)

    endpoint = "/predictions"
    cursor = params.get("cursor")
    if cursor:
        endpoint = f"/predictions?cursor={cursor}"

    result = _api_call(token, endpoint, timeout=timeout)

    if result.get("ok") and "data" in result:
        data = result["data"]
        predictions = data.get("results", [])
        return {
            "ok": True,
            "result": {
                "predictions": [
                    {
                        "id": p.get("id"),
                        "status": p.get("status"),
                        "version": p.get("version"),
                        "created_at": p.get("created_at"),
                        "completed_at": p.get("completed_at"),
                    }
                    for p in predictions
                ],
                "next": data.get("next"),
                "previous": data.get("previous"),
            }
        }
    return result


# =============================================================================
# Model Actions
# =============================================================================

def list_models(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List public models for an owner.

    Params:
        owner (str): Model owner username (required)
        cursor (str): Pagination cursor for next page (optional)

    Returns:
        List of models owned by the specified user/organization.
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    timeout = profile.get("default_timeout", DEFAULT_TIMEOUT)

    owner = params.get("owner")
    if not owner:
        return {"ok": False, "error": "owner is required"}

    endpoint = f"/models?owner={owner}"
    cursor = params.get("cursor")
    if cursor:
        endpoint = f"{endpoint}&cursor={cursor}"

    result = _api_call(token, endpoint, timeout=timeout)

    if result.get("ok") and "data" in result:
        data = result["data"]
        models = data.get("results", [])
        return {
            "ok": True,
            "result": {
                "models": [
                    {
                        "owner": m.get("owner"),
                        "name": m.get("name"),
                        "description": m.get("description"),
                        "visibility": m.get("visibility"),
                        "url": m.get("url"),
                        "github_url": m.get("github_url"),
                        "paper_url": m.get("paper_url"),
                        "license_url": m.get("license_url"),
                        "run_count": m.get("run_count"),
                        "cover_image_url": m.get("cover_image_url"),
                        "default_example": m.get("default_example"),
                        "latest_version": m.get("latest_version", {}).get("id") if m.get("latest_version") else None,
                    }
                    for m in models
                ],
                "next": data.get("next"),
                "previous": data.get("previous"),
            }
        }
    return result


def get_model(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a specific model.

    Params:
        owner (str): Model owner username (required)
        name (str): Model name (required)

    Returns:
        Detailed model information including latest version.
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    timeout = profile.get("default_timeout", DEFAULT_TIMEOUT)

    owner = params.get("owner")
    name = params.get("name")

    if not owner:
        return {"ok": False, "error": "owner is required"}
    if not name:
        return {"ok": False, "error": "name is required"}

    result = _api_call(token, f"/models/{owner}/{name}", timeout=timeout)

    if result.get("ok") and "data" in result:
        model = result["data"]
        latest_version = model.get("latest_version", {})
        return {
            "ok": True,
            "result": {
                "owner": model.get("owner"),
                "name": model.get("name"),
                "description": model.get("description"),
                "visibility": model.get("visibility"),
                "url": model.get("url"),
                "github_url": model.get("github_url"),
                "paper_url": model.get("paper_url"),
                "license_url": model.get("license_url"),
                "run_count": model.get("run_count"),
                "cover_image_url": model.get("cover_image_url"),
                "default_example": model.get("default_example"),
                "latest_version": {
                    "id": latest_version.get("id"),
                    "created_at": latest_version.get("created_at"),
                    "cog_version": latest_version.get("cog_version"),
                    "openapi_schema": latest_version.get("openapi_schema"),
                } if latest_version else None,
            }
        }
    return result


def get_model_versions(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List versions for a model.

    Params:
        owner (str): Model owner username (required)
        name (str): Model name (required)
        cursor (str): Pagination cursor for next page (optional)

    Returns:
        List of model versions with their IDs and creation dates.
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    timeout = profile.get("default_timeout", DEFAULT_TIMEOUT)

    owner = params.get("owner")
    name = params.get("name")

    if not owner:
        return {"ok": False, "error": "owner is required"}
    if not name:
        return {"ok": False, "error": "name is required"}

    endpoint = f"/models/{owner}/{name}/versions"
    cursor = params.get("cursor")
    if cursor:
        endpoint = f"{endpoint}?cursor={cursor}"

    result = _api_call(token, endpoint, timeout=timeout)

    if result.get("ok") and "data" in result:
        data = result["data"]
        versions = data.get("results", [])
        return {
            "ok": True,
            "result": {
                "versions": [
                    {
                        "id": v.get("id"),
                        "created_at": v.get("created_at"),
                        "cog_version": v.get("cog_version"),
                        "openapi_schema": v.get("openapi_schema"),
                    }
                    for v in versions
                ],
                "next": data.get("next"),
                "previous": data.get("previous"),
            }
        }
    return result


# =============================================================================
# Collection Actions
# =============================================================================

def list_collections(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List model collections.

    Params:
        cursor (str): Pagination cursor for next page (optional)

    Returns:
        List of collections with their slugs, names, and descriptions.
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    timeout = profile.get("default_timeout", DEFAULT_TIMEOUT)

    endpoint = "/collections"
    cursor = params.get("cursor")
    if cursor:
        endpoint = f"/collections?cursor={cursor}"

    result = _api_call(token, endpoint, timeout=timeout)

    if result.get("ok") and "data" in result:
        data = result["data"]
        collections = data.get("results", [])
        return {
            "ok": True,
            "result": {
                "collections": [
                    {
                        "slug": c.get("slug"),
                        "name": c.get("name"),
                        "description": c.get("description"),
                    }
                    for c in collections
                ],
                "next": data.get("next"),
                "previous": data.get("previous"),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "create_prediction": create_prediction,
    "get_prediction": get_prediction,
    "cancel_prediction": cancel_prediction,
    "list_predictions": list_predictions,
    "list_models": list_models,
    "get_model": get_model,
    "get_model_versions": get_model_versions,
    "list_collections": list_collections,
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

    logger.info(f"Executing replicate.{profile}.{action}")
    return ACTIONS[action](profile, params)
