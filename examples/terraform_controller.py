"""Terraform Cloud Controller - Terraform Cloud/Enterprise API integration.

This controller provides integration with Terraform Cloud and Terraform Enterprise
for managing workspaces, runs, and state.

Method IDs:
  controller.terraform.{profile}.list_workspaces
  controller.terraform.{profile}.get_workspace
  controller.terraform.{profile}.create_run
  controller.terraform.{profile}.get_run
  controller.terraform.{profile}.apply_run
  controller.terraform.{profile}.cancel_run
  controller.terraform.{profile}.list_runs
  controller.terraform.{profile}.get_state_version

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:

  {
    "organization": "my-terraform-org",
    "token_env": "TFC_TOKEN"  // Environment variable containing API token
  }

  Optional fields:
  {
    "base_url": "https://app.terraform.io/api/v2",  // For Terraform Enterprise
    "timeout": 60  // Request timeout in seconds
  }

Required Permissions:
  - list_workspaces: Read access to workspaces
  - get_workspace: Read access to workspace
  - create_run: Write access to workspace
  - get_run: Read access to runs
  - apply_run: Apply access to workspace
  - cancel_run: Write access to runs
  - list_runs: Read access to runs
  - get_state_version: Read access to state

Dependencies:
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

logger = logging.getLogger("tinyhive.controller.terraform")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# Terraform Cloud API base URL
DEFAULT_BASE_URL = "https://app.terraform.io/api/v2"
DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with Terraform Cloud configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available Terraform Cloud profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


def _get_token(profile: Dict[str, Any]) -> str:
    """Get API token from environment variable specified in profile."""
    token_env = profile.get("token_env", "TFC_TOKEN")
    token = os.environ.get(token_env, "")
    if not token:
        raise ValueError(
            f"Environment variable '{token_env}' not set. "
            "Set it to your Terraform Cloud API token."
        )
    return token


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Terraform Cloud API call."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/vnd.api+json",
    }

    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "data": json.loads(response_body)}
            return {"ok": True, "data": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            errors = error_data.get("errors", [])
            if errors:
                error_message = "; ".join(
                    err.get("detail", err.get("title", str(err)))
                    for err in errors
                )
            else:
                error_message = error_body[:500]
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Terraform Cloud API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Terraform Cloud API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Workspace Actions
# =============================================================================

def list_workspaces(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List workspaces in the organization.

    Params:
        organization (str): Organization name (default: from profile)
        page_number (int): Page number for pagination (default: 1)
        page_size (int): Number of results per page (default: 20)
        search_name (str): Filter workspaces by name (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("base_url", DEFAULT_BASE_URL)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    organization = params.get("organization", profile.get("organization"))
    if not organization:
        return {"ok": False, "error": "organization required (in profile or params)"}

    query_params = {}
    if params.get("page_number"):
        query_params["page[number]"] = params["page_number"]
    if params.get("page_size"):
        query_params["page[size]"] = params["page_size"]
    if params.get("search_name"):
        query_params["search[name]"] = params["search_name"]

    url = f"{base_url}/organizations/{organization}/workspaces"
    if query_params:
        url += f"?{urlencode(query_params)}"

    result = _api_call(token, url, timeout=timeout)

    if result.get("ok") and "data" in result:
        workspaces_data = result["data"].get("data", [])
        return {
            "ok": True,
            "result": {
                "workspaces": [
                    {
                        "id": ws.get("id"),
                        "name": ws.get("attributes", {}).get("name"),
                        "description": ws.get("attributes", {}).get("description"),
                        "auto_apply": ws.get("attributes", {}).get("auto-apply"),
                        "terraform_version": ws.get("attributes", {}).get("terraform-version"),
                        "working_directory": ws.get("attributes", {}).get("working-directory"),
                        "vcs_repo": ws.get("attributes", {}).get("vcs-repo"),
                        "created_at": ws.get("attributes", {}).get("created-at"),
                        "updated_at": ws.get("attributes", {}).get("updated-at"),
                        "resource_count": ws.get("attributes", {}).get("resource-count"),
                        "locked": ws.get("attributes", {}).get("locked"),
                    }
                    for ws in workspaces_data
                ],
                "pagination": result["data"].get("meta", {}).get("pagination", {}),
            }
        }
    return result


def get_workspace(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific workspace.

    Params:
        organization (str): Organization name (default: from profile)
        workspace_name (str): Workspace name (required)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("base_url", DEFAULT_BASE_URL)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    organization = params.get("organization", profile.get("organization"))
    if not organization:
        return {"ok": False, "error": "organization required (in profile or params)"}

    workspace_name = params.get("workspace_name", "")
    if not workspace_name:
        return {"ok": False, "error": "workspace_name required"}

    url = f"{base_url}/organizations/{organization}/workspaces/{workspace_name}"

    result = _api_call(token, url, timeout=timeout)

    if result.get("ok") and "data" in result:
        ws = result["data"].get("data", {})
        attrs = ws.get("attributes", {})
        return {
            "ok": True,
            "result": {
                "id": ws.get("id"),
                "name": attrs.get("name"),
                "description": attrs.get("description"),
                "auto_apply": attrs.get("auto-apply"),
                "terraform_version": attrs.get("terraform-version"),
                "working_directory": attrs.get("working-directory"),
                "vcs_repo": attrs.get("vcs-repo"),
                "created_at": attrs.get("created-at"),
                "updated_at": attrs.get("updated-at"),
                "resource_count": attrs.get("resource-count"),
                "locked": attrs.get("locked"),
                "execution_mode": attrs.get("execution-mode"),
                "source": attrs.get("source"),
                "source_name": attrs.get("source-name"),
                "source_url": attrs.get("source-url"),
            }
        }
    return result


# =============================================================================
# Run Actions
# =============================================================================

def create_run(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new run in a workspace.

    Params:
        workspace_id (str): Workspace ID (required, e.g., "ws-xxxxx")
        message (str): Message describing the run (optional)
        auto_apply (bool): Whether to auto-apply if plan succeeds (default: false)
        is_destroy (bool): Whether this is a destroy run (default: false)
        target_addrs (list): Resource addresses to target (optional)
        replace_addrs (list): Resource addresses to replace (optional)
        refresh (bool): Whether to refresh state (default: true)
        refresh_only (bool): Whether to only refresh state (default: false)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("base_url", DEFAULT_BASE_URL)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    workspace_id = params.get("workspace_id", "")
    if not workspace_id:
        return {"ok": False, "error": "workspace_id required"}

    # Build the JSON:API payload
    attributes = {}
    if params.get("message"):
        attributes["message"] = params["message"]
    if params.get("auto_apply") is not None:
        attributes["auto-apply"] = params["auto_apply"]
    if params.get("is_destroy") is not None:
        attributes["is-destroy"] = params["is_destroy"]
    if params.get("target_addrs"):
        attributes["target-addrs"] = params["target_addrs"]
    if params.get("replace_addrs"):
        attributes["replace-addrs"] = params["replace_addrs"]
    if params.get("refresh") is not None:
        attributes["refresh"] = params["refresh"]
    if params.get("refresh_only") is not None:
        attributes["refresh-only"] = params["refresh_only"]

    payload = {
        "data": {
            "type": "runs",
            "attributes": attributes,
            "relationships": {
                "workspace": {
                    "data": {
                        "type": "workspaces",
                        "id": workspace_id
                    }
                }
            }
        }
    }

    url = f"{base_url}/runs"
    data = json.dumps(payload).encode("utf-8")

    result = _api_call(token, url, method="POST", data=data, timeout=timeout)

    if result.get("ok") and "data" in result:
        run = result["data"].get("data", {})
        attrs = run.get("attributes", {})
        return {
            "ok": True,
            "result": {
                "id": run.get("id"),
                "status": attrs.get("status"),
                "message": attrs.get("message"),
                "is_destroy": attrs.get("is-destroy"),
                "auto_apply": attrs.get("auto-apply"),
                "created_at": attrs.get("created-at"),
                "plan_only": attrs.get("plan-only"),
                "source": attrs.get("source"),
            }
        }
    return result


def get_run(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific run.

    Params:
        run_id (str): Run ID (required, e.g., "run-xxxxx")
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("base_url", DEFAULT_BASE_URL)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    run_id = params.get("run_id", "")
    if not run_id:
        return {"ok": False, "error": "run_id required"}

    url = f"{base_url}/runs/{run_id}"

    result = _api_call(token, url, timeout=timeout)

    if result.get("ok") and "data" in result:
        run = result["data"].get("data", {})
        attrs = run.get("attributes", {})
        return {
            "ok": True,
            "result": {
                "id": run.get("id"),
                "status": attrs.get("status"),
                "message": attrs.get("message"),
                "is_destroy": attrs.get("is-destroy"),
                "auto_apply": attrs.get("auto-apply"),
                "created_at": attrs.get("created-at"),
                "has_changes": attrs.get("has-changes"),
                "resource_additions": attrs.get("resource-additions"),
                "resource_changes": attrs.get("resource-changes"),
                "resource_destructions": attrs.get("resource-destructions"),
                "status_timestamps": attrs.get("status-timestamps"),
                "permissions": attrs.get("permissions"),
                "actions": attrs.get("actions"),
                "source": attrs.get("source"),
                "terraform_version": attrs.get("terraform-version"),
            }
        }
    return result


def apply_run(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply a run that is waiting for confirmation.

    Params:
        run_id (str): Run ID (required, e.g., "run-xxxxx")
        comment (str): Comment explaining the apply (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("base_url", DEFAULT_BASE_URL)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    run_id = params.get("run_id", "")
    if not run_id:
        return {"ok": False, "error": "run_id required"}

    payload = {}
    if params.get("comment"):
        payload["comment"] = params["comment"]

    url = f"{base_url}/runs/{run_id}/actions/apply"
    data = json.dumps(payload).encode("utf-8") if payload else None

    result = _api_call(token, url, method="POST", data=data, timeout=timeout)

    if result.get("ok"):
        return {
            "ok": True,
            "result": {
                "run_id": run_id,
                "action": "apply",
                "status": "applied"
            }
        }
    return result


def cancel_run(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cancel a run that is currently planning or applying.

    Params:
        run_id (str): Run ID (required, e.g., "run-xxxxx")
        comment (str): Comment explaining the cancellation (optional)
        force (bool): Force cancel even if currently applying (default: false)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("base_url", DEFAULT_BASE_URL)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    run_id = params.get("run_id", "")
    if not run_id:
        return {"ok": False, "error": "run_id required"}

    payload = {}
    if params.get("comment"):
        payload["comment"] = params["comment"]

    # Use force-cancel endpoint if force is True
    action = "force-cancel" if params.get("force") else "cancel"
    url = f"{base_url}/runs/{run_id}/actions/{action}"
    data = json.dumps(payload).encode("utf-8") if payload else None

    result = _api_call(token, url, method="POST", data=data, timeout=timeout)

    if result.get("ok"):
        return {
            "ok": True,
            "result": {
                "run_id": run_id,
                "action": action,
                "status": "cancelled"
            }
        }
    return result


def list_runs(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List runs for a workspace.

    Params:
        workspace_id (str): Workspace ID (required, e.g., "ws-xxxxx")
        page_number (int): Page number for pagination (default: 1)
        page_size (int): Number of results per page (default: 20)
        status (str): Filter by status (optional)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("base_url", DEFAULT_BASE_URL)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    workspace_id = params.get("workspace_id", "")
    if not workspace_id:
        return {"ok": False, "error": "workspace_id required"}

    query_params = {}
    if params.get("page_number"):
        query_params["page[number]"] = params["page_number"]
    if params.get("page_size"):
        query_params["page[size]"] = params["page_size"]
    if params.get("status"):
        query_params["filter[status]"] = params["status"]

    url = f"{base_url}/workspaces/{workspace_id}/runs"
    if query_params:
        url += f"?{urlencode(query_params)}"

    result = _api_call(token, url, timeout=timeout)

    if result.get("ok") and "data" in result:
        runs_data = result["data"].get("data", [])
        return {
            "ok": True,
            "result": {
                "runs": [
                    {
                        "id": run.get("id"),
                        "status": run.get("attributes", {}).get("status"),
                        "message": run.get("attributes", {}).get("message"),
                        "is_destroy": run.get("attributes", {}).get("is-destroy"),
                        "created_at": run.get("attributes", {}).get("created-at"),
                        "has_changes": run.get("attributes", {}).get("has-changes"),
                        "resource_additions": run.get("attributes", {}).get("resource-additions"),
                        "resource_changes": run.get("attributes", {}).get("resource-changes"),
                        "resource_destructions": run.get("attributes", {}).get("resource-destructions"),
                        "source": run.get("attributes", {}).get("source"),
                    }
                    for run in runs_data
                ],
                "pagination": result["data"].get("meta", {}).get("pagination", {}),
            }
        }
    return result


# =============================================================================
# State Actions
# =============================================================================

def get_state_version(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the current state version for a workspace.

    Params:
        workspace_id (str): Workspace ID (required, e.g., "ws-xxxxx")
        include_outputs (bool): Include state outputs (default: true)
    """
    profile = load_profile(profile_name)
    token = _get_token(profile)
    base_url = profile.get("base_url", DEFAULT_BASE_URL)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    workspace_id = params.get("workspace_id", "")
    if not workspace_id:
        return {"ok": False, "error": "workspace_id required"}

    url = f"{base_url}/workspaces/{workspace_id}/current-state-version"

    # Optionally include outputs
    if params.get("include_outputs", True):
        url += "?include=outputs"

    result = _api_call(token, url, timeout=timeout)

    if result.get("ok") and "data" in result:
        state = result["data"].get("data", {})
        attrs = state.get("attributes", {})

        # Extract outputs if included
        outputs = []
        included = result["data"].get("included", [])
        for item in included:
            if item.get("type") == "state-version-outputs":
                output_attrs = item.get("attributes", {})
                outputs.append({
                    "name": output_attrs.get("name"),
                    "value": output_attrs.get("value"),
                    "sensitive": output_attrs.get("sensitive"),
                    "type": output_attrs.get("type"),
                })

        return {
            "ok": True,
            "result": {
                "id": state.get("id"),
                "serial": attrs.get("serial"),
                "terraform_version": attrs.get("terraform-version"),
                "created_at": attrs.get("created-at"),
                "size": attrs.get("size"),
                "hosted_state_download_url": attrs.get("hosted-state-download-url"),
                "hosted_json_state_download_url": attrs.get("hosted-json-state-download-url"),
                "resources_processed": attrs.get("resources-processed"),
                "modules": attrs.get("modules"),
                "providers": attrs.get("providers"),
                "resources": attrs.get("resources"),
                "outputs": outputs if outputs else None,
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_workspaces": list_workspaces,
    "get_workspace": get_workspace,
    "create_run": create_run,
    "get_run": get_run,
    "apply_run": apply_run,
    "cancel_run": cancel_run,
    "list_runs": list_runs,
    "get_state_version": get_state_version,
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
        logger.info(f"Executing terraform.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
