"""
Jenkins Controller for TinyHive

A controller for interacting with Jenkins CI/CD server via REST API.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "jenkins_url": "https://jenkins.example.com",
    "username_env": "JENKINS_USERNAME",
    "api_token_env": "JENKINS_API_TOKEN"
}

Environment Variables:
---------------------
- JENKINS_USERNAME: Jenkins username for authentication
- JENKINS_API_TOKEN: Jenkins API token (generate from User > Configure > API Token)

Required Permissions:
--------------------
- list_jobs: Overall/Read, Job/Read
- get_job: Job/Read
- build_job: Job/Build
- get_build: Job/Read
- get_build_log: Job/Read
- stop_build: Job/Cancel
- get_queue: Overall/Read
- list_views: Overall/Read

Dependencies:
------------
None (standard library only)
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.jenkins")

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


def _get_auth(profile: Dict[str, Any]) -> str:
    """Get Basic Auth header value from profile credentials."""
    username_env = profile.get("username_env", "JENKINS_USERNAME")
    api_token_env = profile.get("api_token_env", "JENKINS_API_TOKEN")

    username = os.environ.get(username_env)
    api_token = os.environ.get(api_token_env)

    if not username:
        raise ValueError(f"Environment variable '{username_env}' not set")
    if not api_token:
        raise ValueError(f"Environment variable '{api_token_env}' not set")

    credentials = f"{username}:{api_token}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    profile: Dict[str, Any],
    path: str,
    method: str = "GET",
    data: bytes = None,
    content_type: str = "application/json",
    timeout: int = DEFAULT_TIMEOUT,
    accept: str = "application/json"
) -> Dict[str, Any]:
    """Make an authenticated Jenkins API call."""
    jenkins_url = profile.get("jenkins_url", "").rstrip("/")
    if not jenkins_url:
        return {"ok": False, "error": "jenkins_url not configured in profile"}

    url = f"{jenkins_url}{path}"

    headers = {
        "Authorization": _get_auth(profile),
        "Content-Type": content_type,
        "Accept": accept,
    }

    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read()

            # Handle different response types
            content_type_header = response.headers.get("Content-Type", "")

            if "application/json" in content_type_header:
                if response_body:
                    return {"ok": True, "result": json.loads(response_body.decode("utf-8"))}
                return {"ok": True, "result": {}}
            elif "text/plain" in content_type_header or "text/html" in content_type_header:
                return {"ok": True, "result": response_body.decode("utf-8", errors="replace")}
            else:
                # Try JSON first, fall back to text
                try:
                    return {"ok": True, "result": json.loads(response_body.decode("utf-8"))}
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return {"ok": True, "result": response_body.decode("utf-8", errors="replace")}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error("Jenkins API error %d: %s", e.code, error_body[:500])
        return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except ValueError as e:
        # Credential errors
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error in Jenkins API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def list_jobs(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all jobs in Jenkins.

    Params:
        folder (str): Folder path to list jobs from (optional)
        tree (str): Tree filter for response fields (optional)

    Returns:
        jobs: List of job objects with name, url, color (build status)
    """
    try:
        profile = load_profile(profile_name)

        folder = params.get("folder", "")
        tree = params.get("tree", "jobs[name,url,color,buildable]")

        if folder:
            # Navigate to folder
            folder_path = "/job/" + "/job/".join(quote(f, safe="") for f in folder.strip("/").split("/"))
            path = f"{folder_path}/api/json?tree={quote(tree, safe='')}"
        else:
            path = f"/api/json?tree={quote(tree, safe='')}"

        result = _api_call(profile, path)

        if result.get("ok") and isinstance(result.get("result"), dict):
            jobs = result["result"].get("jobs", [])
            return {
                "ok": True,
                "data": {
                    "jobs": [
                        {
                            "name": job.get("name"),
                            "url": job.get("url"),
                            "color": job.get("color"),
                            "buildable": job.get("buildable", True)
                        }
                        for job in jobs
                    ],
                    "count": len(jobs)
                }
            }
        return result

    except Exception as e:
        logger.exception("list_jobs failed")
        return {"ok": False, "error": str(e)}


