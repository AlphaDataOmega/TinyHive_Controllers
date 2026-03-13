"""
Grafana Controller for TinyHive

Provides integration with Grafana API for dashboard and data source management.

Method IDs:
  controller.grafana.{profile}.list_dashboards
  controller.grafana.{profile}.get_dashboard
  controller.grafana.{profile}.create_dashboard
  controller.grafana.{profile}.delete_dashboard
  controller.grafana.{profile}.list_datasources
  controller.grafana.{profile}.get_datasource
  controller.grafana.{profile}.list_alerts
  controller.grafana.{profile}.create_annotation

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "grafana_url": "https://grafana.example.com",
    "api_key_env": "GRAFANA_API_KEY"
}

Required Permissions:
--------------------
- list_dashboards: Viewer
- get_dashboard: Viewer
- create_dashboard: Editor
- delete_dashboard: Editor
- list_datasources: Viewer (Admin for full details)
- get_datasource: Viewer (Admin for full details)
- list_alerts: Viewer
- create_annotation: Editor

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
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.grafana")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

DEFAULT_TIMEOUT = 30


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
    """Get the API key from environment variable specified in profile."""
    env_var = profile.get("api_key_env", "GRAFANA_API_KEY")
    api_key = os.environ.get(env_var)
    if not api_key:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return api_key


def _get_base_url(profile: Dict[str, Any]) -> str:
    """Get the Grafana base URL from profile."""
    grafana_url = profile.get("grafana_url")
    if not grafana_url:
        raise ValueError("grafana_url not set in profile")
    return grafana_url.rstrip("/")


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    api_key: str,
    base_url: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Grafana API call."""
    url = f"{base_url}/api{endpoint}"

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
                return {"ok": True, "data": json.loads(response_body)}
            return {"ok": True, "data": {}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Grafana API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Grafana API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Dashboard Actions
# =============================================================================

def list_dashboards(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search dashboards.

    Params:
        query (str): Search query string (optional)
        tag (str or list): Filter by tag(s) (optional)
        type (str): Filter by type: 'dash-db' or 'dash-folder' (optional)
        folderIds (list): Filter by folder IDs (optional)
        starred (bool): Filter starred dashboards only (optional)
        limit (int): Max results to return (default: 100)
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        base_url = _get_base_url(profile)

        query_params = []

        if params.get("query"):
            query_params.append(f"query={quote(params['query'])}")

        tags = params.get("tag")
        if tags:
            if isinstance(tags, str):
                tags = [tags]
            for tag in tags:
                query_params.append(f"tag={quote(tag)}")

        if params.get("type"):
            query_params.append(f"type={quote(params['type'])}")

        folder_ids = params.get("folderIds")
        if folder_ids:
            for fid in folder_ids:
                query_params.append(f"folderIds={fid}")

        if params.get("starred"):
            query_params.append("starred=true")

        limit = params.get("limit", 100)
        query_params.append(f"limit={limit}")

        endpoint = "/search"
        if query_params:
            endpoint += "?" + "&".join(query_params)

        result = _api_call(api_key, base_url, endpoint)

        if result.get("ok"):
            dashboards = result.get("data", [])
            return {
                "ok": True,
                "result": {
                    "dashboards": [
                        {
                            "uid": d.get("uid"),
                            "title": d.get("title"),
                            "uri": d.get("uri"),
                            "url": d.get("url"),
                            "type": d.get("type"),
                            "tags": d.get("tags", []),
                            "isStarred": d.get("isStarred", False),
                            "folderId": d.get("folderId"),
                            "folderTitle": d.get("folderTitle"),
                        }
                        for d in dashboards
                    ],
                    "count": len(dashboards)
                }
            }
        return result
    except Exception as e:
        logger.exception("list_dashboards failed")
        return {"ok": False, "error": str(e)}


def get_dashboard(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a dashboard by UID.

    Params:
        uid (str): Dashboard UID (required)
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        base_url = _get_base_url(profile)

        uid = params.get("uid")
        if not uid:
            return {"ok": False, "error": "uid is required"}

        endpoint = f"/dashboards/uid/{quote(uid)}"
        result = _api_call(api_key, base_url, endpoint)

        if result.get("ok"):
            data = result.get("data", {})
            return {
                "ok": True,
                "result": {
                    "dashboard": data.get("dashboard"),
                    "meta": data.get("meta"),
                }
            }
        return result
    except Exception as e:
        logger.exception("get_dashboard failed")
        return {"ok": False, "error": str(e)}


def create_dashboard(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create or update a dashboard.

    Params:
        dashboard (dict): Dashboard model (required)
            Must include 'title'. Include 'uid' for updates.
            Set 'id' to null for new dashboards.
        folderId (int): Folder ID to save in (optional, default: General folder)
        folderUid (str): Folder UID to save in (optional, alternative to folderId)
        overwrite (bool): Overwrite existing dashboard (default: False)
        message (str): Commit message for versioning (optional)
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        base_url = _get_base_url(profile)

        dashboard = params.get("dashboard")
        if not dashboard:
            return {"ok": False, "error": "dashboard is required"}

        if not dashboard.get("title"):
            return {"ok": False, "error": "dashboard.title is required"}

        payload = {
            "dashboard": dashboard,
            "overwrite": params.get("overwrite", False),
        }

        if params.get("folderId") is not None:
            payload["folderId"] = params["folderId"]

        if params.get("folderUid"):
            payload["folderUid"] = params["folderUid"]

        if params.get("message"):
            payload["message"] = params["message"]

        result = _api_call(api_key, base_url, "/dashboards/db", method="POST", data=payload)

        if result.get("ok"):
            data = result.get("data", {})
            return {
                "ok": True,
                "result": {
                    "id": data.get("id"),
                    "uid": data.get("uid"),
                    "url": data.get("url"),
                    "status": data.get("status"),
                    "version": data.get("version"),
                    "slug": data.get("slug"),
                }
            }
        return result
    except Exception as e:
        logger.exception("create_dashboard failed")
        return {"ok": False, "error": str(e)}


def delete_dashboard(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a dashboard by UID.

    Params:
        uid (str): Dashboard UID (required)
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        base_url = _get_base_url(profile)

        uid = params.get("uid")
        if not uid:
            return {"ok": False, "error": "uid is required"}

        endpoint = f"/dashboards/uid/{quote(uid)}"
        result = _api_call(api_key, base_url, endpoint, method="DELETE")

        if result.get("ok"):
            data = result.get("data", {})
            return {
                "ok": True,
                "result": {
                    "title": data.get("title"),
                    "message": data.get("message", "Dashboard deleted"),
                    "id": data.get("id"),
                }
            }
        return result
    except Exception as e:
        logger.exception("delete_dashboard failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Data Source Actions
# =============================================================================

def list_datasources(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all data sources.

    Params:
        None
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        base_url = _get_base_url(profile)

        result = _api_call(api_key, base_url, "/datasources")

        if result.get("ok"):
            datasources = result.get("data", [])
            return {
                "ok": True,
                "result": {
                    "datasources": [
                        {
                            "id": ds.get("id"),
                            "uid": ds.get("uid"),
                            "name": ds.get("name"),
                            "type": ds.get("type"),
                            "typeName": ds.get("typeName"),
                            "url": ds.get("url"),
                            "access": ds.get("access"),
                            "isDefault": ds.get("isDefault", False),
                            "database": ds.get("database"),
                            "readOnly": ds.get("readOnly", False),
                        }
                        for ds in datasources
                    ],
                    "count": len(datasources)
                }
            }
        return result
    except Exception as e:
        logger.exception("list_datasources failed")
        return {"ok": False, "error": str(e)}


def get_datasource(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a data source by ID or name.

    Params:
        id (int): Data source ID (optional, use this or name)
        name (str): Data source name (optional, use this or id)
        uid (str): Data source UID (optional, use this or id/name)
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        base_url = _get_base_url(profile)

        ds_id = params.get("id")
        ds_name = params.get("name")
        ds_uid = params.get("uid")

        if ds_id:
            endpoint = f"/datasources/{ds_id}"
        elif ds_uid:
            endpoint = f"/datasources/uid/{quote(ds_uid)}"
        elif ds_name:
            endpoint = f"/datasources/name/{quote(ds_name)}"
        else:
            return {"ok": False, "error": "id, uid, or name is required"}

        result = _api_call(api_key, base_url, endpoint)

        if result.get("ok"):
            ds = result.get("data", {})
            return {
                "ok": True,
                "result": {
                    "id": ds.get("id"),
                    "uid": ds.get("uid"),
                    "name": ds.get("name"),
                    "type": ds.get("type"),
                    "typeName": ds.get("typeName"),
                    "url": ds.get("url"),
                    "access": ds.get("access"),
                    "isDefault": ds.get("isDefault", False),
                    "database": ds.get("database"),
                    "basicAuth": ds.get("basicAuth", False),
                    "jsonData": ds.get("jsonData", {}),
                    "readOnly": ds.get("readOnly", False),
                }
            }
        return result
    except Exception as e:
        logger.exception("get_datasource failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Alert Actions
# =============================================================================

def list_alerts(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List alert rules.

    Params:
        dashboard_id (int): Filter by dashboard ID (optional)
        panel_id (int): Filter by panel ID (optional)
        query (str): Filter by alert name (optional)
        state (str): Filter by state: 'all', 'no_data', 'paused', 'alerting', 'ok', 'pending' (optional)
        limit (int): Max results (optional)
        folder_id (list): Filter by folder IDs (optional)
        dashboard_query (str): Filter by dashboard name (optional)
        dashboard_tag (str or list): Filter by dashboard tag(s) (optional)
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        base_url = _get_base_url(profile)

        query_params = []

        if params.get("dashboard_id"):
            query_params.append(f"dashboardId={params['dashboard_id']}")

        if params.get("panel_id"):
            query_params.append(f"panelId={params['panel_id']}")

        if params.get("query"):
            query_params.append(f"query={quote(params['query'])}")

        if params.get("state"):
            query_params.append(f"state={quote(params['state'])}")

        if params.get("limit"):
            query_params.append(f"limit={params['limit']}")

        folder_ids = params.get("folder_id")
        if folder_ids:
            if isinstance(folder_ids, int):
                folder_ids = [folder_ids]
            for fid in folder_ids:
                query_params.append(f"folderId={fid}")

        if params.get("dashboard_query"):
            query_params.append(f"dashboardQuery={quote(params['dashboard_query'])}")

        tags = params.get("dashboard_tag")
        if tags:
            if isinstance(tags, str):
                tags = [tags]
            for tag in tags:
                query_params.append(f"dashboardTag={quote(tag)}")

        endpoint = "/alerts"
        if query_params:
            endpoint += "?" + "&".join(query_params)

        result = _api_call(api_key, base_url, endpoint)

        if result.get("ok"):
            alerts = result.get("data", [])
            return {
                "ok": True,
                "result": {
                    "alerts": [
                        {
                            "id": a.get("id"),
                            "dashboardId": a.get("dashboardId"),
                            "dashboardUid": a.get("dashboardUid"),
                            "dashboardSlug": a.get("dashboardSlug"),
                            "panelId": a.get("panelId"),
                            "name": a.get("name"),
                            "state": a.get("state"),
                            "newStateDate": a.get("newStateDate"),
                            "evalDate": a.get("evalDate"),
                            "evalData": a.get("evalData"),
                            "executionError": a.get("executionError"),
                            "url": a.get("url"),
                        }
                        for a in alerts
                    ],
                    "count": len(alerts)
                }
            }
        return result
    except Exception as e:
        logger.exception("list_alerts failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Annotation Actions
# =============================================================================

def create_annotation(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an annotation.

    Params:
        dashboardId (int): Dashboard ID (optional, for dashboard annotation)
        dashboardUID (str): Dashboard UID (optional, alternative to dashboardId)
        panelId (int): Panel ID (optional, for panel annotation)
        time (int): Epoch time in milliseconds (required)
        timeEnd (int): End epoch time in milliseconds (optional, for region annotation)
        text (str): Annotation text/description (required)
        tags (list): List of tags (optional)
    """
    try:
        profile = load_profile(profile_name)
        api_key = _get_api_key(profile)
        base_url = _get_base_url(profile)

        time_val = params.get("time")
        text = params.get("text")

        if time_val is None:
            return {"ok": False, "error": "time is required"}
        if not text:
            return {"ok": False, "error": "text is required"}

        payload = {
            "time": time_val,
            "text": text,
        }

        if params.get("dashboardId") is not None:
            payload["dashboardId"] = params["dashboardId"]

        if params.get("dashboardUID"):
            payload["dashboardUID"] = params["dashboardUID"]

        if params.get("panelId") is not None:
            payload["panelId"] = params["panelId"]

        if params.get("timeEnd") is not None:
            payload["timeEnd"] = params["timeEnd"]

        if params.get("tags"):
            payload["tags"] = params["tags"]

        result = _api_call(api_key, base_url, "/annotations", method="POST", data=payload)

        if result.get("ok"):
            data = result.get("data", {})
            return {
                "ok": True,
                "result": {
                    "id": data.get("id"),
                    "message": data.get("message", "Annotation created"),
                }
            }
        return result
    except Exception as e:
        logger.exception("create_annotation failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_dashboards": list_dashboards,
    "get_dashboard": get_dashboard,
    "create_dashboard": create_dashboard,
    "delete_dashboard": delete_dashboard,
    "list_datasources": list_datasources,
    "get_datasource": get_datasource,
    "list_alerts": list_alerts,
    "create_annotation": create_annotation,
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

    logger.info(f"Executing grafana.{profile}.{action}")
    return ACTIONS[action](profile, params)
