"""
Netlify Controller for TinyHive

A controller for interacting with the Netlify API.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "site_id": "optional-default-site-id",
    "team_slug": "optional-team-slug"
}

Environment Variables:
---------------------
NETLIFY_ACCESS_TOKEN: Personal access token from Netlify

API Documentation:
-----------------
https://docs.netlify.com/api/get-started/

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

logger = logging.getLogger("tinyhive.controller.netlify")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"
BASE_URL = "https://api.netlify.com/api/v1"
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


def _get_access_token() -> str:
    """Get the Netlify access token from environment variable."""
    token = os.environ.get("NETLIFY_ACCESS_TOKEN")
    if not token:
        raise ValueError(
            "NETLIFY_ACCESS_TOKEN environment variable not set. "
            "Create a personal access token at https://app.netlify.com/user/applications#personal-access-tokens"
        )
    return token


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    endpoint: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    content_type: str = "application/json",
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Netlify API call."""
    token = _get_access_token()

    url = f"{BASE_URL}{endpoint}"
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
            error_message = error_data.get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Netlify API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Netlify API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Site Actions
# =============================================================================

def list_sites(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all sites.

    Params:
        filter (str): Filter sites - 'all', 'owner', 'guest' (optional)
        page (int): Page number for pagination (optional)
        per_page (int): Number of sites per page, max 100 (optional)
    """
    profile = load_profile(profile_name)

    query_params = {}
    if params.get("filter"):
        query_params["filter"] = params["filter"]
    if params.get("page"):
        query_params["page"] = params["page"]
    if params.get("per_page"):
        query_params["per_page"] = params["per_page"]

    endpoint = "/sites"
    if query_params:
        endpoint += f"?{urlencode(query_params)}"

    result = _api_call(endpoint)

    if result.get("ok") and "result" in result:
        sites = result["result"]
        return {
            "ok": True,
            "data": [
                {
                    "id": site.get("id"),
                    "name": site.get("name"),
                    "url": site.get("url"),
                    "ssl_url": site.get("ssl_url"),
                    "admin_url": site.get("admin_url"),
                    "created_at": site.get("created_at"),
                    "updated_at": site.get("updated_at"),
                    "state": site.get("state"),
                    "custom_domain": site.get("custom_domain"),
                }
                for site in sites
            ],
            "count": len(sites)
        }
    return result


def get_site(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a specific site.

    Params:
        site_id (str): The site ID (required, or uses profile default)
    """
    profile = load_profile(profile_name)

    site_id = params.get("site_id", profile.get("site_id"))
    if not site_id:
        return {"ok": False, "error": "site_id is required"}

    result = _api_call(f"/sites/{site_id}")

    if result.get("ok") and "result" in result:
        site = result["result"]
        return {
            "ok": True,
            "data": {
                "id": site.get("id"),
                "name": site.get("name"),
                "url": site.get("url"),
                "ssl_url": site.get("ssl_url"),
                "admin_url": site.get("admin_url"),
                "created_at": site.get("created_at"),
                "updated_at": site.get("updated_at"),
                "state": site.get("state"),
                "custom_domain": site.get("custom_domain"),
                "deploy_url": site.get("deploy_url"),
                "published_deploy": site.get("published_deploy"),
                "build_settings": site.get("build_settings"),
                "repo": site.get("repo"),
                "ssl": site.get("ssl"),
                "force_ssl": site.get("force_ssl"),
            }
        }
    return result


# =============================================================================
# Deploy Actions
# =============================================================================

def list_deploys(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List deploys for a site.

    Params:
        site_id (str): The site ID (required, or uses profile default)
        page (int): Page number for pagination (optional)
        per_page (int): Number of deploys per page, max 100 (optional)
    """
    profile = load_profile(profile_name)

    site_id = params.get("site_id", profile.get("site_id"))
    if not site_id:
        return {"ok": False, "error": "site_id is required"}

    query_params = {}
    if params.get("page"):
        query_params["page"] = params["page"]
    if params.get("per_page"):
        query_params["per_page"] = params["per_page"]

    endpoint = f"/sites/{site_id}/deploys"
    if query_params:
        endpoint += f"?{urlencode(query_params)}"

    result = _api_call(endpoint)

    if result.get("ok") and "result" in result:
        deploys = result["result"]
        return {
            "ok": True,
            "data": [
                {
                    "id": deploy.get("id"),
                    "site_id": deploy.get("site_id"),
                    "state": deploy.get("state"),
                    "name": deploy.get("name"),
                    "url": deploy.get("url"),
                    "ssl_url": deploy.get("ssl_url"),
                    "deploy_url": deploy.get("deploy_url"),
                    "deploy_ssl_url": deploy.get("deploy_ssl_url"),
                    "created_at": deploy.get("created_at"),
                    "updated_at": deploy.get("updated_at"),
                    "published_at": deploy.get("published_at"),
                    "commit_ref": deploy.get("commit_ref"),
                    "branch": deploy.get("branch"),
                    "error_message": deploy.get("error_message"),
                    "context": deploy.get("context"),
                    "locked": deploy.get("locked"),
                }
                for deploy in deploys
            ],
            "count": len(deploys)
        }
    return result


def get_deploy(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a specific deploy.

    Params:
        deploy_id (str): The deploy ID (required)
    """
    profile = load_profile(profile_name)

    deploy_id = params.get("deploy_id")
    if not deploy_id:
        return {"ok": False, "error": "deploy_id is required"}

    result = _api_call(f"/deploys/{deploy_id}")

    if result.get("ok") and "result" in result:
        deploy = result["result"]
        return {
            "ok": True,
            "data": {
                "id": deploy.get("id"),
                "site_id": deploy.get("site_id"),
                "state": deploy.get("state"),
                "name": deploy.get("name"),
                "url": deploy.get("url"),
                "ssl_url": deploy.get("ssl_url"),
                "deploy_url": deploy.get("deploy_url"),
                "deploy_ssl_url": deploy.get("deploy_ssl_url"),
                "created_at": deploy.get("created_at"),
                "updated_at": deploy.get("updated_at"),
                "published_at": deploy.get("published_at"),
                "commit_ref": deploy.get("commit_ref"),
                "commit_url": deploy.get("commit_url"),
                "branch": deploy.get("branch"),
                "error_message": deploy.get("error_message"),
                "context": deploy.get("context"),
                "locked": deploy.get("locked"),
                "review_url": deploy.get("review_url"),
                "framework": deploy.get("framework"),
                "function_schedules": deploy.get("function_schedules"),
            }
        }
    return result


def create_deploy(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new deploy with file digests.

    This initiates a deploy by providing SHA1 hashes of files. Netlify will
    respond with which files need to be uploaded.

    Params:
        site_id (str): The site ID (required, or uses profile default)
        files (dict): Map of file paths to SHA1 digests (required)
            Example: {"/index.html": "abc123...", "/css/style.css": "def456..."}
        draft (bool): Create as draft deploy (optional)
        branch (str): Branch name for deploy (optional)
        title (str): Deploy title/message (optional)
    """
    profile = load_profile(profile_name)

    site_id = params.get("site_id", profile.get("site_id"))
    if not site_id:
        return {"ok": False, "error": "site_id is required"}

    files = params.get("files")
    if not files or not isinstance(files, dict):
        return {"ok": False, "error": "files dict is required (path -> SHA1 digest)"}

    deploy_data: Dict[str, Any] = {"files": files}

    if params.get("draft"):
        deploy_data["draft"] = True
    if params.get("branch"):
        deploy_data["branch"] = params["branch"]
    if params.get("title"):
        deploy_data["title"] = params["title"]

    data = json.dumps(deploy_data).encode("utf-8")
    result = _api_call(f"/sites/{site_id}/deploys", method="POST", data=data)

    if result.get("ok") and "result" in result:
        deploy = result["result"]
        return {
            "ok": True,
            "data": {
                "id": deploy.get("id"),
                "site_id": deploy.get("site_id"),
                "state": deploy.get("state"),
                "deploy_url": deploy.get("deploy_url"),
                "deploy_ssl_url": deploy.get("deploy_ssl_url"),
                "required": deploy.get("required", []),
                "required_functions": deploy.get("required_functions", []),
            }
        }
    return result


def lock_deploy(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lock a deploy to prevent auto-publishing.

    Params:
        deploy_id (str): The deploy ID (required)
    """
    profile = load_profile(profile_name)

    deploy_id = params.get("deploy_id")
    if not deploy_id:
        return {"ok": False, "error": "deploy_id is required"}

    result = _api_call(f"/deploys/{deploy_id}/lock", method="POST")

    if result.get("ok") and "result" in result:
        deploy = result["result"]
        return {
            "ok": True,
            "data": {
                "id": deploy.get("id"),
                "site_id": deploy.get("site_id"),
                "state": deploy.get("state"),
                "locked": deploy.get("locked"),
                "deploy_url": deploy.get("deploy_url"),
                "deploy_ssl_url": deploy.get("deploy_ssl_url"),
            }
        }
    return result


# =============================================================================
# Form Actions
# =============================================================================

def list_forms(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List forms for a site.

    Params:
        site_id (str): The site ID (required, or uses profile default)
    """
    profile = load_profile(profile_name)

    site_id = params.get("site_id", profile.get("site_id"))
    if not site_id:
        return {"ok": False, "error": "site_id is required"}

    result = _api_call(f"/sites/{site_id}/forms")

    if result.get("ok") and "result" in result:
        forms = result["result"]
        return {
            "ok": True,
            "data": [
                {
                    "id": form.get("id"),
                    "site_id": form.get("site_id"),
                    "name": form.get("name"),
                    "paths": form.get("paths"),
                    "submission_count": form.get("submission_count"),
                    "fields": form.get("fields"),
                    "created_at": form.get("created_at"),
                }
                for form in forms
            ],
            "count": len(forms)
        }
    return result


def list_submissions(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List submissions for a form.

    Params:
        form_id (str): The form ID (required)
        page (int): Page number for pagination (optional)
        per_page (int): Number of submissions per page, max 100 (optional)
    """
    profile = load_profile(profile_name)

    form_id = params.get("form_id")
    if not form_id:
        return {"ok": False, "error": "form_id is required"}

    query_params = {}
    if params.get("page"):
        query_params["page"] = params["page"]
    if params.get("per_page"):
        query_params["per_page"] = params["per_page"]

    endpoint = f"/forms/{form_id}/submissions"
    if query_params:
        endpoint += f"?{urlencode(query_params)}"

    result = _api_call(endpoint)

    if result.get("ok") and "result" in result:
        submissions = result["result"]
        return {
            "ok": True,
            "data": [
                {
                    "id": submission.get("id"),
                    "form_id": submission.get("form_id"),
                    "form_name": submission.get("form_name"),
                    "site_url": submission.get("site_url"),
                    "created_at": submission.get("created_at"),
                    "data": submission.get("data"),
                    "human_fields": submission.get("human_fields"),
                    "ordered_human_fields": submission.get("ordered_human_fields"),
                }
                for submission in submissions
            ],
            "count": len(submissions)
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_sites": list_sites,
    "get_site": get_site,
    "list_deploys": list_deploys,
    "get_deploy": get_deploy,
    "create_deploy": create_deploy,
    "lock_deploy": lock_deploy,
    "list_forms": list_forms,
    "list_submissions": list_submissions,
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

    logger.info(f"Executing netlify.{profile}.{action}")
    try:
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
