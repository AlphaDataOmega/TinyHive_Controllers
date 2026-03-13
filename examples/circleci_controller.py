"""CircleCI Controller — Pipelines, Workflows, and Jobs integration.

This is a TinyHive controller for CircleCI API v2.
Requires a CircleCI API token set in environment.

Method IDs:
  controller.circleci.{profile}.list_pipelines
  controller.circleci.{profile}.get_pipeline
  controller.circleci.{profile}.trigger_pipeline
  controller.circleci.{profile}.list_workflows
  controller.circleci.{profile}.get_workflow
  controller.circleci.{profile}.list_jobs
  controller.circleci.{profile}.get_job_artifacts
  controller.circleci.{profile}.cancel_workflow

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:
  {
    "token_env": "CIRCLECI_TOKEN",  // Environment variable containing API token
    "default_org_slug": "gh/myorg",  // Optional: default org slug (e.g., "gh/myorg" or "bb/myorg")
    "default_project_slug": "gh/myorg/myrepo"  // Optional: default project slug
  }

Dependencies:
  - None (Python stdlib only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode

log = logging.getLogger("tinyhive.controller.circleci")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

BASE_URL = "https://circleci.com/api/v2"


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'")
    return json.loads(path.read_text())


def _get_access_token(profile: Dict[str, Any]) -> str:
    """Get CircleCI API token from environment."""
    env_var = profile.get("token_env", "CIRCLECI_TOKEN")
    token = os.environ.get(env_var, "")
    if not token:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return token


def _api_call(
    token: str,
    url: str,
    method: str = "GET",
    data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Make a CircleCI API call."""
    headers = {
        "Circle-Token": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    body = json.dumps(data).encode("utf-8") if data else None

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=30) as response:
            response_data = response.read().decode("utf-8")
            if response_data:
                return {"ok": True, "data": json.loads(response_data)}
            return {"ok": True, "data": None}
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(body)
            error_message = error_data.get("message", body[:500])
        except json.JSONDecodeError:
            error_message = body[:500]
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Pipeline Actions
# ---------------------------------------------------------------------------

