"""Figma Controller for TinyHive

A controller for integrating with the Figma REST API.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Figma profile:
{
    "token_env": "FIGMA_ACCESS_TOKEN"
}

Required Scopes:
----------------
- files:read          - For get_file, get_file_nodes, get_images
- file_comments:read  - For get_comments
- file_comments:write - For post_comment
- projects:read       - For list_projects, list_project_files
- library_read        - For get_team_components

Dependencies:
------------
- None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.figma")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Figma API base URL
FIGMA_API_BASE = "https://api.figma.com/v1"

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


def _get_token(profile: Dict[str, Any]) -> str:
    """Get the Figma access token from environment variable."""
    token_env = profile.get("token_env", "FIGMA_ACCESS_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(
            f"Environment variable '{token_env}' not set. "
            "Set your Figma access token in this environment variable."
        )
    return token


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    token: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    query_params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated Figma API call.

    Args:
        token: Figma access token
        endpoint: API endpoint (e.g., 'files/abc123')
        method: HTTP method (GET, POST, etc.)
        data: Request payload for POST requests
        query_params: URL query parameters
        timeout: Request timeout in seconds

    Returns:
        Response dict with 'ok' field and result/error
    """
    url = f"{FIGMA_API_BASE}/{endpoint}"

    # Add query parameters if provided
    if query_params:
        # Filter out None values
        filtered_params = {k: v for k, v in query_params.items() if v is not None}
        if filtered_params:
            url = f"{url}?{urlencode(filtered_params)}"

    headers = {
        "X-Figma-Token": token,
        "Content-Type": "application/json",
    }

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            result = json.loads(response_body)
            return {"ok": True, "result": result}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("message", error_json.get("err", error_body[:500]))
        except json.JSONDecodeError:
            error_msg = error_body[:500]
        logger.error("Figma HTTP error %d: %s", e.code, error_msg)
        return {"ok": False, "error": f"HTTP {e.code}: {error_msg}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Figma API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def get_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a Figma file's data.

    Params:
        file_key (str): The file key (from Figma URL) (required)
        node_ids (str): Comma-separated list of node IDs to retrieve (optional)
        depth (int): Depth of the node tree to retrieve (optional)
        geometry (str): Set to 'paths' to include vector paths (optional)
        plugin_data (str): Plugin ID to include plugin data (optional)
        branch_data (bool): Include branch metadata (optional)

    Returns:
        ok (bool): Success status
        result (dict): File data including document, components, styles, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        file_key = params.get("file_key")
        if not file_key:
            return {"ok": False, "error": "file_key is required"}

        query_params = {}
        if params.get("node_ids"):
            query_params["ids"] = params["node_ids"]
        if params.get("depth") is not None:
            query_params["depth"] = params["depth"]
        if params.get("geometry"):
            query_params["geometry"] = params["geometry"]
        if params.get("plugin_data"):
            query_params["plugin_data"] = params["plugin_data"]
        if params.get("branch_data"):
            query_params["branch_data"] = "true"

        return _api_call(token, f"files/{file_key}", query_params=query_params)

    except Exception as e:
        logger.exception("get_file failed")
        return {"ok": False, "error": str(e)}


def get_file_nodes(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get specific nodes from a Figma file.

    Params:
        file_key (str): The file key (from Figma URL) (required)
        node_ids (str): Comma-separated list of node IDs to retrieve (required)
        depth (int): Depth of the node tree to retrieve (optional)
        geometry (str): Set to 'paths' to include vector paths (optional)
        plugin_data (str): Plugin ID to include plugin data (optional)

    Returns:
        ok (bool): Success status
        result (dict): Nodes data with 'nodes' object keyed by node ID
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        file_key = params.get("file_key")
        node_ids = params.get("node_ids")

        if not file_key:
            return {"ok": False, "error": "file_key is required"}
        if not node_ids:
            return {"ok": False, "error": "node_ids is required"}

        query_params = {"ids": node_ids}
        if params.get("depth") is not None:
            query_params["depth"] = params["depth"]
        if params.get("geometry"):
            query_params["geometry"] = params["geometry"]
        if params.get("plugin_data"):
            query_params["plugin_data"] = params["plugin_data"]

        return _api_call(token, f"files/{file_key}/nodes", query_params=query_params)

    except Exception as e:
        logger.exception("get_file_nodes failed")
        return {"ok": False, "error": str(e)}


def get_images(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Export images from a Figma file.

    Params:
        file_key (str): The file key (from Figma URL) (required)
        node_ids (str): Comma-separated list of node IDs to export (required)
        format (str): Image format: jpg, png, svg, pdf (default: png)
        scale (float): Scale factor 0.01-4 (default: 1)
        svg_include_id (bool): Include id attribute in SVG (optional)
        svg_simplify_stroke (bool): Simplify strokes in SVG (optional)
        use_absolute_bounds (bool): Use full dimensions for exports (optional)
        version (str): File version ID to export from (optional)

    Returns:
        ok (bool): Success status
        result (dict): Images dict with 'images' object keyed by node ID
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        file_key = params.get("file_key")
        node_ids = params.get("node_ids")

        if not file_key:
            return {"ok": False, "error": "file_key is required"}
        if not node_ids:
            return {"ok": False, "error": "node_ids is required"}

        query_params = {"ids": node_ids}

        img_format = params.get("format", "png")
        if img_format not in ("jpg", "png", "svg", "pdf"):
            return {"ok": False, "error": "format must be one of: jpg, png, svg, pdf"}
        query_params["format"] = img_format

        if params.get("scale") is not None:
            scale = float(params["scale"])
            if scale < 0.01 or scale > 4:
                return {"ok": False, "error": "scale must be between 0.01 and 4"}
            query_params["scale"] = scale

        if params.get("svg_include_id"):
            query_params["svg_include_id"] = "true"
        if params.get("svg_simplify_stroke"):
            query_params["svg_simplify_stroke"] = "true"
        if params.get("use_absolute_bounds"):
            query_params["use_absolute_bounds"] = "true"
        if params.get("version"):
            query_params["version"] = params["version"]

        return _api_call(token, f"images/{file_key}", query_params=query_params)

    except Exception as e:
        logger.exception("get_images failed")
        return {"ok": False, "error": str(e)}


def get_comments(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get comments on a Figma file.

    Params:
        file_key (str): The file key (from Figma URL) (required)
        as_md (bool): Return comments as markdown (optional)

    Returns:
        ok (bool): Success status
        result (dict): Comments data with 'comments' array
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        file_key = params.get("file_key")
        if not file_key:
            return {"ok": False, "error": "file_key is required"}

        query_params = {}
        if params.get("as_md"):
            query_params["as_md"] = "true"

        return _api_call(token, f"files/{file_key}/comments", query_params=query_params)

    except Exception as e:
        logger.exception("get_comments failed")
        return {"ok": False, "error": str(e)}


def post_comment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post a comment on a Figma file.

    Params:
        file_key (str): The file key (from Figma URL) (required)
        message (str): The comment text (required)
        client_meta (dict): Position data with 'x', 'y' coordinates or
                           'node_id' and 'node_offset' (optional)
        comment_id (str): Parent comment ID for replies (optional)

    Returns:
        ok (bool): Success status
        result (dict): Created comment data
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        file_key = params.get("file_key")
        message = params.get("message")

        if not file_key:
            return {"ok": False, "error": "file_key is required"}
        if not message:
            return {"ok": False, "error": "message is required"}

        data = {"message": message}

        if params.get("client_meta"):
            data["client_meta"] = params["client_meta"]
        if params.get("comment_id"):
            data["comment_id"] = params["comment_id"]

        return _api_call(token, f"files/{file_key}/comments", method="POST", data=data)

    except Exception as e:
        logger.exception("post_comment failed")
        return {"ok": False, "error": str(e)}


def list_projects(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List projects for a team.

    Params:
        team_id (str): The team ID (required)

    Returns:
        ok (bool): Success status
        result (dict): Projects data with 'projects' array
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        team_id = params.get("team_id")
        if not team_id:
            return {"ok": False, "error": "team_id is required"}

        return _api_call(token, f"teams/{team_id}/projects")

    except Exception as e:
        logger.exception("list_projects failed")
        return {"ok": False, "error": str(e)}


def list_project_files(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List files in a project.

    Params:
        project_id (str): The project ID (required)
        branch_data (bool): Include branch metadata (optional)

    Returns:
        ok (bool): Success status
        result (dict): Files data with 'files' array
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        project_id = params.get("project_id")
        if not project_id:
            return {"ok": False, "error": "project_id is required"}

        query_params = {}
        if params.get("branch_data"):
            query_params["branch_data"] = "true"

        return _api_call(token, f"projects/{project_id}/files", query_params=query_params)

    except Exception as e:
        logger.exception("list_project_files failed")
        return {"ok": False, "error": str(e)}


def get_team_components(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get published components for a team.

    Params:
        team_id (str): The team ID (required)
        page_size (int): Number of results per page (default: 30, max: 100)
        cursor (str): Pagination cursor (optional)

    Returns:
        ok (bool): Success status
        result (dict): Components data with 'meta' containing 'components' array
    """
    try:
        profile = load_profile(profile_name)
        token = _get_token(profile)

        team_id = params.get("team_id")
        if not team_id:
            return {"ok": False, "error": "team_id is required"}

        query_params = {}
        page_size = params.get("page_size", 30)
        query_params["page_size"] = min(int(page_size), 100)

        if params.get("cursor"):
            query_params["cursor"] = params["cursor"]

        return _api_call(token, f"teams/{team_id}/components", query_params=query_params)

    except Exception as e:
        logger.exception("get_team_components failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "get_file": get_file,
    "get_file_nodes": get_file_nodes,
    "get_images": get_images,
    "get_comments": get_comments,
    "post_comment": post_comment,
    "list_projects": list_projects,
    "list_project_files": list_project_files,
    "get_team_components": get_team_components,
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

    logger.info(f"Executing figma.{profile}.{action}")
    return ACTIONS[action](profile, params)
