"""
ServiceNow Controller for TinyHive

A controller for interacting with ServiceNow REST APIs, supporting incident
management, user lookups, CMDB queries, change requests, and Flow Designer.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "instance": "yourinstance.service-now.com",
    "username_env": "SERVICENOW_USERNAME",
    "password_env": "SERVICENOW_PASSWORD",
    "timeout": 30
}

Required Permissions:
--------------------
- Incidents: itil role or equivalent
- Users: user_admin or read access to sys_user
- CMDB: itil role or cmdb_read
- Change Requests: itil role or change_manager
- Flow Designer: flow_designer role or specific flow permissions

Method IDs:
----------
  controller.servicenow.{profile}.list_incidents
  controller.servicenow.{profile}.get_incident
  controller.servicenow.{profile}.create_incident
  controller.servicenow.{profile}.update_incident
  controller.servicenow.{profile}.list_users
  controller.servicenow.{profile}.list_cmdb_items
  controller.servicenow.{profile}.create_change_request
  controller.servicenow.{profile}.execute_flow

Dependencies:
------------
- None (standard library only)
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.servicenow")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

DEFAULT_TIMEOUT = 30


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile from the profiles directory."""
    profile_path = PROFILES_DIR / f"{name}.json"
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {name}. Create {profile_path} with ServiceNow configuration.")

    with open(profile_path) as f:
        return json.load(f)


