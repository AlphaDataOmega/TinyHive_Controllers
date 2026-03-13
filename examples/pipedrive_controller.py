"""
Pipedrive Controller for TinyHive

A controller for interacting with the Pipedrive CRM API.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "company_domain": "yourcompany",
    "token_env": "PIPEDRIVE_API_TOKEN"
}

Required Permissions:
--------------------
- API token must have appropriate scopes for the actions being performed
- Deals: Read/Write access to deals
- Persons: Read/Write access to contacts
- Activities: Read/Write access to activities

Dependencies:
------------
None (standard library only)

Method IDs:
-----------
  controller.pipedrive.{profile}.list_deals
  controller.pipedrive.{profile}.get_deal
  controller.pipedrive.{profile}.create_deal
  controller.pipedrive.{profile}.update_deal
  controller.pipedrive.{profile}.list_persons
  controller.pipedrive.{profile}.create_person
  controller.pipedrive.{profile}.list_activities
  controller.pipedrive.{profile}.create_activity
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.pipedrive")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

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


def list_profiles() -> List[str]:
    """List available Pipedrive profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    profile: Dict[str, Any],
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    query_params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated Pipedrive API call.

    Args:
        profile: Profile configuration dict
        endpoint: API endpoint (e.g., "/deals", "/persons/123")
        method: HTTP method
        data: JSON body for POST/PUT requests
        query_params: Additional query parameters
        timeout: Request timeout in seconds

    Returns:
        Dict with "ok", "data"/"result", and "error" keys
    """
    company_domain = profile.get("company_domain")
    if not company_domain:
        return {"ok": False, "error": "company_domain not configured in profile"}

    token_env = profile.get("token_env", "PIPEDRIVE_API_TOKEN")
    api_token = os.environ.get(token_env)
    if not api_token:
        return {"ok": False, "error": f"API token not found in environment variable '{token_env}'"}

    # Build URL with API token
    base_url = f"https://{company_domain}.pipedrive.com/api/v1"
    url = f"{base_url}{endpoint}"

    # Add API token to query params
    params = {"api_token": api_token}
    if query_params:
        params.update(query_params)

    url_with_params = f"{url}?{urlencode(params)}"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url_with_params, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                result = json.loads(response_body)
                if result.get("success"):
                    return {"ok": True, "data": result.get("data"), "additional_data": result.get("additional_data")}
                else:
                    return {"ok": False, "error": result.get("error", "Unknown error")}
            return {"ok": True, "data": None}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("error", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Pipedrive API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Pipedrive API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Deal Actions
# =============================================================================

def list_deals(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List deals from Pipedrive.

    Params:
        status (str): Filter by deal status ('open', 'won', 'lost', 'deleted', 'all_not_deleted')
        filter_id (int): ID of the filter to use
        start (int): Pagination start (default: 0)
        limit (int): Number of deals to fetch (default: 100, max: 500)
    """
    profile = load_profile(profile_name)

    query_params = {}
    if params.get("status"):
        query_params["status"] = params["status"]
    if params.get("filter_id"):
        query_params["filter_id"] = params["filter_id"]
    if params.get("start") is not None:
        query_params["start"] = params["start"]
    if params.get("limit"):
        query_params["limit"] = min(params["limit"], 500)

    return _api_call(profile, "/deals", query_params=query_params)


