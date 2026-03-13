"""
Sentry Controller for TinyHive

A controller for Sentry error monitoring and issue tracking integration.

Method IDs:
  controller.sentry.{profile}.list_projects
  controller.sentry.{profile}.list_issues
  controller.sentry.{profile}.get_issue
  controller.sentry.{profile}.update_issue
  controller.sentry.{profile}.list_events
  controller.sentry.{profile}.capture_event
  controller.sentry.{profile}.list_releases
  controller.sentry.{profile}.create_release

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "org_slug": "my-organization",
    "token_env": "SENTRY_AUTH_TOKEN"
}

Required Scopes:
---------------
- project:read - for list_projects
- event:read - for list_issues, get_issue, list_events
- event:write - for update_issue, capture_event
- release:read - for list_releases
- release:write - for create_release

Dependencies:
------------
None (standard library only)
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse

logger = logging.getLogger("tinyhive.controller.sentry")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# Sentry API base URL
SENTRY_API_BASE = "https://sentry.io/api/0"

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with Sentry configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available Sentry profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# HTTP Helpers
# =============================================================================

def _get_auth_token(profile: Dict[str, Any]) -> str:
    """Get the authentication token from environment variable."""
    token_env = profile.get("token_env", "SENTRY_AUTH_TOKEN")
    token = os.environ.get(token_env, "")
    if not token:
        raise ValueError(
            f"Environment variable '{token_env}' not set. "
            "Create a Sentry auth token at https://sentry.io/settings/auth-tokens/"
        )
    return token


def _api_call(
    token: str,
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    content_type: str = "application/json",
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Sentry API call."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
    }

    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("detail", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Sentry API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Sentry API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Project Actions
# =============================================================================

def list_projects(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all projects in the organization.

    Required Scope: project:read

    Params:
        org_slug (str): Organization slug (default: from profile)
    """
    profile = load_profile(profile_name)
    token = _get_auth_token(profile)

    org_slug = params.get("org_slug", profile.get("org_slug"))
    if not org_slug:
        return {"ok": False, "error": "org_slug required (in profile or params)"}

    url = f"{SENTRY_API_BASE}/organizations/{org_slug}/projects/"

    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        projects = result["result"]
        return {
            "ok": True,
            "data": [
                {
                    "id": p.get("id"),
                    "slug": p.get("slug"),
                    "name": p.get("name"),
                    "platform": p.get("platform"),
                    "status": p.get("status"),
                    "dateCreated": p.get("dateCreated"),
                    "isBookmarked": p.get("isBookmarked"),
                    "isMember": p.get("isMember"),
                    "hasAccess": p.get("hasAccess"),
                }
                for p in projects
            ]
        }
    return result


# =============================================================================
# Issue Actions
# =============================================================================

