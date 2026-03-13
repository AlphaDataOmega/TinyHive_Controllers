"""Make (Integromat) Controller for TinyHive

A controller for Make (formerly Integromat) automation platform API.
Supports scenario management, execution triggering, and webhook operations.

Method IDs:
  controller.make.{profile}.list_scenarios
  controller.make.{profile}.get_scenario
  controller.make.{profile}.run_scenario
  controller.make.{profile}.list_executions
  controller.make.{profile}.get_execution
  controller.make.{profile}.toggle_scenario
  controller.make.{profile}.list_connections
  controller.make.{profile}.list_hooks

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:

  {
    "team_id": 123456,
    "region": "eu1",
    "token_env": "MAKE_API_TOKEN"
  }

  Fields:
    - team_id: Your Make team/organization ID (required)
    - region: API region - "eu1", "us1", "eu2", etc. (default: "eu1")
    - token_env: Environment variable containing API token (default: "MAKE_API_TOKEN")

Authentication:
  Obtain an API token from Make:
    1. Go to your Make profile settings
    2. Navigate to API section
    3. Generate a new API token
    4. Set it in the environment variable specified by token_env

Dependencies:
  - None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.make")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with Make configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available Make profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# Authentication
# =============================================================================

def _get_api_token(profile: Dict[str, Any]) -> str:
    """Get API token from environment variable."""
    env_var = profile.get("token_env", "MAKE_API_TOKEN")
    token = os.environ.get(env_var, "")
    if not token:
        raise ValueError(
            f"Environment variable '{env_var}' not set. "
            "Obtain a token from Make profile settings > API."
        )
    return token


def _get_base_url(profile: Dict[str, Any]) -> str:
    """Get the Make API base URL for the region."""
    region = profile.get("region", "eu1")
    return f"https://{region}.make.com/api/v2"


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    base_url: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Make API call."""
    url = f"{base_url}{endpoint}"

    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "data": json.loads(response_body)}
            return {"ok": True, "data": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_data.get("error", error_body[:500]))
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Make API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Make API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Scenario Actions
# =============================================================================

