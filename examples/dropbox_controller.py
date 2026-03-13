"""Dropbox Controller for TinyHive

A controller for Dropbox API v2 integration.

Method IDs:
  controller.dropbox.{profile}.list_folder
  controller.dropbox.{profile}.get_metadata
  controller.dropbox.{profile}.upload_file
  controller.dropbox.{profile}.download_file
  controller.dropbox.{profile}.delete
  controller.dropbox.{profile}.create_folder
  controller.dropbox.{profile}.move
  controller.dropbox.{profile}.create_shared_link

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "token_env": "DROPBOX_ACCESS_TOKEN",
    "timeout": 60
}

Required Permissions:
--------------------
- files.metadata.read
- files.metadata.write
- files.content.read
- files.content.write
- sharing.write

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

logger = logging.getLogger("tinyhive.controller.dropbox")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# Dropbox API endpoints
API_BASE = "https://api.dropboxapi.com/2"
CONTENT_BASE = "https://content.dropboxapi.com/2"

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with Dropbox configuration.")
    return json.loads(path.read_text())


def _get_access_token(profile: Dict[str, Any]) -> str:
    """Get the Dropbox access token from environment variable."""
    env_var = profile.get("token_env", "DROPBOX_ACCESS_TOKEN")
    token = os.environ.get(env_var, "")
    if not token:
        raise ValueError(
            f"Environment variable '{env_var}' not set. "
            "Obtain a token from https://www.dropbox.com/developers/apps"
        )
    return token


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    endpoint: str,
    data: Dict[str, Any] = None,
    timeout: int = DEFAULT_TIMEOUT,
    base_url: str = API_BASE
) -> Dict[str, Any]:
    """Make an authenticated Dropbox API call (RPC style)."""
    url = f"{base_url}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    body = json.dumps(data).encode("utf-8") if data else b"{}"

    try:
        req = Request(url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_summary = error_data.get("error_summary", error_body[:500])
        except json.JSONDecodeError:
            error_summary = error_body[:500]
        logger.error("Dropbox API error %d: %s", e.code, error_summary)
        return {"ok": False, "error": f"HTTP {e.code}: {error_summary}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Dropbox API call")
        return {"ok": False, "error": str(e)}


def _content_upload(
    token: str,
    endpoint: str,
    content: bytes,
    api_args: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Upload content to Dropbox (content upload style)."""
    url = f"{CONTENT_BASE}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
        "Dropbox-API-Arg": json.dumps(api_args),
    }

    try:
        req = Request(url, data=content, headers=headers, method="POST")
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_summary = error_data.get("error_summary", error_body[:500])
        except json.JSONDecodeError:
            error_summary = error_body[:500]
        logger.error("Dropbox upload error %d: %s", e.code, error_summary)
        return {"ok": False, "error": f"HTTP {e.code}: {error_summary}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Dropbox upload")
        return {"ok": False, "error": str(e)}


