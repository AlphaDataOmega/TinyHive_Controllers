"""Salesforce Controller for TinyHive

A controller for Salesforce REST API integration supporting SOQL queries,
SOSL searches, and CRUD operations on sObjects.

Method IDs:
  controller.salesforce.{profile}.query
  controller.salesforce.{profile}.get_record
  controller.salesforce.{profile}.create_record
  controller.salesforce.{profile}.update_record
  controller.salesforce.{profile}.delete_record
  controller.salesforce.{profile}.describe_object
  controller.salesforce.{profile}.list_objects
  controller.salesforce.{profile}.search

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "token_env": "SALESFORCE_ACCESS_TOKEN",
    "instance_url": "https://yourorg.salesforce.com"
}

Required Permissions:
--------------------
- API Enabled permission
- Object-level permissions for accessed sObjects

Dependencies:
------------
None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.salesforce")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Salesforce API version
API_VERSION = "v59.0"

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


def _get_access_token(profile: Dict[str, Any]) -> str:
    """Get the Salesforce access token from environment variable."""
    env_var = profile.get("token_env", "SALESFORCE_ACCESS_TOKEN")
    access_token = os.environ.get(env_var)
    if not access_token:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return access_token


def _get_instance_url(profile: Dict[str, Any]) -> str:
    """Get the Salesforce instance URL from profile."""
    instance_url = profile.get("instance_url")
    if not instance_url:
        raise ValueError("Profile missing required 'instance_url' field")
    # Remove trailing slash if present
    return instance_url.rstrip("/")


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    access_token: str,
    instance_url: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Salesforce API call."""
    url = f"{instance_url}/services/data/{API_VERSION}{endpoint}"

    headers = {
        "Authorization": f"Bearer {access_token}",
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
            # Salesforce returns errors as a list
            if isinstance(error_data, list) and len(error_data) > 0:
                error_message = error_data[0].get("message", error_body[:500])
                error_code = error_data[0].get("errorCode", "UNKNOWN")
                error_message = f"{error_code}: {error_message}"
            else:
                error_message = error_body[:500]
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Salesforce API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Salesforce API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Query Actions
# =============================================================================

def query(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a SOQL query.

    Params:
        query (str): SOQL query string (required)

    Returns:
        Query results with records on success.
    """
    profile = load_profile(profile_name)
    access_token = _get_access_token(profile)
    instance_url = _get_instance_url(profile)

    soql_query = params.get("query")
    if not soql_query:
        return {"ok": False, "error": "query is required"}

    # URL encode the query
    encoded_query = quote(soql_query, safe="")
    endpoint = f"/query?q={encoded_query}"

    result = _api_call(access_token, instance_url, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        response = result["result"]
        return {
            "ok": True,
            "data": {
                "totalSize": response.get("totalSize", 0),
                "done": response.get("done", True),
                "records": response.get("records", []),
                "nextRecordsUrl": response.get("nextRecordsUrl"),
            }
        }
    return result


def search(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a SOSL search.

    Params:
        search_query (str): SOSL search string (required)
            Example: "FIND {test} IN ALL FIELDS RETURNING Account(Id, Name)"

    Returns:
        Search results on success.
    """
    profile = load_profile(profile_name)
    access_token = _get_access_token(profile)
    instance_url = _get_instance_url(profile)

    search_query = params.get("search_query")
    if not search_query:
        return {"ok": False, "error": "search_query is required"}

    # URL encode the search query
    encoded_query = quote(search_query, safe="")
    endpoint = f"/search?q={encoded_query}"

    result = _api_call(access_token, instance_url, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        response = result["result"]
        return {
            "ok": True,
            "data": {
                "searchRecords": response.get("searchRecords", []),
            }
        }
    return result


# =============================================================================
# Record Actions
# =============================================================================

def get_record(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a record by ID.

    Params:
        sobject (str): sObject type, e.g., "Account", "Contact" (required)
        record_id (str): Salesforce record ID (required)
        fields (list): List of field names to return (optional)

    Returns:
        Record data on success.
    """
    profile = load_profile(profile_name)
    access_token = _get_access_token(profile)
    instance_url = _get_instance_url(profile)

    sobject = params.get("sobject")
    if not sobject:
        return {"ok": False, "error": "sobject is required"}

    record_id = params.get("record_id")
    if not record_id:
        return {"ok": False, "error": "record_id is required"}

    endpoint = f"/sobjects/{sobject}/{record_id}"

    # Add fields parameter if specified
    if params.get("fields"):
        fields_str = ",".join(params["fields"])
        endpoint += f"?fields={fields_str}"

    result = _api_call(access_token, instance_url, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        record = result["result"]
        return {
            "ok": True,
            "data": record
        }
    return result


def create_record(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new record.

    Params:
        sobject (str): sObject type, e.g., "Account", "Contact" (required)
        fields (dict): Field values for the new record (required)

    Returns:
        Created record ID on success.
    """
    profile = load_profile(profile_name)
    access_token = _get_access_token(profile)
    instance_url = _get_instance_url(profile)

    sobject = params.get("sobject")
    if not sobject:
        return {"ok": False, "error": "sobject is required"}

    fields = params.get("fields")
    if not fields:
        return {"ok": False, "error": "fields is required"}

    endpoint = f"/sobjects/{sobject}"

    result = _api_call(access_token, instance_url, endpoint, method="POST", data=fields)

    if result.get("ok") and "result" in result:
        response = result["result"]
        return {
            "ok": True,
            "data": {
                "id": response.get("id"),
                "success": response.get("success", True),
                "errors": response.get("errors", []),
            }
        }
    return result


def update_record(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing record.

    Params:
        sobject (str): sObject type, e.g., "Account", "Contact" (required)
        record_id (str): Salesforce record ID (required)
        fields (dict): Field values to update (required)

    Returns:
        Success status on success.
    """
    profile = load_profile(profile_name)
    access_token = _get_access_token(profile)
    instance_url = _get_instance_url(profile)

    sobject = params.get("sobject")
    if not sobject:
        return {"ok": False, "error": "sobject is required"}

    record_id = params.get("record_id")
    if not record_id:
        return {"ok": False, "error": "record_id is required"}

    fields = params.get("fields")
    if not fields:
        return {"ok": False, "error": "fields is required"}

    endpoint = f"/sobjects/{sobject}/{record_id}"

    result = _api_call(access_token, instance_url, endpoint, method="PATCH", data=fields)

    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "id": record_id,
                "updated": True,
            }
        }
    return result


def delete_record(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a record.

    Params:
        sobject (str): sObject type, e.g., "Account", "Contact" (required)
        record_id (str): Salesforce record ID (required)

    Returns:
        Success status on success.
    """
    profile = load_profile(profile_name)
    access_token = _get_access_token(profile)
    instance_url = _get_instance_url(profile)

    sobject = params.get("sobject")
    if not sobject:
        return {"ok": False, "error": "sobject is required"}

    record_id = params.get("record_id")
    if not record_id:
        return {"ok": False, "error": "record_id is required"}

    endpoint = f"/sobjects/{sobject}/{record_id}"

    result = _api_call(access_token, instance_url, endpoint, method="DELETE")

    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "id": record_id,
                "deleted": True,
            }
        }
    return result


# =============================================================================
# Metadata Actions
# =============================================================================

def describe_object(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get metadata description of an sObject.

    Params:
        sobject (str): sObject type, e.g., "Account", "Contact" (required)

    Returns:
        Object metadata including fields, relationships, etc.
    """
    profile = load_profile(profile_name)
    access_token = _get_access_token(profile)
    instance_url = _get_instance_url(profile)

    sobject = params.get("sobject")
    if not sobject:
        return {"ok": False, "error": "sobject is required"}

    endpoint = f"/sobjects/{sobject}/describe"

    result = _api_call(access_token, instance_url, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        metadata = result["result"]
        # Return a subset of useful metadata
        fields_info = []
        for field in metadata.get("fields", []):
            fields_info.append({
                "name": field.get("name"),
                "label": field.get("label"),
                "type": field.get("type"),
                "length": field.get("length"),
                "nillable": field.get("nillable"),
                "createable": field.get("createable"),
                "updateable": field.get("updateable"),
                "picklistValues": field.get("picklistValues", []),
                "referenceTo": field.get("referenceTo", []),
            })

        return {
            "ok": True,
            "data": {
                "name": metadata.get("name"),
                "label": metadata.get("label"),
                "labelPlural": metadata.get("labelPlural"),
                "keyPrefix": metadata.get("keyPrefix"),
                "createable": metadata.get("createable"),
                "updateable": metadata.get("updateable"),
                "deletable": metadata.get("deletable"),
                "queryable": metadata.get("queryable"),
                "searchable": metadata.get("searchable"),
                "fields": fields_info,
                "recordTypeInfos": metadata.get("recordTypeInfos", []),
                "childRelationships": [
                    {
                        "childSObject": rel.get("childSObject"),
                        "field": rel.get("field"),
                        "relationshipName": rel.get("relationshipName"),
                    }
                    for rel in metadata.get("childRelationships", [])
                ],
            }
        }
    return result


def list_objects(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List available sObjects in the organization.

    Params:
        None required

    Returns:
        List of sObjects with basic metadata.
    """
    profile = load_profile(profile_name)
    access_token = _get_access_token(profile)
    instance_url = _get_instance_url(profile)

    endpoint = "/sobjects"

    result = _api_call(access_token, instance_url, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        response = result["result"]
        sobjects = []
        for sobject in response.get("sobjects", []):
            sobjects.append({
                "name": sobject.get("name"),
                "label": sobject.get("label"),
                "labelPlural": sobject.get("labelPlural"),
                "keyPrefix": sobject.get("keyPrefix"),
                "createable": sobject.get("createable"),
                "updateable": sobject.get("updateable"),
                "deletable": sobject.get("deletable"),
                "queryable": sobject.get("queryable"),
                "searchable": sobject.get("searchable"),
                "custom": sobject.get("custom"),
            })

        return {
            "ok": True,
            "data": {
                "sobjects": sobjects,
                "encoding": response.get("encoding"),
                "maxBatchSize": response.get("maxBatchSize"),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "query": query,
    "get_record": get_record,
    "create_record": create_record,
    "update_record": update_record,
    "delete_record": delete_record,
    "describe_object": describe_object,
    "list_objects": list_objects,
    "search": search,
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
        logger.info(f"Executing salesforce.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