def list_scenarios(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all scenarios in the team.

    Params:
        team_id (int): Team/organization ID (default: from profile)
        folder_id (int): Filter by folder ID (optional)
        pg[limit] (int): Number of results to return (optional)
        pg[offset] (int): Offset for pagination (optional)
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    team_id = params.get("team_id", profile.get("team_id"))
    if not team_id:
        return {"ok": False, "error": "team_id required (in profile or params)"}

    query_params = {"teamId": team_id}
    if params.get("folder_id"):
        query_params["folderId"] = params["folder_id"]
    if params.get("pg[limit]"):
        query_params["pg[limit]"] = params["pg[limit]"]
    if params.get("pg[offset]"):
        query_params["pg[offset]"] = params["pg[offset]"]

    endpoint = f"/scenarios?{urlencode(query_params)}"
    result = _api_call(token, base_url, endpoint)

    if result.get("ok") and "data" in result:
        scenarios = result["data"].get("scenarios", result["data"])
        if isinstance(scenarios, list):
            return {
                "ok": True,
                "result": {
                    "scenarios": [
                        {
                            "id": s.get("id"),
                            "name": s.get("name"),
                            "description": s.get("description"),
                            "is_enabled": s.get("isEnabled"),
                            "is_paused": s.get("isPaused"),
                            "created": s.get("created"),
                            "last_edit": s.get("lastEdit"),
                            "scheduling": s.get("scheduling"),
                        }
                        for s in scenarios
                    ],
                    "count": len(scenarios)
                }
            }
        return {"ok": True, "result": result["data"]}
    return result


def get_scenario(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific scenario.

    Params:
        scenario_id (int): Scenario ID (required)
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    scenario_id = params.get("scenario_id")
    if not scenario_id:
        return {"ok": False, "error": "scenario_id required"}

    endpoint = f"/scenarios/{scenario_id}"
    result = _api_call(token, base_url, endpoint)

    if result.get("ok") and "data" in result:
        s = result["data"].get("scenario", result["data"])
        return {
            "ok": True,
            "result": {
                "id": s.get("id"),
                "name": s.get("name"),
                "description": s.get("description"),
                "is_enabled": s.get("isEnabled"),
                "is_paused": s.get("isPaused"),
                "team_id": s.get("teamId"),
                "folder_id": s.get("folderId"),
                "created": s.get("created"),
                "last_edit": s.get("lastEdit"),
                "scheduling": s.get("scheduling"),
                "blueprint": s.get("blueprint"),
            }
        }
    return result


def run_scenario(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trigger a scenario execution.

    Params:
        scenario_id (int): Scenario ID (required)
        data (dict): Input data to pass to the scenario (optional)
        responsive (bool): Wait for execution to complete (default: false)
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    scenario_id = params.get("scenario_id")
    if not scenario_id:
        return {"ok": False, "error": "scenario_id required"}

    payload = {}
    if params.get("data"):
        payload["data"] = params["data"]
    if params.get("responsive"):
        payload["responsive"] = params["responsive"]

    endpoint = f"/scenarios/{scenario_id}/run"
    result = _api_call(token, base_url, endpoint, method="POST", data=payload if payload else None)

    if result.get("ok") and "data" in result:
        execution = result["data"].get("execution", result["data"])
        return {
            "ok": True,
            "result": {
                "execution_id": execution.get("executionId", execution.get("id")),
                "status": execution.get("status"),
                "outputs": execution.get("outputs"),
            }
        }
    return result


def list_executions(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List executions of a scenario.

    Params:
        scenario_id (int): Scenario ID (required)
        pg[limit] (int): Number of results to return (optional)
        pg[offset] (int): Offset for pagination (optional)
        status (str): Filter by status (optional)
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    scenario_id = params.get("scenario_id")
    if not scenario_id:
        return {"ok": False, "error": "scenario_id required"}

    query_params = {}
    if params.get("pg[limit]"):
        query_params["pg[limit]"] = params["pg[limit]"]
    if params.get("pg[offset]"):
        query_params["pg[offset]"] = params["pg[offset]"]
    if params.get("status"):
        query_params["status"] = params["status"]

    query_string = f"?{urlencode(query_params)}" if query_params else ""
    endpoint = f"/scenarios/{scenario_id}/executions{query_string}"
    result = _api_call(token, base_url, endpoint)

    if result.get("ok") and "data" in result:
        executions = result["data"].get("executions", result["data"])
        if isinstance(executions, list):
            return {
                "ok": True,
                "result": {
                    "executions": [
                        {
                            "id": e.get("id"),
                            "status": e.get("status"),
                            "started": e.get("started"),
                            "finished": e.get("finished"),
                            "duration": e.get("duration"),
                            "operations": e.get("operations"),
                            "transfer": e.get("transfer"),
                        }
                        for e in executions
                    ],
                    "count": len(executions)
                }
            }
        return {"ok": True, "result": result["data"]}
    return result


def get_execution(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific execution.

    Params:
        execution_id (int): Execution ID (required)
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    execution_id = params.get("execution_id")
    if not execution_id:
        return {"ok": False, "error": "execution_id required"}

    endpoint = f"/executions/{execution_id}"
    result = _api_call(token, base_url, endpoint)

    if result.get("ok") and "data" in result:
        e = result["data"].get("execution", result["data"])
        return {
            "ok": True,
            "result": {
                "id": e.get("id"),
                "scenario_id": e.get("scenarioId"),
                "status": e.get("status"),
                "started": e.get("started"),
                "finished": e.get("finished"),
                "duration": e.get("duration"),
                "operations": e.get("operations"),
                "transfer": e.get("transfer"),
                "logs": e.get("logs"),
                "errors": e.get("errors"),
            }
        }
    return result


def toggle_scenario(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enable or disable a scenario.

    Params:
        scenario_id (int): Scenario ID (required)
        enabled (bool): True to enable, False to disable (required)
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    scenario_id = params.get("scenario_id")
    if not scenario_id:
        return {"ok": False, "error": "scenario_id required"}

    enabled = params.get("enabled")
    if enabled is None:
        return {"ok": False, "error": "enabled (true/false) required"}

    # Make uses different endpoints for start/stop
    if enabled:
        endpoint = f"/scenarios/{scenario_id}/start"
    else:
        endpoint = f"/scenarios/{scenario_id}/stop"

    result = _api_call(token, base_url, endpoint, method="POST")

    if result.get("ok"):
        return {
            "ok": True,
            "result": {
                "scenario_id": scenario_id,
                "enabled": enabled,
                "status": "started" if enabled else "stopped"
            }
        }
    return result


# =============================================================================
# Connection Actions
# =============================================================================

def list_connections(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all connections in the team.

    Params:
        team_id (int): Team/organization ID (default: from profile)
        pg[limit] (int): Number of results to return (optional)
        pg[offset] (int): Offset for pagination (optional)
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    team_id = params.get("team_id", profile.get("team_id"))
    if not team_id:
        return {"ok": False, "error": "team_id required (in profile or params)"}

    query_params = {"teamId": team_id}
    if params.get("pg[limit]"):
        query_params["pg[limit]"] = params["pg[limit]"]
    if params.get("pg[offset]"):
        query_params["pg[offset]"] = params["pg[offset]"]

    endpoint = f"/connections?{urlencode(query_params)}"
    result = _api_call(token, base_url, endpoint)

    if result.get("ok") and "data" in result:
        connections = result["data"].get("connections", result["data"])
        if isinstance(connections, list):
            return {
                "ok": True,
                "result": {
                    "connections": [
                        {
                            "id": c.get("id"),
                            "name": c.get("name"),
                            "account_name": c.get("accountName"),
                            "account_type": c.get("accountType"),
                            "package_name": c.get("packageName"),
                            "scoped": c.get("scoped"),
                            "created": c.get("created"),
                        }
                        for c in connections
                    ],
                    "count": len(connections)
                }
            }
        return {"ok": True, "result": result["data"]}
    return result


# =============================================================================
# Webhook Actions
# =============================================================================

def list_hooks(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all webhooks in the team.

    Params:
        team_id (int): Team/organization ID (default: from profile)
        pg[limit] (int): Number of results to return (optional)
        pg[offset] (int): Offset for pagination (optional)
    """
    profile = load_profile(profile_name)
    token = _get_api_token(profile)
    base_url = _get_base_url(profile)

    team_id = params.get("team_id", profile.get("team_id"))
    if not team_id:
        return {"ok": False, "error": "team_id required (in profile or params)"}

    query_params = {"teamId": team_id}
    if params.get("pg[limit]"):
        query_params["pg[limit]"] = params["pg[limit]"]
    if params.get("pg[offset]"):
        query_params["pg[offset]"] = params["pg[offset]"]

    endpoint = f"/hooks?{urlencode(query_params)}"
    result = _api_call(token, base_url, endpoint)

    if result.get("ok") and "data" in result:
        hooks = result["data"].get("hooks", result["data"])
        if isinstance(hooks, list):
            return {
                "ok": True,
                "result": {
                    "hooks": [
                        {
                            "id": h.get("id"),
                            "name": h.get("name"),
                            "url": h.get("url"),
                            "type": h.get("type"),
                            "enabled": h.get("enabled"),
                            "scenario_id": h.get("scenarioId"),
                            "created": h.get("created"),
                            "queue_count": h.get("queueCount"),
                        }
                        for h in hooks
                    ],
                    "count": len(hooks)
                }
            }
        return {"ok": True, "result": result["data"]}
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_scenarios": list_scenarios,
    "get_scenario": get_scenario,
    "run_scenario": run_scenario,
    "list_executions": list_executions,
    "get_execution": get_execution,
    "toggle_scenario": toggle_scenario,
    "list_connections": list_connections,
    "list_hooks": list_hooks,
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
        logger.info(f"Executing make.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