def list_issues(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List issues for a project.

    Required Scope: event:read

    Params:
        org_slug (str): Organization slug (default: from profile)
        project_slug (str): Project slug (required)
        query (str): Search query (optional, e.g., "is:unresolved")
        statsPeriod (str): Stats time period (optional, e.g., "24h", "14d")
    """
    profile = load_profile(profile_name)
    token = _get_auth_token(profile)

    org_slug = params.get("org_slug", profile.get("org_slug"))
    if not org_slug:
        return {"ok": False, "error": "org_slug required (in profile or params)"}

    project_slug = params.get("project_slug")
    if not project_slug:
        return {"ok": False, "error": "project_slug required"}

    query_params = {"project": project_slug}
    if params.get("query"):
        query_params["query"] = params["query"]
    if params.get("statsPeriod"):
        query_params["statsPeriod"] = params["statsPeriod"]

    url = f"{SENTRY_API_BASE}/organizations/{org_slug}/issues/?{urlencode(query_params)}"

    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        issues = result["result"]
        return {
            "ok": True,
            "data": [
                {
                    "id": i.get("id"),
                    "shortId": i.get("shortId"),
                    "title": i.get("title"),
                    "culprit": i.get("culprit"),
                    "status": i.get("status"),
                    "level": i.get("level"),
                    "platform": i.get("platform"),
                    "type": i.get("type"),
                    "count": i.get("count"),
                    "userCount": i.get("userCount"),
                    "firstSeen": i.get("firstSeen"),
                    "lastSeen": i.get("lastSeen"),
                    "isUnhandled": i.get("isUnhandled"),
                    "permalink": i.get("permalink"),
                    "assignedTo": i.get("assignedTo"),
                }
                for i in issues
            ]
        }
    return result


def get_issue(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a specific issue.

    Required Scope: event:read

    Params:
        issue_id (str): Issue ID (required)
    """
    profile = load_profile(profile_name)
    token = _get_auth_token(profile)

    issue_id = params.get("issue_id")
    if not issue_id:
        return {"ok": False, "error": "issue_id required"}

    url = f"{SENTRY_API_BASE}/issues/{issue_id}/"

    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        issue = result["result"]
        return {
            "ok": True,
            "data": {
                "id": issue.get("id"),
                "shortId": issue.get("shortId"),
                "title": issue.get("title"),
                "culprit": issue.get("culprit"),
                "status": issue.get("status"),
                "statusDetails": issue.get("statusDetails"),
                "level": issue.get("level"),
                "platform": issue.get("platform"),
                "type": issue.get("type"),
                "metadata": issue.get("metadata"),
                "count": issue.get("count"),
                "userCount": issue.get("userCount"),
                "firstSeen": issue.get("firstSeen"),
                "lastSeen": issue.get("lastSeen"),
                "firstRelease": issue.get("firstRelease"),
                "lastRelease": issue.get("lastRelease"),
                "isUnhandled": issue.get("isUnhandled"),
                "permalink": issue.get("permalink"),
                "assignedTo": issue.get("assignedTo"),
                "annotations": issue.get("annotations"),
                "project": issue.get("project"),
            }
        }
    return result


def update_issue(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an issue's status or assignment.

    Required Scope: event:write

    Params:
        issue_id (str): Issue ID (required)
        status (str): New status (optional: "resolved", "unresolved", "ignored")
        assignedTo (str): User or team to assign (optional, e.g., "user:123" or "team:456")
    """
    profile = load_profile(profile_name)
    token = _get_auth_token(profile)

    issue_id = params.get("issue_id")
    if not issue_id:
        return {"ok": False, "error": "issue_id required"}

    update_data = {}
    if params.get("status"):
        update_data["status"] = params["status"]
    if params.get("assignedTo"):
        update_data["assignedTo"] = params["assignedTo"]

    if not update_data:
        return {"ok": False, "error": "At least one of status or assignedTo required"}

    url = f"{SENTRY_API_BASE}/issues/{issue_id}/"
    data = json.dumps(update_data).encode("utf-8")

    result = _api_call(token, url, method="PUT", data=data)

    if result.get("ok") and "result" in result:
        issue = result["result"]
        return {
            "ok": True,
            "data": {
                "id": issue.get("id"),
                "shortId": issue.get("shortId"),
                "status": issue.get("status"),
                "assignedTo": issue.get("assignedTo"),
            }
        }
    return result


# =============================================================================
# Event Actions
# =============================================================================

def list_events(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List events for a specific issue.

    Required Scope: event:read

    Params:
        issue_id (str): Issue ID (required)
    """
    profile = load_profile(profile_name)
    token = _get_auth_token(profile)

    issue_id = params.get("issue_id")
    if not issue_id:
        return {"ok": False, "error": "issue_id required"}

    url = f"{SENTRY_API_BASE}/issues/{issue_id}/events/"

    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        events = result["result"]
        return {
            "ok": True,
            "data": [
                {
                    "eventID": e.get("eventID"),
                    "id": e.get("id"),
                    "dateCreated": e.get("dateCreated"),
                    "dateReceived": e.get("dateReceived"),
                    "user": e.get("user"),
                    "message": e.get("message"),
                    "title": e.get("title"),
                    "platform": e.get("platform"),
                    "type": e.get("type"),
                    "tags": e.get("tags"),
                    "context": e.get("context"),
                }
                for e in events
            ]
        }
    return result


def capture_event(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a new event to Sentry (for testing or programmatic event capture).

    This uses the Sentry store endpoint with DSN authentication.

    Params:
        dsn (str): Sentry DSN (required, e.g., "https://key@sentry.io/project_id")
        event_data (dict): Event data (required)
            - message (str): Error message
            - level (str): Event level (debug, info, warning, error, fatal)
            - platform (str): Platform (e.g., "python", "javascript")
            - exception (dict): Exception information
            - tags (dict): Custom tags
            - extra (dict): Extra context data
    """
    dsn = params.get("dsn")
    if not dsn:
        return {"ok": False, "error": "dsn required"}

    event_data = params.get("event_data")
    if not event_data:
        return {"ok": False, "error": "event_data required"}

    # Parse DSN
    try:
        parsed = urlparse(dsn)
        public_key = parsed.username
        project_id = parsed.path.strip("/")
        sentry_host = parsed.hostname
    except Exception as e:
        return {"ok": False, "error": f"Invalid DSN format: {e}"}

    if not public_key or not project_id:
        return {"ok": False, "error": "Invalid DSN: missing key or project_id"}

    # Build the store URL
    store_url = f"https://{sentry_host}/api/{project_id}/store/"

    # Build event payload
    import time
    import uuid

    event = {
        "event_id": uuid.uuid4().hex,
        "timestamp": time.time(),
        "platform": event_data.get("platform", "python"),
    }

    if event_data.get("message"):
        event["message"] = event_data["message"]
    if event_data.get("level"):
        event["level"] = event_data["level"]
    if event_data.get("exception"):
        event["exception"] = event_data["exception"]
    if event_data.get("tags"):
        event["tags"] = event_data["tags"]
    if event_data.get("extra"):
        event["extra"] = event_data["extra"]
    if event_data.get("user"):
        event["user"] = event_data["user"]
    if event_data.get("environment"):
        event["environment"] = event_data["environment"]
    if event_data.get("release"):
        event["release"] = event_data["release"]

    # Build auth header
    sentry_auth = (
        f"Sentry sentry_version=7, "
        f"sentry_client=tinyhive-sentry/1.0, "
        f"sentry_key={public_key}"
    )

    headers = {
        "Content-Type": "application/json",
        "X-Sentry-Auth": sentry_auth,
    }

    try:
        data = json.dumps(event).encode("utf-8")
        req = Request(store_url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                result = json.loads(response_body)
                return {"ok": True, "data": {"event_id": result.get("id", event["event_id"])}}
            return {"ok": True, "data": {"event_id": event["event_id"]}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error("Sentry store error %d: %s", e.code, error_body[:500])
        return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error capturing event")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Release Actions
# =============================================================================

def list_releases(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List releases for an organization.

    Required Scope: release:read

    Params:
        org_slug (str): Organization slug (default: from profile)
    """
    profile = load_profile(profile_name)
    token = _get_auth_token(profile)

    org_slug = params.get("org_slug", profile.get("org_slug"))
    if not org_slug:
        return {"ok": False, "error": "org_slug required (in profile or params)"}

    url = f"{SENTRY_API_BASE}/organizations/{org_slug}/releases/"

    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        releases = result["result"]
        return {
            "ok": True,
            "data": [
                {
                    "version": r.get("version"),
                    "shortVersion": r.get("shortVersion"),
                    "status": r.get("status"),
                    "dateCreated": r.get("dateCreated"),
                    "dateReleased": r.get("dateReleased"),
                    "firstEvent": r.get("firstEvent"),
                    "lastEvent": r.get("lastEvent"),
                    "newGroups": r.get("newGroups"),
                    "commitCount": r.get("commitCount"),
                    "authors": r.get("authors"),
                    "projects": [
                        {"slug": p.get("slug"), "name": p.get("name")}
                        for p in r.get("projects", [])
                    ],
                }
                for r in releases
            ]
        }
    return result


def create_release(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new release.

    Required Scope: release:write

    Params:
        org_slug (str): Organization slug (default: from profile)
        version (str): Release version string (required)
        projects (list): List of project slugs (required)
        ref (str): Git commit reference (optional)
        url (str): URL for release info (optional)
        dateReleased (str): ISO 8601 release date (optional)
    """
    profile = load_profile(profile_name)
    token = _get_auth_token(profile)

    org_slug = params.get("org_slug", profile.get("org_slug"))
    if not org_slug:
        return {"ok": False, "error": "org_slug required (in profile or params)"}

    version = params.get("version")
    if not version:
        return {"ok": False, "error": "version required"}

    projects = params.get("projects")
    if not projects:
        return {"ok": False, "error": "projects required (list of project slugs)"}

    release_data = {
        "version": version,
        "projects": projects,
    }

    if params.get("ref"):
        release_data["ref"] = params["ref"]
    if params.get("url"):
        release_data["url"] = params["url"]
    if params.get("dateReleased"):
        release_data["dateReleased"] = params["dateReleased"]

    url = f"{SENTRY_API_BASE}/organizations/{org_slug}/releases/"
    data = json.dumps(release_data).encode("utf-8")

    result = _api_call(token, url, method="POST", data=data)

    if result.get("ok") and "result" in result:
        release = result["result"]
        return {
            "ok": True,
            "data": {
                "version": release.get("version"),
                "shortVersion": release.get("shortVersion"),
                "status": release.get("status"),
                "dateCreated": release.get("dateCreated"),
                "projects": [
                    {"slug": p.get("slug"), "name": p.get("name")}
                    for p in release.get("projects", [])
                ],
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_projects": list_projects,
    "list_issues": list_issues,
    "get_issue": get_issue,
    "update_issue": update_issue,
    "list_events": list_events,
    "capture_event": capture_event,
    "list_releases": list_releases,
    "create_release": create_release,
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
        logger.info(f"Executing sentry.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