def get_deal(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a specific deal by ID.

    Params:
        deal_id (int): The ID of the deal to retrieve (required)
    """
    profile = load_profile(profile_name)

    deal_id = params.get("deal_id")
    if not deal_id:
        return {"ok": False, "error": "deal_id is required"}

    return _api_call(profile, f"/deals/{deal_id}")


def create_deal(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new deal in Pipedrive.

    Params:
        title (str): Deal title (required)
        value (float): Deal value
        currency (str): Currency code (e.g., 'USD', 'EUR')
        person_id (int): ID of the person this deal is associated with
        org_id (int): ID of the organization this deal is associated with
        pipeline_id (int): ID of the pipeline this deal belongs to
        stage_id (int): ID of the stage this deal is in
    """
    profile = load_profile(profile_name)

    title = params.get("title")
    if not title:
        return {"ok": False, "error": "title is required"}

    data = {"title": title}

    if params.get("value") is not None:
        data["value"] = params["value"]
    if params.get("currency"):
        data["currency"] = params["currency"]
    if params.get("person_id"):
        data["person_id"] = params["person_id"]
    if params.get("org_id"):
        data["org_id"] = params["org_id"]
    if params.get("pipeline_id"):
        data["pipeline_id"] = params["pipeline_id"]
    if params.get("stage_id"):
        data["stage_id"] = params["stage_id"]

    return _api_call(profile, "/deals", method="POST", data=data)


def update_deal(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing deal.

    Params:
        deal_id (int): The ID of the deal to update (required)
        fields (dict): Fields to update (title, value, currency, status, stage_id, etc.)
    """
    profile = load_profile(profile_name)

    deal_id = params.get("deal_id")
    if not deal_id:
        return {"ok": False, "error": "deal_id is required"}

    fields = params.get("fields", {})
    if not fields:
        return {"ok": False, "error": "fields is required"}

    return _api_call(profile, f"/deals/{deal_id}", method="PUT", data=fields)


# =============================================================================
# Person Actions
# =============================================================================

def list_persons(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List persons (contacts) from Pipedrive.

    Params:
        filter_id (int): ID of the filter to use
        start (int): Pagination start (default: 0)
        limit (int): Number of persons to fetch (default: 100, max: 500)
    """
    profile = load_profile(profile_name)

    query_params = {}
    if params.get("filter_id"):
        query_params["filter_id"] = params["filter_id"]
    if params.get("start") is not None:
        query_params["start"] = params["start"]
    if params.get("limit"):
        query_params["limit"] = min(params["limit"], 500)

    return _api_call(profile, "/persons", query_params=query_params)


def create_person(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new person (contact) in Pipedrive.

    Params:
        name (str): Person's name (required)
        email (str or list): Email address(es)
        phone (str or list): Phone number(s)
        org_id (int): ID of the organization this person belongs to
    """
    profile = load_profile(profile_name)

    name = params.get("name")
    if not name:
        return {"ok": False, "error": "name is required"}

    data = {"name": name}

    # Handle email - can be string or list
    email = params.get("email")
    if email:
        if isinstance(email, str):
            data["email"] = [{"value": email, "primary": True, "label": "work"}]
        elif isinstance(email, list):
            data["email"] = [{"value": e, "primary": i == 0, "label": "work"} for i, e in enumerate(email)]

    # Handle phone - can be string or list
    phone = params.get("phone")
    if phone:
        if isinstance(phone, str):
            data["phone"] = [{"value": phone, "primary": True, "label": "work"}]
        elif isinstance(phone, list):
            data["phone"] = [{"value": p, "primary": i == 0, "label": "work"} for i, p in enumerate(phone)]

    if params.get("org_id"):
        data["org_id"] = params["org_id"]

    return _api_call(profile, "/persons", method="POST", data=data)


# =============================================================================
# Activity Actions
# =============================================================================

def list_activities(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List activities from Pipedrive.

    Params:
        type (str): Activity type (e.g., 'call', 'meeting', 'task', 'email')
        filter_id (int): ID of the filter to use
        start_date (str): Start date in YYYY-MM-DD format
        end_date (str): End date in YYYY-MM-DD format
        start (int): Pagination start (default: 0)
        limit (int): Number of activities to fetch (default: 100, max: 500)
    """
    profile = load_profile(profile_name)

    query_params = {}
    if params.get("type"):
        query_params["type"] = params["type"]
    if params.get("filter_id"):
        query_params["filter_id"] = params["filter_id"]
    if params.get("start_date"):
        query_params["start_date"] = params["start_date"]
    if params.get("end_date"):
        query_params["end_date"] = params["end_date"]
    if params.get("start") is not None:
        query_params["start"] = params["start"]
    if params.get("limit"):
        query_params["limit"] = min(params["limit"], 500)

    return _api_call(profile, "/activities", query_params=query_params)


def create_activity(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new activity in Pipedrive.

    Params:
        subject (str): Activity subject/title (required)
        type (str): Activity type (e.g., 'call', 'meeting', 'task', 'email') (required)
        deal_id (int): ID of the deal this activity is linked to
        person_id (int): ID of the person this activity is linked to
        due_date (str): Due date in YYYY-MM-DD format
        due_time (str): Due time in HH:MM format
        duration (str): Duration in HH:MM format
        note (str): Activity note/description
    """
    profile = load_profile(profile_name)

    subject = params.get("subject")
    if not subject:
        return {"ok": False, "error": "subject is required"}

    activity_type = params.get("type")
    if not activity_type:
        return {"ok": False, "error": "type is required"}

    data = {
        "subject": subject,
        "type": activity_type,
    }

    if params.get("deal_id"):
        data["deal_id"] = params["deal_id"]
    if params.get("person_id"):
        data["person_id"] = params["person_id"]
    if params.get("due_date"):
        data["due_date"] = params["due_date"]
    if params.get("due_time"):
        data["due_time"] = params["due_time"]
    if params.get("duration"):
        data["duration"] = params["duration"]
    if params.get("note"):
        data["note"] = params["note"]

    return _api_call(profile, "/activities", method="POST", data=data)


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_deals": list_deals,
    "get_deal": get_deal,
    "create_deal": create_deal,
    "update_deal": update_deal,
    "list_persons": list_persons,
    "create_person": create_person,
    "list_activities": list_activities,
    "create_activity": create_activity,
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
        logger.info(f"Executing pipedrive.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
