"""Typeform Controller — Typeform API integration for forms and responses.

This controller provides integration with the Typeform API for managing
forms, collecting responses, and accessing form analytics.

Method IDs:
  controller.typeform.{profile}.list_forms
  controller.typeform.{profile}.get_form
  controller.typeform.{profile}.list_responses
  controller.typeform.{profile}.get_response
  controller.typeform.{profile}.create_form
  controller.typeform.{profile}.update_form
  controller.typeform.{profile}.delete_form
  controller.typeform.{profile}.get_form_insights

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:

  {
    "token_env": "TYPEFORM_TOKEN",
    "workspace_id": "optional-workspace-id"
  }

Required Scopes:
  - forms:read - Read forms
  - forms:write - Create/update/delete forms
  - responses:read - Read form responses
  - insights:read - Read form analytics

Dependencies:
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

logger = logging.getLogger("tinyhive.controller.typeform")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# Typeform API base URL
API_BASE = "https://api.typeform.com"

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with Typeform configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available Typeform profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


def _get_token(profile: Dict[str, Any]) -> str:
    """Get the API token from environment variable."""
    env_var = profile.get("token_env", "TYPEFORM_TOKEN")
    token = os.environ.get(env_var, "")
    if not token:
        raise ValueError(
            f"Environment variable '{env_var}' not set. "
            "Create a personal access token at https://admin.typeform.com/user/tokens"
        )
    return token


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Typeform API call."""
    url = f"{API_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

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
            error_message = error_data.get("description", error_data.get("message", error_body[:500]))
            error_code = error_data.get("code", "UNKNOWN")
        except json.JSONDecodeError:
            error_message = error_body[:500]
            error_code = "UNKNOWN"
        logger.error("Typeform API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}", "error_code": error_code}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Typeform API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Forms Actions
# =============================================================================

