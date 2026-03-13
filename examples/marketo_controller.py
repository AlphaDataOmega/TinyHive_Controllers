"""Marketo Controller for TinyHive

A controller for Marketo REST API integration supporting lead management,
campaigns, programs, lists, and custom activities using OAuth 2.0 client credentials.

Method IDs:
  controller.marketo.{profile}.get_leads
  controller.marketo.{profile}.create_lead
  controller.marketo.{profile}.sync_leads
  controller.marketo.{profile}.add_to_list
  controller.marketo.{profile}.list_programs
  controller.marketo.{profile}.get_campaigns
  controller.marketo.{profile}.request_campaign
  controller.marketo.{profile}.create_activity

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Example profile:
{
    "munchkin_id": "123-ABC-456",
    "client_id_env": "MARKETO_CLIENT_ID",
    "client_secret_env": "MARKETO_CLIENT_SECRET"
}

Environment Variables:
- MARKETO_CLIENT_ID: Your Marketo REST API client ID
- MARKETO_CLIENT_SECRET: Your Marketo REST API client secret

API Endpoints:
- Base URL: https://{munchkin_id}.mktorest.com/rest/v1
- Identity URL: https://{munchkin_id}.mktorest.com/identity/oauth/token

Dependencies:
- None (standard library only)
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.marketo")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Token cache: profile_name -> (token, expiry_timestamp)
_token_cache: Dict[str, Tuple[str, float]] = {}

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile from the profiles directory."""
    profile_path = PROFILES_DIR / f"{name}.json"
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {name}. Create {profile_path} with Marketo configuration.")

    with open(profile_path) as f:
        return json.load(f)


def _get_munchkin_id(profile: Dict[str, Any]) -> str:
    """Get the Marketo Munchkin ID from profile."""
    munchkin_id = profile.get("munchkin_id")
    if not munchkin_id:
        raise ValueError("Profile missing required 'munchkin_id' field (e.g., '123-ABC-456')")
    return munchkin_id


def _get_base_url(profile: Dict[str, Any]) -> str:
    """Get the Marketo REST API base URL."""
    munchkin_id = _get_munchkin_id(profile)
    return f"https://{munchkin_id}.mktorest.com/rest/v1"


def _get_identity_url(profile: Dict[str, Any]) -> str:
    """Get the Marketo identity URL for OAuth token requests."""
    munchkin_id = _get_munchkin_id(profile)
    return f"https://{munchkin_id}.mktorest.com/identity/oauth/token"


# =============================================================================
# OAuth 2.0 Authentication
# =============================================================================