def list_profiles() -> List[str]:
    """List available ServiceNow profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# Authentication
# =============================================================================

def _get_auth_header(profile: Dict[str, Any]) -> str:
    """Get Basic Auth header from profile credentials."""
    username_env = profile.get("username_env", "SERVICENOW_USERNAME")
    password_env = profile.get("password_env", "SERVICENOW_PASSWORD")

    username = os.environ.get(username_env)
    password = os.environ.get(password_env)

    if not username or not password:
        raise ValueError(
            f"Missing credentials. Set environment variables: {username_env} and {password_env}"
        )

    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    profile: Dict[str, Any],
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    query_params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Make an authenticated ServiceNow REST API call.

    Args:
        profile: Profile configuration dict
        endpoint: API endpoint path (e.g., "/api/now/table/incident")
        method: HTTP method (GET, POST, PUT, PATCH, DELETE)
        data: Request body data (will be JSON-encoded)
        query_params: Query string parameters

    Returns:
        Dict with "ok" status and "result" or "error"
    """
    instance = profile.get("instance", "")
    if not instance:
        return {"ok": False, "error": "Instance not configured in profile"}

    # Build URL
    base_url = f"https://{instance}"
    url = f"{base_url}{endpoint}"

    if query_params:
        # Filter out None values
        filtered_params = {k: v for k, v in query_params.items() if v is not None}
        if filtered_params:
            url += "?" + urlencode(filtered_params)

    # Prepare headers
    headers = {
        "Authorization": _get_auth_header(profile),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Prepare body
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {"status": "success"}}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("error", {}).get("message", error_body[:500])
            error_detail = error_data.get("error", {}).get("detail", "")
            if error_detail:
                error_message = f"{error_message}: {error_detail}"
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("ServiceNow API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}

    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}

    except Exception as e:
        logger.exception("Unexpected error in ServiceNow API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Incident Actions
# =============================================================================

def list_incidents(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List incidents from ServiceNow.

    Params:
        sysparm_query (str): Encoded query string (e.g., "active=true^priority=1")
        sysparm_limit (int): Maximum records to return (default: 100)
        sysparm_offset (int): Record offset for pagination (optional)
        sysparm_fields (str): Comma-separated fields to return (optional)
        sysparm_display_value (str): Return display values: "true", "false", "all" (optional)
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    query_params = {
        "sysparm_query": params.get("sysparm_query"),
        "sysparm_limit": params.get("sysparm_limit", 100),
        "sysparm_offset": params.get("sysparm_offset"),
        "sysparm_fields": params.get("sysparm_fields"),
        "sysparm_display_value": params.get("sysparm_display_value"),
    }

    result = _api_call(profile, "/api/now/table/incident", "GET", query_params=query_params)

    if result.get("ok") and "result" in result:
        incidents = result["result"].get("result", [])
        return {
            "ok": True,
            "data": {
                "incidents": incidents,
                "count": len(incidents)
            }
        }
    return result


def get_incident(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a specific incident by sys_id.

    Params:
        sys_id (str): Incident sys_id (required)
        sysparm_fields (str): Comma-separated fields to return (optional)
        sysparm_display_value (str): Return display values: "true", "false", "all" (optional)
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    sys_id = params.get("sys_id")
    if not sys_id:
        return {"ok": False, "error": "sys_id is required"}

    query_params = {
        "sysparm_fields": params.get("sysparm_fields"),
        "sysparm_display_value": params.get("sysparm_display_value"),
    }

    endpoint = f"/api/now/table/incident/{quote(sys_id, safe='')}"
    result = _api_call(profile, endpoint, "GET", query_params=query_params)

    if result.get("ok") and "result" in result:
        incident = result["result"].get("result", {})
        return {"ok": True, "data": {"incident": incident}}
    return result


def create_incident(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new incident.

    Params:
        short_description (str): Brief description of the incident (required)
        description (str): Detailed description (optional)
        urgency (int): Urgency level 1-3, where 1=High (optional)
        impact (int): Impact level 1-3, where 1=High (optional)
        assignment_group (str): Assignment group sys_id or name (optional)
        caller_id (str): Caller user sys_id (optional)
        category (str): Incident category (optional)
        subcategory (str): Incident subcategory (optional)
        contact_type (str): Contact type (optional)
        state (int): Incident state (optional)
        additional_fields (dict): Any additional fields to set (optional)
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    short_description = params.get("short_description")
    if not short_description:
        return {"ok": False, "error": "short_description is required"}

    # Build incident data
    incident_data = {
        "short_description": short_description,
    }

    # Add optional fields
    optional_fields = [
        "description", "urgency", "impact", "assignment_group",
        "caller_id", "category", "subcategory", "contact_type", "state"
    ]
    for field in optional_fields:
        if params.get(field) is not None:
            incident_data[field] = params[field]

    # Merge additional fields if provided
    additional_fields = params.get("additional_fields", {})
    if additional_fields and isinstance(additional_fields, dict):
        incident_data.update(additional_fields)

    result = _api_call(profile, "/api/now/table/incident", "POST", data=incident_data)

    if result.get("ok") and "result" in result:
        incident = result["result"].get("result", {})
        return {
            "ok": True,
            "data": {
                "incident": incident,
                "sys_id": incident.get("sys_id"),
                "number": incident.get("number")
            }
        }
    return result


def update_incident(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing incident.

    Params:
        sys_id (str): Incident sys_id (required)
        fields (dict): Fields to update (required)
            Example: {"state": 2, "work_notes": "Working on this"}
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    sys_id = params.get("sys_id")
    if not sys_id:
        return {"ok": False, "error": "sys_id is required"}

    fields = params.get("fields")
    if not fields or not isinstance(fields, dict):
        return {"ok": False, "error": "fields dict is required"}

    endpoint = f"/api/now/table/incident/{quote(sys_id, safe='')}"
    result = _api_call(profile, endpoint, "PATCH", data=fields)

    if result.get("ok") and "result" in result:
        incident = result["result"].get("result", {})
        return {
            "ok": True,
            "data": {
                "incident": incident,
                "sys_id": incident.get("sys_id"),
                "number": incident.get("number")
            }
        }
    return result


# =============================================================================
# User Actions
# =============================================================================

def list_users(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List users from ServiceNow.

    Params:
        sysparm_query (str): Encoded query string (e.g., "active=true^emailLIKE@example.com")
        sysparm_limit (int): Maximum records to return (default: 100)
        sysparm_offset (int): Record offset for pagination (optional)
        sysparm_fields (str): Comma-separated fields to return (optional)
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    query_params = {
        "sysparm_query": params.get("sysparm_query"),
        "sysparm_limit": params.get("sysparm_limit", 100),
        "sysparm_offset": params.get("sysparm_offset"),
        "sysparm_fields": params.get("sysparm_fields"),
    }

    result = _api_call(profile, "/api/now/table/sys_user", "GET", query_params=query_params)

    if result.get("ok") and "result" in result:
        users = result["result"].get("result", [])
        return {
            "ok": True,
            "data": {
                "users": users,
                "count": len(users)
            }
        }
    return result


# =============================================================================
# CMDB Actions
# =============================================================================

def list_cmdb_items(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List CMDB Configuration Items.

    Params:
        table (str): CMDB table name (default: cmdb_ci)
            Common tables: cmdb_ci, cmdb_ci_server, cmdb_ci_computer,
            cmdb_ci_database, cmdb_ci_app_server, cmdb_ci_service
        sysparm_query (str): Encoded query string (optional)
        sysparm_limit (int): Maximum records to return (default: 100)
        sysparm_offset (int): Record offset for pagination (optional)
        sysparm_fields (str): Comma-separated fields to return (optional)
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    table = params.get("table", "cmdb_ci")

    query_params = {
        "sysparm_query": params.get("sysparm_query"),
        "sysparm_limit": params.get("sysparm_limit", 100),
        "sysparm_offset": params.get("sysparm_offset"),
        "sysparm_fields": params.get("sysparm_fields"),
    }

    endpoint = f"/api/now/table/{quote(table, safe='')}"
    result = _api_call(profile, endpoint, "GET", query_params=query_params)

    if result.get("ok") and "result" in result:
        items = result["result"].get("result", [])
        return {
            "ok": True,
            "data": {
                "items": items,
                "count": len(items),
                "table": table
            }
        }
    return result


# =============================================================================
# Change Request Actions
# =============================================================================

def create_change_request(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new change request.

    Params:
        short_description (str): Brief description of the change (required)
        description (str): Detailed description (optional)
        type (str): Change type - "normal", "standard", "emergency" (default: normal)
        category (str): Change category (optional)
        priority (int): Priority 1-5 (optional)
        risk (int): Risk level 1-4 (optional)
        impact (int): Impact level 1-3 (optional)
        assignment_group (str): Assignment group sys_id or name (optional)
        assigned_to (str): Assigned user sys_id (optional)
        start_date (str): Planned start date in ISO format (optional)
        end_date (str): Planned end date in ISO format (optional)
        additional_fields (dict): Any additional fields to set (optional)
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    short_description = params.get("short_description")
    if not short_description:
        return {"ok": False, "error": "short_description is required"}

    # Map type string to ServiceNow values
    change_type = params.get("type", "normal").lower()
    type_mapping = {
        "normal": "normal",
        "standard": "standard",
        "emergency": "emergency"
    }
    sn_type = type_mapping.get(change_type, "normal")

    # Build change request data
    change_data = {
        "short_description": short_description,
        "type": sn_type,
    }

    # Add optional fields
    optional_fields = [
        "description", "category", "priority", "risk", "impact",
        "assignment_group", "assigned_to", "start_date", "end_date"
    ]
    for field in optional_fields:
        if params.get(field) is not None:
            change_data[field] = params[field]

    # Merge additional fields if provided
    additional_fields = params.get("additional_fields", {})
    if additional_fields and isinstance(additional_fields, dict):
        change_data.update(additional_fields)

    result = _api_call(profile, "/api/now/table/change_request", "POST", data=change_data)

    if result.get("ok") and "result" in result:
        change = result["result"].get("result", {})
        return {
            "ok": True,
            "data": {
                "change_request": change,
                "sys_id": change.get("sys_id"),
                "number": change.get("number")
            }
        }
    return result


# =============================================================================
# Flow Designer Actions
# =============================================================================

def execute_flow(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trigger a Flow Designer flow.

    Params:
        flow_sys_id (str): The sys_id of the flow to execute (required)
        inputs (dict): Input values for the flow (optional)
            Keys should match the flow's input variable names

    Note:
        The flow must be published and active. The user must have
        permission to execute the flow.

    Returns:
        Flow execution context ID and status
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    flow_sys_id = params.get("flow_sys_id")
    if not flow_sys_id:
        return {"ok": False, "error": "flow_sys_id is required"}

    inputs = params.get("inputs", {})

    # Flow Designer REST API endpoint
    endpoint = f"/api/sn_flow/execute/flow/{quote(flow_sys_id, safe='')}"

    # Build request body with inputs
    request_data = {}
    if inputs and isinstance(inputs, dict):
        request_data["inputs"] = inputs

    result = _api_call(profile, endpoint, "POST", data=request_data if request_data else None)

    if result.get("ok") and "result" in result:
        flow_result = result["result"]
        return {
            "ok": True,
            "data": {
                "execution_id": flow_result.get("sys_id") or flow_result.get("context_id"),
                "status": flow_result.get("status", "triggered"),
                "result": flow_result
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_incidents": list_incidents,
    "get_incident": get_incident,
    "create_incident": create_incident,
    "update_incident": update_incident,
    "list_users": list_users,
    "list_cmdb_items": list_cmdb_items,
    "create_change_request": create_change_request,
    "execute_flow": execute_flow,
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
        return {
            "ok": False,
            "error": f"Unknown action '{action}'. Available actions: {list(ACTIONS.keys())}"
        }

    try:
        logger.info(f"Executing servicenow.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