def list_forms(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all forms in the workspace.

    Params:
        page (int): Page number (default: 1)
        page_size (int): Number of forms per page (default: 10, max: 200)
        workspace_id (str): Filter by workspace (optional, defaults to profile)
        search (str): Search forms by title (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    query_params = {}

    page = params.get("page", 1)
    page_size = params.get("page_size", 10)
    query_params["page"] = page
    query_params["page_size"] = min(page_size, 200)

    workspace_id = params.get("workspace_id", profile.get("workspace_id"))
    if workspace_id:
        query_params["workspace_id"] = workspace_id

    if params.get("search"):
        query_params["search"] = params["search"]

    endpoint = f"/forms?{urlencode(query_params)}"
    result = _api_call(token, endpoint)

    if result.get("ok") and "data" in result:
        data = result["data"]
        forms = data.get("items", [])
        return {
            "ok": True,
            "result": {
                "forms": [
                    {
                        "id": f.get("id"),
                        "title": f.get("title"),
                        "last_updated_at": f.get("last_updated_at"),
                        "created_at": f.get("created_at"),
                        "settings": f.get("settings", {}),
                        "_links": f.get("_links", {})
                    }
                    for f in forms
                ],
                "total_items": data.get("total_items", len(forms)),
                "page_count": data.get("page_count", 1)
            }
        }
    return result


def get_form(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific form.

    Params:
        form_id (str): The form ID (required)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    form_id = params.get("form_id", "")
    if not form_id:
        return {"ok": False, "error": "form_id is required"}

    endpoint = f"/forms/{form_id}"
    result = _api_call(token, endpoint)

    if result.get("ok") and "data" in result:
        form = result["data"]
        return {
            "ok": True,
            "result": {
                "id": form.get("id"),
                "title": form.get("title"),
                "workspace": form.get("workspace"),
                "theme": form.get("theme"),
                "settings": form.get("settings", {}),
                "welcome_screens": form.get("welcome_screens", []),
                "thankyou_screens": form.get("thankyou_screens", []),
                "fields": form.get("fields", []),
                "logic": form.get("logic", []),
                "created_at": form.get("created_at"),
                "last_updated_at": form.get("last_updated_at"),
                "_links": form.get("_links", {})
            }
        }
    return result


def create_form(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new form.

    Params:
        title (str): Form title (required)
        fields (list): List of field definitions (optional)
        workspace_id (str): Workspace to create form in (optional, defaults to profile)
        settings (dict): Form settings (optional)
        welcome_screens (list): Welcome screen definitions (optional)
        thankyou_screens (list): Thank you screen definitions (optional)

    Field definition example:
        {
            "type": "short_text",
            "title": "What is your name?",
            "ref": "name_field",
            "properties": {
                "description": "Please enter your full name"
            },
            "validations": {
                "required": true
            }
        }

    Common field types:
        - short_text, long_text, email, phone_number, url, number
        - yes_no, multiple_choice, dropdown, rating, opinion_scale
        - date, file_upload, payment, statement, group
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    title = params.get("title", "")
    if not title:
        return {"ok": False, "error": "title is required"}

    form_data: Dict[str, Any] = {"title": title}

    if params.get("fields"):
        form_data["fields"] = params["fields"]

    workspace_id = params.get("workspace_id", profile.get("workspace_id"))
    if workspace_id:
        form_data["workspace"] = {"href": f"{API_BASE}/workspaces/{workspace_id}"}

    if params.get("settings"):
        form_data["settings"] = params["settings"]

    if params.get("welcome_screens"):
        form_data["welcome_screens"] = params["welcome_screens"]

    if params.get("thankyou_screens"):
        form_data["thankyou_screens"] = params["thankyou_screens"]

    endpoint = "/forms"
    data = json.dumps(form_data).encode("utf-8")
    result = _api_call(token, endpoint, method="POST", data=data)

    if result.get("ok") and "data" in result:
        form = result["data"]
        return {
            "ok": True,
            "result": {
                "id": form.get("id"),
                "title": form.get("title"),
                "created_at": form.get("created_at"),
                "_links": form.get("_links", {})
            }
        }
    return result


def update_form(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing form.

    Params:
        form_id (str): The form ID (required)
        title (str): New form title (optional)
        fields (list): Updated field definitions (optional)
        settings (dict): Updated form settings (optional)
        welcome_screens (list): Updated welcome screens (optional)
        thankyou_screens (list): Updated thank you screens (optional)

    Note: This performs a PUT operation which replaces the entire form.
    Include all fields you want to keep, not just the ones you want to change.
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    form_id = params.get("form_id", "")
    if not form_id:
        return {"ok": False, "error": "form_id is required"}

    # Build update payload - at minimum need title
    form_data: Dict[str, Any] = {}

    if params.get("title"):
        form_data["title"] = params["title"]

    if params.get("fields") is not None:
        form_data["fields"] = params["fields"]

    if params.get("settings"):
        form_data["settings"] = params["settings"]

    if params.get("welcome_screens") is not None:
        form_data["welcome_screens"] = params["welcome_screens"]

    if params.get("thankyou_screens") is not None:
        form_data["thankyou_screens"] = params["thankyou_screens"]

    if not form_data:
        return {"ok": False, "error": "At least one field to update is required"}

    endpoint = f"/forms/{form_id}"
    data = json.dumps(form_data).encode("utf-8")
    result = _api_call(token, endpoint, method="PUT", data=data)

    if result.get("ok") and "data" in result:
        form = result["data"]
        return {
            "ok": True,
            "result": {
                "id": form.get("id"),
                "title": form.get("title"),
                "last_updated_at": form.get("last_updated_at"),
                "_links": form.get("_links", {})
            }
        }
    return result


def delete_form(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a form.

    Params:
        form_id (str): The form ID (required)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    form_id = params.get("form_id", "")
    if not form_id:
        return {"ok": False, "error": "form_id is required"}

    endpoint = f"/forms/{form_id}"
    result = _api_call(token, endpoint, method="DELETE")

    if result.get("ok"):
        return {
            "ok": True,
            "result": {
                "deleted": True,
                "form_id": form_id
            }
        }
    return result


# =============================================================================
# Responses Actions
# =============================================================================

def list_responses(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List responses for a form.

    Params:
        form_id (str): The form ID (required)
        page_size (int): Number of responses per page (default: 25, max: 1000)
        since (str): Filter responses after this ISO 8601 datetime (optional)
        until (str): Filter responses before this ISO 8601 datetime (optional)
        after (str): Response token to paginate from (optional)
        before (str): Response token to paginate to (optional)
        included_response_ids (str): Comma-separated response IDs to include (optional)
        completed (bool): Filter by completion status (optional)
        sort (str): Sort order - 'submitted_at,asc' or 'submitted_at,desc' (optional)
        query (str): Filter by answer content (optional)
        fields (list): List of field IDs to include (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    form_id = params.get("form_id", "")
    if not form_id:
        return {"ok": False, "error": "form_id is required"}

    query_params = {}

    page_size = params.get("page_size", 25)
    query_params["page_size"] = min(page_size, 1000)

    if params.get("since"):
        query_params["since"] = params["since"]

    if params.get("until"):
        query_params["until"] = params["until"]

    if params.get("after"):
        query_params["after"] = params["after"]

    if params.get("before"):
        query_params["before"] = params["before"]

    if params.get("included_response_ids"):
        query_params["included_response_ids"] = params["included_response_ids"]

    if params.get("completed") is not None:
        query_params["completed"] = str(params["completed"]).lower()

    if params.get("sort"):
        query_params["sort"] = params["sort"]

    if params.get("query"):
        query_params["query"] = params["query"]

    if params.get("fields"):
        query_params["fields"] = ",".join(params["fields"])

    endpoint = f"/forms/{form_id}/responses"
    if query_params:
        endpoint += f"?{urlencode(query_params)}"

    result = _api_call(token, endpoint)

    if result.get("ok") and "data" in result:
        data = result["data"]
        responses = data.get("items", [])
        return {
            "ok": True,
            "result": {
                "responses": [
                    {
                        "response_id": r.get("response_id"),
                        "landed_at": r.get("landed_at"),
                        "submitted_at": r.get("submitted_at"),
                        "metadata": r.get("metadata", {}),
                        "answers": r.get("answers", []),
                        "hidden": r.get("hidden", {}),
                        "calculated": r.get("calculated", {}),
                        "variables": r.get("variables", [])
                    }
                    for r in responses
                ],
                "total_items": data.get("total_items", len(responses)),
                "page_count": data.get("page_count", 1)
            }
        }
    return result


def get_response(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a single response by ID.

    Params:
        form_id (str): The form ID (required)
        response_id (str): The response ID (required)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    form_id = params.get("form_id", "")
    response_id = params.get("response_id", "")

    if not form_id:
        return {"ok": False, "error": "form_id is required"}
    if not response_id:
        return {"ok": False, "error": "response_id is required"}

    # Typeform API doesn't have a direct single response endpoint
    # Use included_response_ids filter to get specific response
    endpoint = f"/forms/{form_id}/responses?included_response_ids={response_id}"
    result = _api_call(token, endpoint)

    if result.get("ok") and "data" in result:
        data = result["data"]
        responses = data.get("items", [])
        if not responses:
            return {"ok": False, "error": f"Response not found: {response_id}"}

        r = responses[0]
        return {
            "ok": True,
            "result": {
                "response_id": r.get("response_id"),
                "landed_at": r.get("landed_at"),
                "submitted_at": r.get("submitted_at"),
                "metadata": r.get("metadata", {}),
                "answers": r.get("answers", []),
                "hidden": r.get("hidden", {}),
                "calculated": r.get("calculated", {}),
                "variables": r.get("variables", [])
            }
        }
    return result


# =============================================================================
# Insights Actions
# =============================================================================

def get_form_insights(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get analytics/insights for a form.

    Params:
        form_id (str): The form ID (required)

    Returns:
        Summary statistics including views, submissions, completion rate, etc.
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)

    form_id = params.get("form_id", "")
    if not form_id:
        return {"ok": False, "error": "form_id is required"}

    endpoint = f"/insights/{form_id}/summary"
    result = _api_call(token, endpoint)

    if result.get("ok") and "data" in result:
        data = result["data"]
        return {
            "ok": True,
            "result": {
                "form_id": form_id,
                "total_visits": data.get("total_visits", 0),
                "unique_visits": data.get("unique_visits", 0),
                "submissions": data.get("submissions", 0),
                "completion_rate": data.get("completion_rate", 0),
                "average_time": data.get("average_time", 0),
                "responses_today": data.get("responses_today", 0),
                "responses_last_7_days": data.get("responses_last_7_days", 0),
                "responses_last_30_days": data.get("responses_last_30_days", 0)
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_forms": list_forms,
    "get_form": get_form,
    "create_form": create_form,
    "update_form": update_form,
    "delete_form": delete_form,
    "list_responses": list_responses,
    "get_response": get_response,
    "get_form_insights": get_form_insights,
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
        return {"ok": False, "error": f"Unknown action '{action}'. Available: {list(ACTIONS.keys())}"}

    try:
        logger.info(f"Executing typeform.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
