"""HubSpot Controller for TinyHive

A controller for HubSpot CRM API integration supporting contacts, deals,
companies, pipelines, and engagements.

Method IDs:
  controller.hubspot.{profile}.create_contact
  controller.hubspot.{profile}.update_contact
  controller.hubspot.{profile}.get_contact
  controller.hubspot.{profile}.search_contacts
  controller.hubspot.{profile}.create_deal
  controller.hubspot.{profile}.create_company
  controller.hubspot.{profile}.list_pipelines
  controller.hubspot.{profile}.create_engagement

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "api_key_env": "HUBSPOT_API_KEY",
    "portal_id": "12345678"  // Optional, for some engagement types
}

Required Scopes:
---------------
- crm.objects.contacts.read
- crm.objects.contacts.write
- crm.objects.deals.read
- crm.objects.deals.write
- crm.objects.companies.read
- crm.objects.companies.write
- crm.schemas.deals.read (for pipelines)
- sales-email-read (for engagements)

Dependencies:
------------
None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.hubspot")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# HubSpot API base URL
HUBSPOT_API_BASE = "https://api.hubapi.com"

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
    """Get the HubSpot API key from environment variable."""
    env_var = profile.get("api_key_env", "HUBSPOT_API_KEY")
    api_key = os.environ.get(env_var)
    if not api_key:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return api_key


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    api_key: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated HubSpot API call."""
    url = f"{HUBSPOT_API_BASE}{endpoint}"

    headers = {
        "Authorization": f"Bearer {api_key}",
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
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("HubSpot API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in HubSpot API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Contact Actions
# =============================================================================

def create_contact(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new contact in HubSpot.

    Params:
        email (str): Contact email address (required)
        firstname (str): First name (optional)
        lastname (str): Last name (optional)
        phone (str): Phone number (optional)
        properties (dict): Additional properties to set (optional)

    Returns:
        Contact ID and properties on success.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    email = params.get("email")
    if not email:
        return {"ok": False, "error": "email is required"}

    # Build properties object
    properties = {
        "email": email,
    }

    if params.get("firstname"):
        properties["firstname"] = params["firstname"]
    if params.get("lastname"):
        properties["lastname"] = params["lastname"]
    if params.get("phone"):
        properties["phone"] = params["phone"]

    # Merge additional properties
    if params.get("properties"):
        properties.update(params["properties"])

    data = {"properties": properties}

    result = _api_call(api_key, "/crm/v3/objects/contacts", method="POST", data=data)

    if result.get("ok") and "result" in result:
        contact = result["result"]
        return {
            "ok": True,
            "data": {
                "id": contact.get("id"),
                "properties": contact.get("properties", {}),
                "createdAt": contact.get("createdAt"),
            }
        }
    return result


def update_contact(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing contact in HubSpot.

    Params:
        contact_id (str): HubSpot contact ID (required)
        properties (dict): Properties to update (required)

    Returns:
        Updated contact properties on success.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    contact_id = params.get("contact_id")
    if not contact_id:
        return {"ok": False, "error": "contact_id is required"}

    properties = params.get("properties")
    if not properties:
        return {"ok": False, "error": "properties is required"}

    data = {"properties": properties}

    result = _api_call(
        api_key,
        f"/crm/v3/objects/contacts/{contact_id}",
        method="PATCH",
        data=data
    )

    if result.get("ok") and "result" in result:
        contact = result["result"]
        return {
            "ok": True,
            "data": {
                "id": contact.get("id"),
                "properties": contact.get("properties", {}),
                "updatedAt": contact.get("updatedAt"),
            }
        }
    return result


def get_contact(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a contact by ID from HubSpot.

    Params:
        contact_id (str): HubSpot contact ID (required)
        properties (list): List of property names to return (optional)

    Returns:
        Contact details on success.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    contact_id = params.get("contact_id")
    if not contact_id:
        return {"ok": False, "error": "contact_id is required"}

    endpoint = f"/crm/v3/objects/contacts/{contact_id}"

    # Add properties query parameter if specified
    if params.get("properties"):
        props = ",".join(params["properties"])
        endpoint += f"?properties={props}"

    result = _api_call(api_key, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        contact = result["result"]
        return {
            "ok": True,
            "data": {
                "id": contact.get("id"),
                "properties": contact.get("properties", {}),
                "createdAt": contact.get("createdAt"),
                "updatedAt": contact.get("updatedAt"),
            }
        }
    return result


def search_contacts(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for contacts in HubSpot.

    Params:
        filters (list): List of filter objects (optional)
            Each filter: {"propertyName": str, "operator": str, "value": str}
            Operators: EQ, NEQ, LT, LTE, GT, GTE, CONTAINS_TOKEN, etc.
        sorts (list): List of sort objects (optional)
            Each sort: {"propertyName": str, "direction": "ASCENDING"|"DESCENDING"}
        limit (int): Maximum results to return (default: 10, max: 100)
        after (str): Pagination cursor (optional)
        properties (list): Properties to return (optional)

    Returns:
        List of matching contacts.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    data: Dict[str, Any] = {
        "limit": min(params.get("limit", 10), 100),
    }

    # Build filterGroups from filters
    if params.get("filters"):
        data["filterGroups"] = [{"filters": params["filters"]}]

    if params.get("sorts"):
        data["sorts"] = params["sorts"]

    if params.get("after"):
        data["after"] = params["after"]

    if params.get("properties"):
        data["properties"] = params["properties"]

    result = _api_call(api_key, "/crm/v3/objects/contacts/search", method="POST", data=data)

    if result.get("ok") and "result" in result:
        response = result["result"]
        contacts = []
        for contact in response.get("results", []):
            contacts.append({
                "id": contact.get("id"),
                "properties": contact.get("properties", {}),
            })

        return {
            "ok": True,
            "data": {
                "contacts": contacts,
                "total": response.get("total", len(contacts)),
                "paging": response.get("paging"),
            }
        }
    return result


# =============================================================================
# Deal Actions
# =============================================================================

def create_deal(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new deal in HubSpot.

    Params:
        dealname (str): Deal name (required)
        amount (str|float): Deal amount (optional)
        pipeline (str): Pipeline ID (optional, uses default if not specified)
        dealstage (str): Deal stage ID (required)
        properties (dict): Additional properties to set (optional)
        associations (list): Associations to create (optional)
            Each: {"to": {"id": str}, "types": [{"associationCategory": str, "associationTypeId": int}]}

    Returns:
        Deal ID and properties on success.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    dealname = params.get("dealname")
    if not dealname:
        return {"ok": False, "error": "dealname is required"}

    dealstage = params.get("dealstage")
    if not dealstage:
        return {"ok": False, "error": "dealstage is required"}

    # Build properties object
    properties = {
        "dealname": dealname,
        "dealstage": dealstage,
    }

    if params.get("amount") is not None:
        properties["amount"] = str(params["amount"])

    if params.get("pipeline"):
        properties["pipeline"] = params["pipeline"]

    # Merge additional properties
    if params.get("properties"):
        properties.update(params["properties"])

    data: Dict[str, Any] = {"properties": properties}

    # Add associations if provided
    if params.get("associations"):
        data["associations"] = params["associations"]

    result = _api_call(api_key, "/crm/v3/objects/deals", method="POST", data=data)

    if result.get("ok") and "result" in result:
        deal = result["result"]
        return {
            "ok": True,
            "data": {
                "id": deal.get("id"),
                "properties": deal.get("properties", {}),
                "createdAt": deal.get("createdAt"),
            }
        }
    return result


# =============================================================================
# Company Actions
# =============================================================================

def create_company(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new company in HubSpot.

    Params:
        name (str): Company name (required)
        domain (str): Company domain/website (optional)
        properties (dict): Additional properties to set (optional)
        associations (list): Associations to create (optional)

    Returns:
        Company ID and properties on success.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    name = params.get("name")
    if not name:
        return {"ok": False, "error": "name is required"}

    # Build properties object
    properties = {
        "name": name,
    }

    if params.get("domain"):
        properties["domain"] = params["domain"]

    # Merge additional properties
    if params.get("properties"):
        properties.update(params["properties"])

    data: Dict[str, Any] = {"properties": properties}

    # Add associations if provided
    if params.get("associations"):
        data["associations"] = params["associations"]

    result = _api_call(api_key, "/crm/v3/objects/companies", method="POST", data=data)

    if result.get("ok") and "result" in result:
        company = result["result"]
        return {
            "ok": True,
            "data": {
                "id": company.get("id"),
                "properties": company.get("properties", {}),
                "createdAt": company.get("createdAt"),
            }
        }
    return result


# =============================================================================
# Pipeline Actions
# =============================================================================

def list_pipelines(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List deal pipelines in HubSpot.

    Params:
        archived (bool): Include archived pipelines (default: False)

    Returns:
        List of pipelines with their stages.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    endpoint = "/crm/v3/pipelines/deals"

    if params.get("archived"):
        endpoint += "?archived=true"

    result = _api_call(api_key, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        response = result["result"]
        pipelines = []
        for pipeline in response.get("results", []):
            stages = []
            for stage in pipeline.get("stages", []):
                stages.append({
                    "id": stage.get("id"),
                    "label": stage.get("label"),
                    "displayOrder": stage.get("displayOrder"),
                    "metadata": stage.get("metadata", {}),
                })

            pipelines.append({
                "id": pipeline.get("id"),
                "label": pipeline.get("label"),
                "displayOrder": pipeline.get("displayOrder"),
                "stages": stages,
            })

        return {
            "ok": True,
            "data": {
                "pipelines": pipelines,
            }
        }
    return result


# =============================================================================
# Engagement Actions
# =============================================================================

def create_engagement(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an engagement/activity in HubSpot.

    Params:
        type (str): Engagement type - NOTE, EMAIL, TASK, MEETING, CALL (required)
        associations (dict): Associated objects (optional)
            {"contactIds": [int], "companyIds": [int], "dealIds": [int]}
        metadata (dict): Type-specific metadata (required)
            For NOTE: {"body": str}
            For EMAIL: {"from": {"email": str}, "to": [{"email": str}], "subject": str, "html": str}
            For TASK: {"body": str, "subject": str, "status": str, "forObjectType": str}
            For MEETING: {"body": str, "title": str, "startTime": int, "endTime": int}
            For CALL: {"body": str, "toNumber": str, "fromNumber": str, "status": str, "durationMilliseconds": int}
        timestamp (int): Unix timestamp in milliseconds (optional, defaults to now)
        ownerId (int): Owner user ID (optional)

    Returns:
        Engagement ID on success.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    engagement_type = params.get("type")
    if not engagement_type:
        return {"ok": False, "error": "type is required"}

    engagement_type = engagement_type.upper()
    valid_types = ["NOTE", "EMAIL", "TASK", "MEETING", "CALL"]
    if engagement_type not in valid_types:
        return {"ok": False, "error": f"Invalid type. Must be one of: {valid_types}"}

    metadata = params.get("metadata")
    if not metadata:
        return {"ok": False, "error": "metadata is required"}

    # Build engagement request
    import time
    data: Dict[str, Any] = {
        "engagement": {
            "active": True,
            "type": engagement_type,
            "timestamp": params.get("timestamp", int(time.time() * 1000)),
        },
        "metadata": metadata,
    }

    if params.get("ownerId"):
        data["engagement"]["ownerId"] = params["ownerId"]

    # Build associations
    associations: Dict[str, List[Dict[str, int]]] = {}
    assoc_input = params.get("associations", {})

    if assoc_input.get("contactIds"):
        associations["contactIds"] = [
            {"id": cid} for cid in assoc_input["contactIds"]
        ]
    if assoc_input.get("companyIds"):
        associations["companyIds"] = [
            {"id": cid} for cid in assoc_input["companyIds"]
        ]
    if assoc_input.get("dealIds"):
        associations["dealIds"] = [
            {"id": did} for did in assoc_input["dealIds"]
        ]

    if associations:
        data["associations"] = associations

    result = _api_call(api_key, "/engagements/v1/engagements", method="POST", data=data)

    if result.get("ok") and "result" in result:
        engagement = result["result"]
        return {
            "ok": True,
            "data": {
                "id": engagement.get("engagement", {}).get("id"),
                "type": engagement.get("engagement", {}).get("type"),
                "createdAt": engagement.get("engagement", {}).get("createdAt"),
                "associations": engagement.get("associations", {}),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "create_contact": create_contact,
    "update_contact": update_contact,
    "get_contact": get_contact,
    "search_contacts": search_contacts,
    "create_deal": create_deal,
    "create_company": create_company,
    "list_pipelines": list_pipelines,
    "create_engagement": create_engagement,
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
        logger.info(f"Executing hubspot.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
