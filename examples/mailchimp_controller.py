"""Mailchimp Controller for TinyHive

A controller for Mailchimp Marketing API integration supporting audiences,
subscribers, campaigns, and reporting.

Method IDs:
  controller.mailchimp.{profile}.list_audiences
  controller.mailchimp.{profile}.add_subscriber
  controller.mailchimp.{profile}.update_subscriber
  controller.mailchimp.{profile}.get_subscriber
  controller.mailchimp.{profile}.list_campaigns
  controller.mailchimp.{profile}.create_campaign
  controller.mailchimp.{profile}.send_campaign
  controller.mailchimp.{profile}.get_campaign_report

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "api_key_env": "MAILCHIMP_API_KEY"
}

The API key should be in the format: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-us1"
The data center (e.g., us1, us2) is extracted from the API key suffix.

Dependencies:
------------
None (standard library only)
"""

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.mailchimp")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

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
    """Get the Mailchimp API key from environment variable."""
    env_var = profile.get("api_key_env", "MAILCHIMP_API_KEY")
    api_key = os.environ.get(env_var)
    if not api_key:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return api_key


def _get_data_center(api_key: str) -> str:
    """Extract data center from API key suffix (e.g., us1, us2, us3)."""
    if "-" not in api_key:
        raise ValueError("Invalid API key format. Expected format: apikey-dc (e.g., xxx-us1)")
    return api_key.split("-")[-1]


def _get_base_url(api_key: str) -> str:
    """Build the base URL using the data center from the API key."""
    dc = _get_data_center(api_key)
    return f"https://{dc}.api.mailchimp.com/3.0"