def get_job(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get detailed information about a job.

    Params:
        job_name (str): Name of the job (required)
        folder (str): Folder path if job is in a folder (optional)

    Returns:
        Job details including builds, health reports, and configuration
    """
    try:
        profile = load_profile(profile_name)

        job_name = params.get("job_name")
        if not job_name:
            return {"ok": False, "error": "job_name is required"}

        folder = params.get("folder", "")

        if folder:
            folder_path = "/job/" + "/job/".join(quote(f, safe="") for f in folder.strip("/").split("/"))
            path = f"{folder_path}/job/{quote(job_name, safe='')}/api/json"
        else:
            path = f"/job/{quote(job_name, safe='')}/api/json"

        result = _api_call(profile, path)

        if result.get("ok") and isinstance(result.get("result"), dict):
            job = result["result"]
            return {
                "ok": True,
                "data": {
                    "name": job.get("name"),
                    "url": job.get("url"),
                    "description": job.get("description"),
                    "buildable": job.get("buildable"),
                    "color": job.get("color"),
                    "in_queue": job.get("inQueue", False),
                    "last_build": job.get("lastBuild"),
                    "last_successful_build": job.get("lastSuccessfulBuild"),
                    "last_failed_build": job.get("lastFailedBuild"),
                    "last_stable_build": job.get("lastStableBuild"),
                    "next_build_number": job.get("nextBuildNumber"),
                    "health_report": job.get("healthReport", []),
                    "builds": job.get("builds", [])[:10],  # Limit to last 10 builds
                    "property": job.get("property", [])
                }
            }
        return result

    except Exception as e:
        logger.exception("get_job failed")
        return {"ok": False, "error": str(e)}


def build_job(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trigger a build for a job.

    Params:
        job_name (str): Name of the job (required)
        folder (str): Folder path if job is in a folder (optional)
        parameters (dict): Build parameters (optional)

    Returns:
        queue_url: URL to the queued build item
    """
    try:
        profile = load_profile(profile_name)

        job_name = params.get("job_name")
        if not job_name:
            return {"ok": False, "error": "job_name is required"}

        folder = params.get("folder", "")
        parameters = params.get("parameters", {})

        if folder:
            folder_path = "/job/" + "/job/".join(quote(f, safe="") for f in folder.strip("/").split("/"))
            base_path = f"{folder_path}/job/{quote(job_name, safe='')}"
        else:
            base_path = f"/job/{quote(job_name, safe='')}"

        if parameters:
            # Build with parameters
            path = f"{base_path}/buildWithParameters"
            data = urlencode(parameters).encode("utf-8")
            result = _api_call(
                profile, path, method="POST", data=data,
                content_type="application/x-www-form-urlencoded"
            )
        else:
            # Build without parameters
            path = f"{base_path}/build"
            result = _api_call(profile, path, method="POST")

        if result.get("ok"):
            return {
                "ok": True,
                "data": {
                    "message": f"Build triggered for job '{job_name}'",
                    "job_name": job_name
                }
            }
        return result

    except Exception as e:
        logger.exception("build_job failed")
        return {"ok": False, "error": str(e)}


def get_build(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get information about a specific build.

    Params:
        job_name (str): Name of the job (required)
        build_number (int/str): Build number or 'lastBuild', 'lastSuccessfulBuild', etc. (required)
        folder (str): Folder path if job is in a folder (optional)

    Returns:
        Build details including status, duration, and actions
    """
    try:
        profile = load_profile(profile_name)

        job_name = params.get("job_name")
        build_number = params.get("build_number")

        if not job_name:
            return {"ok": False, "error": "job_name is required"}
        if build_number is None:
            return {"ok": False, "error": "build_number is required"}

        folder = params.get("folder", "")

        if folder:
            folder_path = "/job/" + "/job/".join(quote(f, safe="") for f in folder.strip("/").split("/"))
            path = f"{folder_path}/job/{quote(job_name, safe='')}/{build_number}/api/json"
        else:
            path = f"/job/{quote(job_name, safe='')}/{build_number}/api/json"

        result = _api_call(profile, path)

        if result.get("ok") and isinstance(result.get("result"), dict):
            build = result["result"]
            return {
                "ok": True,
                "data": {
                    "number": build.get("number"),
                    "url": build.get("url"),
                    "result": build.get("result"),
                    "building": build.get("building", False),
                    "duration": build.get("duration"),
                    "estimated_duration": build.get("estimatedDuration"),
                    "timestamp": build.get("timestamp"),
                    "display_name": build.get("displayName"),
                    "description": build.get("description"),
                    "executor": build.get("executor"),
                    "artifacts": build.get("artifacts", []),
                    "actions": [
                        action for action in build.get("actions", [])
                        if action and action.get("_class")
                    ][:5],  # Limit actions
                    "changeset": build.get("changeSet", {})
                }
            }
        return result

    except Exception as e:
        logger.exception("get_build failed")
        return {"ok": False, "error": str(e)}


def get_build_log(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the console output (log) of a build.

    Params:
        job_name (str): Name of the job (required)
        build_number (int/str): Build number or 'lastBuild', etc. (required)
        folder (str): Folder path if job is in a folder (optional)
        start (int): Start byte offset for log (optional, for progressive output)

    Returns:
        log: Console output text
    """
    try:
        profile = load_profile(profile_name)

        job_name = params.get("job_name")
        build_number = params.get("build_number")

        if not job_name:
            return {"ok": False, "error": "job_name is required"}
        if build_number is None:
            return {"ok": False, "error": "build_number is required"}

        folder = params.get("folder", "")
        start = params.get("start")

        if folder:
            folder_path = "/job/" + "/job/".join(quote(f, safe="") for f in folder.strip("/").split("/"))
            base_path = f"{folder_path}/job/{quote(job_name, safe='')}/{build_number}"
        else:
            base_path = f"/job/{quote(job_name, safe='')}/{build_number}"

        if start is not None:
            path = f"{base_path}/logText/progressiveText?start={start}"
        else:
            path = f"{base_path}/consoleText"

        result = _api_call(profile, path, accept="text/plain")

        if result.get("ok"):
            log_text = result.get("result", "")
            return {
                "ok": True,
                "data": {
                    "log": log_text,
                    "size": len(log_text) if isinstance(log_text, str) else 0
                }
            }
        return result

    except Exception as e:
        logger.exception("get_build_log failed")
        return {"ok": False, "error": str(e)}


def stop_build(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stop a running build.

    Params:
        job_name (str): Name of the job (required)
        build_number (int/str): Build number (required)
        folder (str): Folder path if job is in a folder (optional)

    Returns:
        message: Confirmation message
    """
    try:
        profile = load_profile(profile_name)

        job_name = params.get("job_name")
        build_number = params.get("build_number")

        if not job_name:
            return {"ok": False, "error": "job_name is required"}
        if build_number is None:
            return {"ok": False, "error": "build_number is required"}

        folder = params.get("folder", "")

        if folder:
            folder_path = "/job/" + "/job/".join(quote(f, safe="") for f in folder.strip("/").split("/"))
            path = f"{folder_path}/job/{quote(job_name, safe='')}/{build_number}/stop"
        else:
            path = f"/job/{quote(job_name, safe='')}/{build_number}/stop"

        result = _api_call(profile, path, method="POST")

        if result.get("ok"):
            return {
                "ok": True,
                "data": {
                    "message": f"Stop requested for build #{build_number} of job '{job_name}'",
                    "job_name": job_name,
                    "build_number": build_number
                }
            }
        return result

    except Exception as e:
        logger.exception("stop_build failed")
        return {"ok": False, "error": str(e)}


def get_queue(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the Jenkins build queue.

    Params:
        None

    Returns:
        items: List of queued build items
    """
    try:
        profile = load_profile(profile_name)

        path = "/queue/api/json"
        result = _api_call(profile, path)

        if result.get("ok") and isinstance(result.get("result"), dict):
            queue = result["result"]
            items = queue.get("items", [])
            return {
                "ok": True,
                "data": {
                    "items": [
                        {
                            "id": item.get("id"),
                            "task_name": item.get("task", {}).get("name"),
                            "task_url": item.get("task", {}).get("url"),
                            "why": item.get("why"),
                            "in_queue_since": item.get("inQueueSince"),
                            "buildable_start_time": item.get("buildableStartMilliseconds"),
                            "blocked": item.get("blocked", False),
                            "stuck": item.get("stuck", False)
                        }
                        for item in items
                    ],
                    "count": len(items)
                }
            }
        return result

    except Exception as e:
        logger.exception("get_queue failed")
        return {"ok": False, "error": str(e)}


def list_views(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all views in Jenkins.

    Params:
        None

    Returns:
        views: List of view objects with name and url
    """
    try:
        profile = load_profile(profile_name)

        path = "/api/json?tree=views[name,url,description]"
        result = _api_call(profile, path)

        if result.get("ok") and isinstance(result.get("result"), dict):
            views = result["result"].get("views", [])
            return {
                "ok": True,
                "data": {
                    "views": [
                        {
                            "name": view.get("name"),
                            "url": view.get("url"),
                            "description": view.get("description")
                        }
                        for view in views
                    ],
                    "count": len(views)
                }
            }
        return result

    except Exception as e:
        logger.exception("list_views failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_jobs": list_jobs,
    "get_job": get_job,
    "build_job": build_job,
    "get_build": get_build,
    "get_build_log": get_build_log,
    "stop_build": stop_build,
    "get_queue": get_queue,
    "list_views": list_views,
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

    logger.info(f"Executing jenkins.{profile}.{action}")
    return ACTIONS[action](profile, params)