def _content_download(
    token: str,
    endpoint: str,
    api_args: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Download content from Dropbox (content download style)."""
    url = f"{CONTENT_BASE}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Dropbox-API-Arg": json.dumps(api_args),
    }

    try:
        req = Request(url, headers=headers, method="POST")
        with urlopen(req, timeout=timeout) as response:
            metadata_header = response.headers.get("Dropbox-API-Result", "{}")
            metadata = json.loads(metadata_header)
            content = response.read()

            # Try to decode as UTF-8, fall back to base64
            try:
                decoded = content.decode("utf-8")
                return {
                    "ok": True,
                    "result": {
                        "metadata": metadata,
                        "content": decoded,
                        "encoding": "utf-8",
                        "size": len(content)
                    }
                }
            except UnicodeDecodeError:
                return {
                    "ok": True,
                    "result": {
                        "metadata": metadata,
                        "content": base64.b64encode(content).decode("ascii"),
                        "encoding": "base64",
                        "size": len(content)
                    }
                }
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_summary = error_data.get("error_summary", error_body[:500])
        except json.JSONDecodeError:
            error_summary = error_body[:500]
        logger.error("Dropbox download error %d: %s", e.code, error_summary)
        return {"ok": False, "error": f"HTTP {e.code}: {error_summary}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Dropbox download")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def list_folder(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List contents of a folder.

    Params:
        path (str): Folder path (use "" for root, required)
        recursive (bool): List recursively (default: false)
        limit (int): Max entries to return (default: 500, max: 2000)

    Returns:
        entries: List of file/folder metadata
        cursor: Cursor for pagination
        has_more: Whether more entries exist
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    path = params.get("path", "")
    # Dropbox API uses "" for root, but paths must start with /
    if path and not path.startswith("/"):
        path = "/" + path

    request_data = {
        "path": path,
        "recursive": params.get("recursive", False),
        "limit": min(params.get("limit", 500), 2000),
        "include_mounted_folders": True,
        "include_non_downloadable_files": True,
    }

    result = _api_call(token, "files/list_folder", request_data, timeout)

    if result.get("ok") and "result" in result:
        api_result = result["result"]
        entries = []
        for entry in api_result.get("entries", []):
            entries.append({
                "name": entry.get("name"),
                "path": entry.get("path_display"),
                "type": entry.get(".tag"),
                "id": entry.get("id"),
                "size": entry.get("size"),
                "modified": entry.get("server_modified"),
                "content_hash": entry.get("content_hash"),
            })
        return {
            "ok": True,
            "data": {
                "entries": entries,
                "cursor": api_result.get("cursor"),
                "has_more": api_result.get("has_more", False),
            }
        }
    return result


def get_metadata(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get metadata for a file or folder.

    Params:
        path (str): Path to file or folder (required)

    Returns:
        Metadata including name, path, type, size, modified date, etc.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    path = params.get("path", "")
    if not path:
        return {"ok": False, "error": "path is required"}
    if not path.startswith("/"):
        path = "/" + path

    request_data = {
        "path": path,
        "include_media_info": True,
        "include_deleted": False,
        "include_has_explicit_shared_members": True,
    }

    result = _api_call(token, "files/get_metadata", request_data, timeout)

    if result.get("ok") and "result" in result:
        entry = result["result"]
        return {
            "ok": True,
            "data": {
                "name": entry.get("name"),
                "path": entry.get("path_display"),
                "type": entry.get(".tag"),
                "id": entry.get("id"),
                "size": entry.get("size"),
                "modified": entry.get("server_modified"),
                "client_modified": entry.get("client_modified"),
                "content_hash": entry.get("content_hash"),
                "is_downloadable": entry.get("is_downloadable", True),
                "sharing_info": entry.get("sharing_info"),
            }
        }
    return result


def upload_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upload a file to Dropbox.

    Params:
        path (str): Destination path in Dropbox (required)
        content (str): File content as string or base64 encoded (required)
        mode (str): Write mode - 'add', 'overwrite', or 'update' (default: 'add')
        content_encoding (str): 'utf-8' or 'base64' (default: 'utf-8')

    Returns:
        Metadata of the uploaded file
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    path = params.get("path", "")
    if not path:
        return {"ok": False, "error": "path is required"}
    if not path.startswith("/"):
        path = "/" + path

    content = params.get("content")
    if content is None:
        return {"ok": False, "error": "content is required"}

    content_encoding = params.get("content_encoding", "utf-8")
    if content_encoding == "base64":
        try:
            content_bytes = base64.b64decode(content)
        except Exception as e:
            return {"ok": False, "error": f"Invalid base64 content: {e}"}
    else:
        content_bytes = content.encode("utf-8")

    mode = params.get("mode", "add")
    if mode == "overwrite":
        mode_obj = "overwrite"
    elif mode == "update":
        mode_obj = {".tag": "update", "update": params.get("rev", "")}
    else:
        mode_obj = "add"

    api_args = {
        "path": path,
        "mode": mode_obj,
        "autorename": params.get("autorename", False),
        "mute": params.get("mute", False),
        "strict_conflict": params.get("strict_conflict", False),
    }

    result = _content_upload(token, "files/upload", content_bytes, api_args, timeout)

    if result.get("ok") and "result" in result:
        entry = result["result"]
        return {
            "ok": True,
            "data": {
                "name": entry.get("name"),
                "path": entry.get("path_display"),
                "id": entry.get("id"),
                "size": entry.get("size"),
                "modified": entry.get("server_modified"),
                "content_hash": entry.get("content_hash"),
            }
        }
    return result


def download_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Download a file from Dropbox.

    Params:
        path (str): Path to file in Dropbox (required)

    Returns:
        metadata: File metadata
        content: File content (utf-8 string or base64 encoded)
        encoding: 'utf-8' or 'base64'
        size: Content size in bytes
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    path = params.get("path", "")
    if not path:
        return {"ok": False, "error": "path is required"}
    if not path.startswith("/"):
        path = "/" + path

    api_args = {"path": path}

    result = _content_download(token, "files/download", api_args, timeout)

    if result.get("ok") and "result" in result:
        return {"ok": True, "data": result["result"]}
    return result


def delete(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a file or folder.

    Params:
        path (str): Path to delete (required)

    Returns:
        Metadata of deleted item
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    path = params.get("path", "")
    if not path:
        return {"ok": False, "error": "path is required"}
    if not path.startswith("/"):
        path = "/" + path

    request_data = {"path": path}

    result = _api_call(token, "files/delete_v2", request_data, timeout)

    if result.get("ok") and "result" in result:
        metadata = result["result"].get("metadata", {})
        return {
            "ok": True,
            "data": {
                "name": metadata.get("name"),
                "path": metadata.get("path_display"),
                "type": metadata.get(".tag"),
            }
        }
    return result


def create_folder(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a folder.

    Params:
        path (str): Path for the new folder (required)

    Returns:
        Metadata of created folder
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    path = params.get("path", "")
    if not path:
        return {"ok": False, "error": "path is required"}
    if not path.startswith("/"):
        path = "/" + path

    request_data = {
        "path": path,
        "autorename": params.get("autorename", False),
    }

    result = _api_call(token, "files/create_folder_v2", request_data, timeout)

    if result.get("ok") and "result" in result:
        metadata = result["result"].get("metadata", {})
        return {
            "ok": True,
            "data": {
                "name": metadata.get("name"),
                "path": metadata.get("path_display"),
                "id": metadata.get("id"),
            }
        }
    return result


def move(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Move a file or folder.

    Params:
        from_path (str): Source path (required)
        to_path (str): Destination path (required)

    Returns:
        Metadata of moved item
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    from_path = params.get("from_path", "")
    to_path = params.get("to_path", "")

    if not from_path:
        return {"ok": False, "error": "from_path is required"}
    if not to_path:
        return {"ok": False, "error": "to_path is required"}

    if not from_path.startswith("/"):
        from_path = "/" + from_path
    if not to_path.startswith("/"):
        to_path = "/" + to_path

    request_data = {
        "from_path": from_path,
        "to_path": to_path,
        "autorename": params.get("autorename", False),
        "allow_ownership_transfer": params.get("allow_ownership_transfer", False),
    }

    result = _api_call(token, "files/move_v2", request_data, timeout)

    if result.get("ok") and "result" in result:
        metadata = result["result"].get("metadata", {})
        return {
            "ok": True,
            "data": {
                "name": metadata.get("name"),
                "path": metadata.get("path_display"),
                "type": metadata.get(".tag"),
                "id": metadata.get("id"),
            }
        }
    return result


def create_shared_link(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a shared link for a file or folder.

    Params:
        path (str): Path to file or folder (required)

    Returns:
        url: Shared link URL
        path: Path to the file
        visibility: Link visibility settings
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    timeout = profile.get("timeout", DEFAULT_TIMEOUT)

    path = params.get("path", "")
    if not path:
        return {"ok": False, "error": "path is required"}
    if not path.startswith("/"):
        path = "/" + path

    request_data = {
        "path": path,
        "settings": {
            "requested_visibility": "public",
            "audience": "public",
            "access": "viewer",
        }
    }

    result = _api_call(token, "sharing/create_shared_link_with_settings", request_data, timeout)

    # Handle case where link already exists
    if not result.get("ok") and "shared_link_already_exists" in result.get("error", ""):
        # Try to get existing links
        list_request = {"path": path, "direct_only": True}
        list_result = _api_call(token, "sharing/list_shared_links", list_request, timeout)
        if list_result.get("ok") and "result" in list_result:
            links = list_result["result"].get("links", [])
            if links:
                link = links[0]
                return {
                    "ok": True,
                    "data": {
                        "url": link.get("url"),
                        "path": link.get("path_lower"),
                        "name": link.get("name"),
                        "visibility": link.get("link_permissions", {}).get("resolved_visibility", {}).get(".tag"),
                    }
                }

    if result.get("ok") and "result" in result:
        link = result["result"]
        return {
            "ok": True,
            "data": {
                "url": link.get("url"),
                "path": link.get("path_lower"),
                "name": link.get("name"),
                "visibility": link.get("link_permissions", {}).get("resolved_visibility", {}).get(".tag"),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_folder": list_folder,
    "get_metadata": get_metadata,
    "upload_file": upload_file,
    "download_file": download_file,
    "delete": delete,
    "create_folder": create_folder,
    "move": move,
    "create_shared_link": create_shared_link,
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
        logger.info(f"Executing dropbox.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