def _get_subscriber_hash(email: str) -> str:
    """Generate MD5 hash of lowercase email for subscriber identification."""
    return hashlib.md5(email.lower().encode("utf-8")).hexdigest()


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
    """Make an authenticated Mailchimp API call using Basic Auth.

    Mailchimp uses Basic Auth with "anystring:api_key" format.
    """
    base_url = _get_base_url(api_key)
    url = f"{base_url}{endpoint}"

    # Basic Auth: any string as username, API key as password
    credentials = base64.b64encode(f"anystring:{api_key}".encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {credentials}",
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
            error_message = error_data.get("detail", error_data.get("title", error_body[:500]))
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Mailchimp API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Mailchimp API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Audience Actions
# =============================================================================

def list_audiences(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all audiences/lists in the Mailchimp account.

    Params:
        count (int): Number of records to return (default: 10, max: 1000)
        offset (int): Number of records to skip (default: 0)

    Returns:
        List of audiences with their details.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    query_params = {}
    count = params.get("count", 10)
    offset = params.get("offset", 0)

    query_params["count"] = min(int(count), 1000)
    query_params["offset"] = int(offset)

    endpoint = f"/lists?{urlencode(query_params)}"
    result = _api_call(api_key, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        response = result["result"]
        audiences = []
        for lst in response.get("lists", []):
            audiences.append({
                "id": lst.get("id"),
                "name": lst.get("name"),
                "contact": lst.get("contact", {}),
                "permission_reminder": lst.get("permission_reminder"),
                "campaign_defaults": lst.get("campaign_defaults", {}),
                "stats": lst.get("stats", {}),
                "date_created": lst.get("date_created"),
            })

        return {
            "ok": True,
            "data": {
                "audiences": audiences,
                "total_items": response.get("total_items", len(audiences)),
            }
        }
    return result


# =============================================================================
# Subscriber Actions
# =============================================================================

def add_subscriber(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a subscriber to an audience/list.

    Params:
        list_id (str): The unique ID for the list (required)
        email (str): Email address for the subscriber (required)
        merge_fields (dict): Merge field values (e.g., {"FNAME": "John", "LNAME": "Doe"})
        tags (list): List of tag names to add to subscriber
        status (str): Subscription status - "subscribed", "unsubscribed",
                      "cleaned", "pending", "transactional" (default: "subscribed")

    Returns:
        Subscriber details on success.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    list_id = params.get("list_id")
    if not list_id:
        return {"ok": False, "error": "list_id is required"}

    email = params.get("email")
    if not email:
        return {"ok": False, "error": "email is required"}

    subscriber_data: Dict[str, Any] = {
        "email_address": email,
        "status": params.get("status", "subscribed"),
    }

    if params.get("merge_fields"):
        subscriber_data["merge_fields"] = params["merge_fields"]

    if params.get("tags"):
        subscriber_data["tags"] = params["tags"]

    endpoint = f"/lists/{list_id}/members"
    result = _api_call(api_key, endpoint, method="POST", data=subscriber_data)

    if result.get("ok") and "result" in result:
        member = result["result"]
        return {
            "ok": True,
            "data": {
                "id": member.get("id"),
                "email_address": member.get("email_address"),
                "unique_email_id": member.get("unique_email_id"),
                "status": member.get("status"),
                "merge_fields": member.get("merge_fields", {}),
                "tags": [t.get("name") for t in member.get("tags", [])],
                "list_id": member.get("list_id"),
            }
        }
    return result


def update_subscriber(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing subscriber in an audience/list.

    Params:
        list_id (str): The unique ID for the list (required)
        email (str): Email address of the subscriber to update (required)
        merge_fields (dict): Merge field values to update
        status (str): New subscription status - "subscribed", "unsubscribed",
                      "cleaned", "pending", "transactional"

    Returns:
        Updated subscriber details on success.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    list_id = params.get("list_id")
    if not list_id:
        return {"ok": False, "error": "list_id is required"}

    email = params.get("email")
    if not email:
        return {"ok": False, "error": "email is required"}

    subscriber_hash = _get_subscriber_hash(email)

    update_data: Dict[str, Any] = {}

    if params.get("merge_fields"):
        update_data["merge_fields"] = params["merge_fields"]

    if params.get("status"):
        update_data["status"] = params["status"]

    if not update_data:
        return {"ok": False, "error": "At least one of merge_fields or status is required"}

    endpoint = f"/lists/{list_id}/members/{subscriber_hash}"
    result = _api_call(api_key, endpoint, method="PATCH", data=update_data)

    if result.get("ok") and "result" in result:
        member = result["result"]
        return {
            "ok": True,
            "data": {
                "id": member.get("id"),
                "email_address": member.get("email_address"),
                "unique_email_id": member.get("unique_email_id"),
                "status": member.get("status"),
                "merge_fields": member.get("merge_fields", {}),
                "tags": [t.get("name") for t in member.get("tags", [])],
                "list_id": member.get("list_id"),
                "last_changed": member.get("last_changed"),
            }
        }
    return result


def get_subscriber(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get subscriber information from an audience/list.

    Params:
        list_id (str): The unique ID for the list (required)
        email (str): Email address of the subscriber (required)

    Returns:
        Subscriber details on success.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    list_id = params.get("list_id")
    if not list_id:
        return {"ok": False, "error": "list_id is required"}

    email = params.get("email")
    if not email:
        return {"ok": False, "error": "email is required"}

    subscriber_hash = _get_subscriber_hash(email)

    endpoint = f"/lists/{list_id}/members/{subscriber_hash}"
    result = _api_call(api_key, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        member = result["result"]
        return {
            "ok": True,
            "data": {
                "id": member.get("id"),
                "email_address": member.get("email_address"),
                "unique_email_id": member.get("unique_email_id"),
                "status": member.get("status"),
                "merge_fields": member.get("merge_fields", {}),
                "tags": [t.get("name") for t in member.get("tags", [])],
                "stats": member.get("stats", {}),
                "list_id": member.get("list_id"),
                "timestamp_signup": member.get("timestamp_signup"),
                "timestamp_opt": member.get("timestamp_opt"),
                "last_changed": member.get("last_changed"),
            }
        }
    return result


# =============================================================================
# Campaign Actions
# =============================================================================

def list_campaigns(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List campaigns in the Mailchimp account.

    Params:
        status (str): Filter by status - "save", "paused", "schedule", "sending", "sent"
        type (str): Filter by type - "regular", "plaintext", "absplit", "rss", "variate"
        count (int): Number of records to return (default: 10, max: 1000)

    Returns:
        List of campaigns with their details.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    query_params = {}

    if params.get("status"):
        query_params["status"] = params["status"]

    if params.get("type"):
        query_params["type"] = params["type"]

    count = params.get("count", 10)
    query_params["count"] = min(int(count), 1000)

    endpoint = "/campaigns"
    if query_params:
        endpoint = f"/campaigns?{urlencode(query_params)}"

    result = _api_call(api_key, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        response = result["result"]
        campaigns = []
        for campaign in response.get("campaigns", []):
            campaigns.append({
                "id": campaign.get("id"),
                "web_id": campaign.get("web_id"),
                "type": campaign.get("type"),
                "status": campaign.get("status"),
                "emails_sent": campaign.get("emails_sent"),
                "send_time": campaign.get("send_time"),
                "content_type": campaign.get("content_type"),
                "recipients": campaign.get("recipients", {}),
                "settings": campaign.get("settings", {}),
                "tracking": campaign.get("tracking", {}),
                "create_time": campaign.get("create_time"),
            })

        return {
            "ok": True,
            "data": {
                "campaigns": campaigns,
                "total_items": response.get("total_items", len(campaigns)),
            }
        }
    return result


def create_campaign(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new campaign.

    Params:
        type (str): Campaign type - "regular", "plaintext", "absplit", "rss", "variate" (required)
        recipients (dict): Recipients configuration (required)
            - list_id (str): The unique list ID (required)
            - segment_opts (dict): Segment options (optional)
        settings (dict): Campaign settings (required)
            - subject_line (str): Subject line for the campaign (required)
            - preview_text (str): Preview text (optional)
            - title (str): Internal title for the campaign (optional)
            - from_name (str): "From" name for the campaign (required)
            - reply_to (str): Reply-to email address (required)

    Returns:
        Created campaign details on success.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    campaign_type = params.get("type")
    if not campaign_type:
        return {"ok": False, "error": "type is required"}

    valid_types = ["regular", "plaintext", "absplit", "rss", "variate"]
    if campaign_type not in valid_types:
        return {"ok": False, "error": f"Invalid type. Must be one of: {valid_types}"}

    recipients = params.get("recipients")
    if not recipients:
        return {"ok": False, "error": "recipients is required"}

    if not recipients.get("list_id"):
        return {"ok": False, "error": "recipients.list_id is required"}

    settings = params.get("settings")
    if not settings:
        return {"ok": False, "error": "settings is required"}

    required_settings = ["subject_line", "from_name", "reply_to"]
    for field in required_settings:
        if not settings.get(field):
            return {"ok": False, "error": f"settings.{field} is required"}

    campaign_data = {
        "type": campaign_type,
        "recipients": recipients,
        "settings": settings,
    }

    endpoint = "/campaigns"
    result = _api_call(api_key, endpoint, method="POST", data=campaign_data)

    if result.get("ok") and "result" in result:
        campaign = result["result"]
        return {
            "ok": True,
            "data": {
                "id": campaign.get("id"),
                "web_id": campaign.get("web_id"),
                "type": campaign.get("type"),
                "status": campaign.get("status"),
                "recipients": campaign.get("recipients", {}),
                "settings": campaign.get("settings", {}),
                "create_time": campaign.get("create_time"),
            }
        }
    return result


def send_campaign(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a campaign.

    Params:
        campaign_id (str): The unique ID for the campaign (required)

    Returns:
        Success status on completion.

    Note: Campaign must have content set before sending.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    campaign_id = params.get("campaign_id")
    if not campaign_id:
        return {"ok": False, "error": "campaign_id is required"}

    endpoint = f"/campaigns/{campaign_id}/actions/send"
    result = _api_call(api_key, endpoint, method="POST")

    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "campaign_id": campaign_id,
                "status": "sent",
                "message": "Campaign has been sent successfully",
            }
        }
    return result


# =============================================================================
# Report Actions
# =============================================================================

def get_campaign_report(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get report/statistics for a sent campaign.

    Params:
        campaign_id (str): The unique ID for the campaign (required)

    Returns:
        Campaign statistics including opens, clicks, bounces, etc.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    campaign_id = params.get("campaign_id")
    if not campaign_id:
        return {"ok": False, "error": "campaign_id is required"}

    endpoint = f"/reports/{campaign_id}"
    result = _api_call(api_key, endpoint, method="GET")

    if result.get("ok") and "result" in result:
        report = result["result"]
        return {
            "ok": True,
            "data": {
                "id": report.get("id"),
                "campaign_title": report.get("campaign_title"),
                "type": report.get("type"),
                "list_id": report.get("list_id"),
                "list_name": report.get("list_name"),
                "subject_line": report.get("subject_line"),
                "emails_sent": report.get("emails_sent"),
                "abuse_reports": report.get("abuse_reports"),
                "unsubscribed": report.get("unsubscribed"),
                "send_time": report.get("send_time"),
                "bounces": report.get("bounces", {}),
                "forwards": report.get("forwards", {}),
                "opens": report.get("opens", {}),
                "clicks": report.get("clicks", {}),
                "facebook_likes": report.get("facebook_likes", {}),
                "industry_stats": report.get("industry_stats", {}),
                "list_stats": report.get("list_stats", {}),
                "timeseries": report.get("timeseries", []),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_audiences": list_audiences,
    "add_subscriber": add_subscriber,
    "update_subscriber": update_subscriber,
    "get_subscriber": get_subscriber,
    "list_campaigns": list_campaigns,
    "create_campaign": create_campaign,
    "send_campaign": send_campaign,
    "get_campaign_report": get_campaign_report,
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
        logger.info(f"Executing mailchimp.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