def _get_access_token(profile: Dict[str, Any], profile_name: str) -> str:
    """
    Get OAuth 2.0 access token using client credentials grant.

    Marketo uses query parameters for client_id and client_secret.
    """
    # Check cache first
    if profile_name in _token_cache:
        token, expiry = _token_cache[profile_name]
        if time.time() < expiry:
            return token

    # Get credentials from environment
    client_id_env = profile.get("client_id_env", "MARKETO_CLIENT_ID")
    client_secret_env = profile.get("client_secret_env", "MARKETO_CLIENT_SECRET")

    client_id = os.environ.get(client_id_env)
    client_secret = os.environ.get(client_secret_env)

    if not client_id:
        raise ValueError(f"Missing environment variable: {client_id_env}")
    if not client_secret:
        raise ValueError(f"Missing environment variable: {client_secret_env}")

    # Build token URL with query parameters (Marketo style)
    identity_url = _get_identity_url(profile)
    token_params = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    token_url = f"{identity_url}?{urlencode(token_params)}"

    headers = {
        "Accept": "application/json",
    }

    try:
        req = Request(token_url, headers=headers, method="GET")
        with urlopen(req, timeout=30) as response:
            token_data = json.loads(response.read().decode("utf-8"))

        if "access_token" not in token_data:
            error_msg = token_data.get("error_description", token_data.get("error", "Unknown error"))
            raise ValueError(f"Failed to obtain access token: {error_msg}")

        access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        # Cache with 60 second buffer before expiry
        expiry = time.time() + expires_in - 60

        _token_cache[profile_name] = (access_token, expiry)
        logger.info(f"Obtained new Marketo access token for profile '{profile_name}'")
        return access_token

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"Failed to obtain access token: HTTP {e.code}: {error_body}")
    except URLError as e:
        raise ValueError(f"Failed to obtain access token: {e.reason}")


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    base_url: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    query_params: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Marketo API call."""
    url = f"{base_url}{endpoint}"

    if query_params:
        url = f"{url}?{urlencode(query_params)}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                result = json.loads(response_body)
                # Marketo returns success: true/false in the response
                if result.get("success") is False:
                    errors = result.get("errors", [])
                    error_msg = "; ".join(
                        f"{e.get('code', 'unknown')}: {e.get('message', 'Unknown error')}"
                        for e in errors
                    )
                    return {"ok": False, "error": error_msg}
                return {"ok": True, "result": result}
            return {"ok": True, "result": {"success": True}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            if "errors" in error_data:
                error_message = "; ".join(
                    f"{err.get('code', 'unknown')}: {err.get('message', 'Unknown')}"
                    for err in error_data["errors"]
                )
            else:
                error_message = error_data.get("error_description", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Marketo API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Marketo API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Lead Actions
# =============================================================================

def get_leads(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get leads by filter criteria.

    Params:
        filter_type (str): The field to filter by (required)
            Common values: 'email', 'id', 'cookie', 'twitterId', 'facebookId', 'linkedInId', 'sfdcAccountId', 'sfdcContactId', 'sfdcLeadId', 'sfdcLeadOwnerId', 'sfdcOpptyId'
        filter_values (list): List of values to filter by (required)
        fields (list): List of field names to return (optional)
        batch_size (int): Number of leads to return (optional, max 300)
        next_page_token (str): Token for pagination (optional)

    Returns:
        List of matching leads.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    filter_type = params.get("filter_type")
    if not filter_type:
        return {"ok": False, "error": "filter_type is required"}

    filter_values = params.get("filter_values")
    if not filter_values:
        return {"ok": False, "error": "filter_values is required"}

    # Build query parameters
    query_params: Dict[str, str] = {
        "filterType": filter_type,
        "filterValues": ",".join(str(v) for v in filter_values),
    }

    if params.get("fields"):
        query_params["fields"] = ",".join(params["fields"])

    if params.get("batch_size"):
        query_params["batchSize"] = str(min(params["batch_size"], 300))

    if params.get("next_page_token"):
        query_params["nextPageToken"] = params["next_page_token"]

    result = _api_call(token, base_url, "/leads.json", method="GET", query_params=query_params)

    if result.get("ok") and "result" in result:
        response = result["result"]
        return {
            "ok": True,
            "data": {
                "leads": response.get("result", []),
                "moreResult": response.get("moreResult", False),
                "nextPageToken": response.get("nextPageToken"),
            }
        }
    return result


def create_lead(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create or update a single lead.

    Params:
        email (str): Lead email address (required)
        fields (dict): Additional field values (optional)
            Example: {"firstName": "John", "lastName": "Doe", "company": "Acme"}
        lookup_field (str): Field to use for deduplication (default: 'email')

    Returns:
        Created/updated lead information.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    email = params.get("email")
    if not email:
        return {"ok": False, "error": "email is required"}

    # Build lead record
    lead_record: Dict[str, Any] = {"email": email}

    # Add additional fields
    if params.get("fields"):
        lead_record.update(params["fields"])

    lookup_field = params.get("lookup_field", "email")

    data = {
        "action": "createOrUpdate",
        "lookupField": lookup_field,
        "input": [lead_record],
    }

    result = _api_call(token, base_url, "/leads.json", method="POST", data=data)

    if result.get("ok") and "result" in result:
        response = result["result"]
        leads = response.get("result", [])
        if leads:
            lead = leads[0]
            return {
                "ok": True,
                "data": {
                    "id": lead.get("id"),
                    "status": lead.get("status"),
                    "reasons": lead.get("reasons", []),
                }
            }
        return {"ok": True, "data": {"message": "No lead returned"}}
    return result


def sync_leads(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sync multiple leads (create, update, or upsert).

    Params:
        leads (list): List of lead records to sync (required)
            Each lead is a dict with field names as keys
            Example: [{"email": "john@example.com", "firstName": "John"}, ...]
        action (str): Sync action (optional, default: 'createOrUpdate')
            Values: 'createOnly', 'updateOnly', 'createOrUpdate', 'createDuplicate'
        lookup_field (str): Field for deduplication (optional, default: 'email')
        async_processing (bool): Use async processing (optional, default: false)
        partition_name (str): Lead partition name (optional)

    Returns:
        Sync results for each lead.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    leads = params.get("leads")
    if not leads:
        return {"ok": False, "error": "leads is required"}

    if not isinstance(leads, list):
        return {"ok": False, "error": "leads must be a list"}

    action = params.get("action", "createOrUpdate")
    valid_actions = ["createOnly", "updateOnly", "createOrUpdate", "createDuplicate"]
    if action not in valid_actions:
        return {"ok": False, "error": f"Invalid action. Must be one of: {valid_actions}"}

    data: Dict[str, Any] = {
        "action": action,
        "lookupField": params.get("lookup_field", "email"),
        "input": leads,
    }

    if params.get("async_processing"):
        data["asyncProcessing"] = True

    if params.get("partition_name"):
        data["partitionName"] = params["partition_name"]

    result = _api_call(token, base_url, "/leads.json", method="POST", data=data)

    if result.get("ok") and "result" in result:
        response = result["result"]
        sync_results = []
        for lead in response.get("result", []):
            sync_results.append({
                "id": lead.get("id"),
                "status": lead.get("status"),
                "reasons": lead.get("reasons", []),
            })

        return {
            "ok": True,
            "data": {
                "results": sync_results,
                "requestId": response.get("requestId"),
            }
        }
    return result


# =============================================================================
# List Actions
# =============================================================================

def add_to_list(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add leads to a static list.

    Params:
        list_id (int/str): Static list ID (required)
        lead_ids (list): List of lead IDs to add (required)

    Returns:
        Results for each lead addition.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    list_id = params.get("list_id")
    if not list_id:
        return {"ok": False, "error": "list_id is required"}

    lead_ids = params.get("lead_ids")
    if not lead_ids:
        return {"ok": False, "error": "lead_ids is required"}

    if not isinstance(lead_ids, list):
        return {"ok": False, "error": "lead_ids must be a list"}

    # Build input array
    input_leads = [{"id": int(lid)} for lid in lead_ids]

    data = {"input": input_leads}

    result = _api_call(
        token, base_url, f"/lists/{list_id}/leads.json",
        method="POST", data=data
    )

    if result.get("ok") and "result" in result:
        response = result["result"]
        add_results = []
        for lead in response.get("result", []):
            add_results.append({
                "id": lead.get("id"),
                "status": lead.get("status"),
                "reasons": lead.get("reasons", []),
            })

        return {
            "ok": True,
            "data": {
                "results": add_results,
                "requestId": response.get("requestId"),
            }
        }
    return result


# =============================================================================
# Program Actions
# =============================================================================

def list_programs(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List programs with optional filtering.

    Params:
        filter_type (str): Filter type (optional)
            Values: 'id', 'name', 'type', 'workspace', 'updatedAt', 'tag'
        filter_values (list): Filter values corresponding to filter_type (optional)
        max_return (int): Maximum programs to return (optional, default: 200)
        offset (int): Offset for pagination (optional)
        earliest_updated_at (str): ISO 8601 datetime for filtering (optional)
        latest_updated_at (str): ISO 8601 datetime for filtering (optional)

    Returns:
        List of programs.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    query_params: Dict[str, str] = {}

    if params.get("filter_type") and params.get("filter_values"):
        query_params["filterType"] = params["filter_type"]
        query_params["filterValues"] = ",".join(str(v) for v in params["filter_values"])

    if params.get("max_return"):
        query_params["maxReturn"] = str(params["max_return"])

    if params.get("offset"):
        query_params["offset"] = str(params["offset"])

    if params.get("earliest_updated_at"):
        query_params["earliestUpdatedAt"] = params["earliest_updated_at"]

    if params.get("latest_updated_at"):
        query_params["latestUpdatedAt"] = params["latest_updated_at"]

    result = _api_call(
        token, base_url, "/programs.json",
        method="GET", query_params=query_params if query_params else None
    )

    if result.get("ok") and "result" in result:
        response = result["result"]
        programs = []
        for program in response.get("result", []):
            programs.append({
                "id": program.get("id"),
                "name": program.get("name"),
                "description": program.get("description"),
                "type": program.get("type"),
                "channel": program.get("channel"),
                "status": program.get("status"),
                "workspace": program.get("workspace"),
                "createdAt": program.get("createdAt"),
                "updatedAt": program.get("updatedAt"),
                "folder": program.get("folder"),
                "tags": program.get("tags", []),
            })

        return {
            "ok": True,
            "data": {
                "programs": programs,
                "moreResult": response.get("moreResult", False),
            }
        }
    return result


# =============================================================================
# Campaign Actions
# =============================================================================

def get_campaigns(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get smart campaigns.

    Params:
        id (list): List of campaign IDs to retrieve (optional)
        name (list): List of campaign names to search for (optional)
        program_name (str): Filter by program name (optional)
        workspace_name (str): Filter by workspace name (optional)
        batch_size (int): Number of campaigns to return (optional, max 300)
        next_page_token (str): Token for pagination (optional)
        is_triggerable (bool): Filter by triggerable status (optional)

    Returns:
        List of smart campaigns.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    query_params: Dict[str, str] = {}

    if params.get("id"):
        query_params["id"] = ",".join(str(i) for i in params["id"])

    if params.get("name"):
        query_params["name"] = ",".join(params["name"])

    if params.get("program_name"):
        query_params["programName"] = params["program_name"]

    if params.get("workspace_name"):
        query_params["workspaceName"] = params["workspace_name"]

    if params.get("batch_size"):
        query_params["batchSize"] = str(min(params["batch_size"], 300))

    if params.get("next_page_token"):
        query_params["nextPageToken"] = params["next_page_token"]

    if params.get("is_triggerable") is not None:
        query_params["isTriggerable"] = str(params["is_triggerable"]).lower()

    result = _api_call(
        token, base_url, "/campaigns.json",
        method="GET", query_params=query_params if query_params else None
    )

    if result.get("ok") and "result" in result:
        response = result["result"]
        campaigns = []
        for campaign in response.get("result", []):
            campaigns.append({
                "id": campaign.get("id"),
                "name": campaign.get("name"),
                "description": campaign.get("description"),
                "type": campaign.get("type"),
                "programId": campaign.get("programId"),
                "programName": campaign.get("programName"),
                "workspaceName": campaign.get("workspaceName"),
                "active": campaign.get("active"),
                "createdAt": campaign.get("createdAt"),
                "updatedAt": campaign.get("updatedAt"),
            })

        return {
            "ok": True,
            "data": {
                "campaigns": campaigns,
                "moreResult": response.get("moreResult", False),
                "nextPageToken": response.get("nextPageToken"),
            }
        }
    return result


def request_campaign(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trigger a smart campaign for specific leads.

    Params:
        campaign_id (int/str): Smart campaign ID (required)
        lead_ids (list): List of lead IDs to trigger campaign for (required)
        tokens (list): List of my tokens to pass to campaign (optional)
            Each token: {"name": "{{my.tokenName}}", "value": "tokenValue"}

    Returns:
        Request status.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    campaign_id = params.get("campaign_id")
    if not campaign_id:
        return {"ok": False, "error": "campaign_id is required"}

    lead_ids = params.get("lead_ids")
    if not lead_ids:
        return {"ok": False, "error": "lead_ids is required"}

    if not isinstance(lead_ids, list):
        return {"ok": False, "error": "lead_ids must be a list"}

    data: Dict[str, Any] = {
        "input": {
            "leads": [{"id": int(lid)} for lid in lead_ids],
        }
    }

    if params.get("tokens"):
        data["input"]["tokens"] = params["tokens"]

    result = _api_call(
        token, base_url, f"/campaigns/{campaign_id}/trigger.json",
        method="POST", data=data
    )

    if result.get("ok") and "result" in result:
        response = result["result"]
        return {
            "ok": True,
            "data": {
                "success": response.get("success", True),
                "requestId": response.get("requestId"),
                "result": response.get("result", []),
            }
        }
    return result


# =============================================================================
# Custom Activity Actions
# =============================================================================

def create_activity(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a custom activity for a lead.

    Params:
        lead_id (int/str): Lead ID to associate activity with (required)
        activity_type_id (int/str): Custom activity type ID (required)
        primary_attribute_value (str): Primary attribute value (required)
        attributes (list): List of activity attributes (optional)
            Each attribute: {"name": "attrName", "value": "attrValue"}
        activity_date (str): ISO 8601 datetime for the activity (optional)

    Returns:
        Created activity information.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    lead_id = params.get("lead_id")
    if not lead_id:
        return {"ok": False, "error": "lead_id is required"}

    activity_type_id = params.get("activity_type_id")
    if not activity_type_id:
        return {"ok": False, "error": "activity_type_id is required"}

    primary_attribute_value = params.get("primary_attribute_value")
    if not primary_attribute_value:
        return {"ok": False, "error": "primary_attribute_value is required"}

    # Build activity record
    activity_record: Dict[str, Any] = {
        "leadId": int(lead_id),
        "activityTypeId": int(activity_type_id),
        "primaryAttributeValue": primary_attribute_value,
    }

    if params.get("activity_date"):
        activity_record["activityDate"] = params["activity_date"]

    if params.get("attributes"):
        activity_record["attributes"] = params["attributes"]

    data = {"input": [activity_record]}

    result = _api_call(
        token, base_url, "/activities/external.json",
        method="POST", data=data
    )

    if result.get("ok") and "result" in result:
        response = result["result"]
        activities = response.get("result", [])
        if activities:
            activity = activities[0]
            return {
                "ok": True,
                "data": {
                    "id": activity.get("id"),
                    "status": activity.get("status"),
                    "marketoGUID": activity.get("marketoGUID"),
                    "reasons": activity.get("reasons", []),
                }
            }
        return {
            "ok": True,
            "data": {
                "success": True,
                "requestId": response.get("requestId"),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "get_leads": get_leads,
    "create_lead": create_lead,
    "sync_leads": sync_leads,
    "add_to_list": add_to_list,
    "list_programs": list_programs,
    "get_campaigns": get_campaigns,
    "request_campaign": request_campaign,
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
        return {"ok": False, "error": f"Unknown action '{action}'. Available: {list(ACTIONS.keys())}"}

    try:
        logger.info(f"Executing marketo.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