def list_pipelines(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List pipelines for a project.

    Params:
        - org_slug: Organization slug (e.g., "gh/myorg") (default: from profile)
        - project_slug: Project slug (e.g., "gh/myorg/myrepo") (required if org_slug not provided)
        - branch: Filter by branch name (optional)
        - page_token: Page token for pagination (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    project_slug = params.get("project_slug", profile.get("default_project_slug"))
    org_slug = params.get("org_slug", profile.get("default_org_slug"))
    branch = params.get("branch")
    page_token = params.get("page_token")

    if project_slug:
        # List pipelines for a specific project
        url = f"{BASE_URL}/project/{project_slug}/pipeline"
    elif org_slug:
        # List pipelines for an organization
        url = f"{BASE_URL}/pipeline"
    else:
        return {"ok": False, "error": "project_slug or org_slug is required"}

    query_params = {}
    if branch:
        query_params["branch"] = branch
    if page_token:
        query_params["page-token"] = page_token
    if org_slug and not project_slug:
        query_params["org-slug"] = org_slug

    if query_params:
        url = f"{url}?{urlencode(query_params)}"

    return _api_call(token, url)


def get_pipeline(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get a specific pipeline by ID.

    Params:
        - pipeline_id: The pipeline ID (UUID) (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    pipeline_id = params.get("pipeline_id")
    if not pipeline_id:
        return {"ok": False, "error": "pipeline_id is required"}

    url = f"{BASE_URL}/pipeline/{pipeline_id}"

    return _api_call(token, url)


def trigger_pipeline(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Trigger a new pipeline for a project.

    Params:
        - org_slug: Organization slug (e.g., "gh/myorg") (default: from profile)
        - project_slug: Project slug (e.g., "gh/myorg/myrepo") (default: from profile)
        - branch: Branch to build (optional, uses default branch if not specified)
        - tag: Tag to build (optional, mutually exclusive with branch)
        - parameters: Pipeline parameters as a dict (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    project_slug = params.get("project_slug", profile.get("default_project_slug"))
    if not project_slug:
        return {"ok": False, "error": "project_slug is required"}

    branch = params.get("branch")
    tag = params.get("tag")
    parameters = params.get("parameters")

    if branch and tag:
        return {"ok": False, "error": "Cannot specify both branch and tag"}

    url = f"{BASE_URL}/project/{project_slug}/pipeline"

    request_data = {}
    if branch:
        request_data["branch"] = branch
    if tag:
        request_data["tag"] = tag
    if parameters:
        request_data["parameters"] = parameters

    return _api_call(token, url, method="POST", data=request_data if request_data else None)


# ---------------------------------------------------------------------------
# Workflow Actions
# ---------------------------------------------------------------------------

def list_workflows(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List workflows for a pipeline.

    Params:
        - pipeline_id: The pipeline ID (UUID) (required)
        - page_token: Page token for pagination (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    pipeline_id = params.get("pipeline_id")
    if not pipeline_id:
        return {"ok": False, "error": "pipeline_id is required"}

    page_token = params.get("page_token")

    url = f"{BASE_URL}/pipeline/{pipeline_id}/workflow"

    query_params = {}
    if page_token:
        query_params["page-token"] = page_token

    if query_params:
        url = f"{url}?{urlencode(query_params)}"

    return _api_call(token, url)


def get_workflow(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get a specific workflow by ID.

    Params:
        - workflow_id: The workflow ID (UUID) (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    workflow_id = params.get("workflow_id")
    if not workflow_id:
        return {"ok": False, "error": "workflow_id is required"}

    url = f"{BASE_URL}/workflow/{workflow_id}"

    return _api_call(token, url)


def cancel_workflow(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Cancel a running workflow.

    Params:
        - workflow_id: The workflow ID (UUID) (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    workflow_id = params.get("workflow_id")
    if not workflow_id:
        return {"ok": False, "error": "workflow_id is required"}

    url = f"{BASE_URL}/workflow/{workflow_id}/cancel"

    return _api_call(token, url, method="POST")


# ---------------------------------------------------------------------------
# Job Actions
# ---------------------------------------------------------------------------

def list_jobs(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List jobs in a workflow.

    Params:
        - workflow_id: The workflow ID (UUID) (required)
        - page_token: Page token for pagination (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    workflow_id = params.get("workflow_id")
    if not workflow_id:
        return {"ok": False, "error": "workflow_id is required"}

    page_token = params.get("page_token")

    url = f"{BASE_URL}/workflow/{workflow_id}/job"

    query_params = {}
    if page_token:
        query_params["page-token"] = page_token

    if query_params:
        url = f"{url}?{urlencode(query_params)}"

    return _api_call(token, url)


def get_job_artifacts(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get artifacts for a job.

    Params:
        - project_slug: Project slug (e.g., "gh/myorg/myrepo") (default: from profile)
        - job_number: The job number (required)
        - page_token: Page token for pagination (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    project_slug = params.get("project_slug", profile.get("default_project_slug"))
    if not project_slug:
        return {"ok": False, "error": "project_slug is required"}

    job_number = params.get("job_number")
    if not job_number:
        return {"ok": False, "error": "job_number is required"}

    page_token = params.get("page_token")

    url = f"{BASE_URL}/project/{project_slug}/{job_number}/artifacts"

    query_params = {}
    if page_token:
        query_params["page-token"] = page_token

    if query_params:
        url = f"{url}?{urlencode(query_params)}"

    return _api_call(token, url)


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

ACTIONS = {
    "list_pipelines": list_pipelines,
    "get_pipeline": get_pipeline,
    "trigger_pipeline": trigger_pipeline,
    "list_workflows": list_workflows,
    "get_workflow": get_workflow,
    "list_jobs": list_jobs,
    "get_job_artifacts": get_job_artifacts,
    "cancel_workflow": cancel_workflow,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """Dispatch an action by name with a profile."""
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action '{action}'"}
    return ACTIONS[action](profile, params)
