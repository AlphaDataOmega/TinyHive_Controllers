"""Box Controller — Box cloud storage integration via REST APIs.

This controller provides integration with Box cloud storage service
using OAuth2 Bearer token authentication.

Method IDs:
  controller.box.{profile}.list_folder
  controller.box.{profile}.get_file_info
  controller.box.{profile}.upload_file
  controller.box.{profile}.download_file
  controller.box.{profile}.delete_file
  controller.box.{profile}.create_folder
  controller.box.{profile}.search
  controller.box.{profile}.create_shared_link

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:

  {
    "token_env": "BOX_ACCESS_TOKEN",
    "default_folder_id": "0"
  }

  - token_env: Environment variable containing the Box access token
  - default_folder_id: Default folder ID for operations (optional, "0" = root)

Required Scopes:
  - list_folder: base_explorer or root_readonly
  - get_file_info: base_explorer or root_readonly
  - upload_file: base_upload or root_readwrite
  - download_file: base_explorer or root_readonly
  - delete_file: base_explorer or root_readwrite
  - create_folder: base_explorer or root_readwrite
  - search: base_explorer or root_readonly
  - create_shared_link: item_share or root_readwrite

Dependencies:
  - None (standard library only)
"""

import base64
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.box")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# Box API endpoints
BOX_API_BASE = "https://api.box.com/2.0"
BOX_UPLOAD_BASE = "https://upload.box.com/api/2.0"

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with Box configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available Box profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# Authentication
# =============================================================================

def _get_access_token(profile: Dict[str, Any]) -> str:
    """Get Box access token from environment variable."""
    token_env = profile.get("token_env", "BOX_ACCESS_TOKEN")
    token = os.environ.get(token_env, "")
    if not token:
        raise ValueError(
            f"Environment variable '{token_env}' not set. "
            "Obtain a Box access token from the Box Developer Console."
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
    content_type: str = "application/json",
    timeout: int = DEFAULT_TIMEOUT,
    extra_headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Make an authenticated Box API call."""
    headers = {
        "Authorization": f"Bearer {token}",
    }
    if content_type:
        headers["Content-Type"] = content_type
    if extra_headers:
        headers.update(extra_headers)

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
            if "context_info" in error_data:
                error_message += f" - {error_data['context_info']}"
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Box API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Box API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def list_folder(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List contents of a Box folder.

    Params:
        folder_id (str): Folder ID to list (default: "0" for root, or from profile)
        limit (int): Maximum items to return (default: 100, max: 1000)
        offset (int): Offset for pagination (default: 0)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    folder_id = params.get("folder_id", profile.get("default_folder_id", "0"))
    limit = min(params.get("limit", 100), 1000)
    offset = params.get("offset", 0)

    query_params = {
        "limit": limit,
        "offset": offset,
        "fields": "id,type,name,size,modified_at,created_at,sha1,parent"
    }

    url = f"{BOX_API_BASE}/folders/{folder_id}/items?{urlencode(query_params)}"
    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        items = result["result"].get("entries", [])
        return {
            "ok": True,
            "result": {
                "items": [
                    {
                        "id": item.get("id"),
                        "type": item.get("type"),
                        "name": item.get("name"),
                        "size": item.get("size"),
                        "modified_at": item.get("modified_at"),
                        "created_at": item.get("created_at"),
                        "sha1": item.get("sha1"),
                        "parent_id": item.get("parent", {}).get("id") if item.get("parent") else None,
                    }
                    for item in items
                ],
                "total_count": result["result"].get("total_count", len(items)),
                "offset": result["result"].get("offset", offset),
                "limit": result["result"].get("limit", limit),
            }
        }
    return result


def get_file_info(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get detailed information about a file.

    Params:
        file_id (str): File ID (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    file_id = params.get("file_id")
    if not file_id:
        return {"ok": False, "error": "file_id is required"}

    fields = "id,type,name,size,sha1,created_at,modified_at,content_created_at,content_modified_at,parent,path_collection,shared_link,owned_by,created_by,modified_by"
    url = f"{BOX_API_BASE}/files/{file_id}?fields={fields}"
    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        file_info = result["result"]
        return {
            "ok": True,
            "result": {
                "id": file_info.get("id"),
                "type": file_info.get("type"),
                "name": file_info.get("name"),
                "size": file_info.get("size"),
                "sha1": file_info.get("sha1"),
                "created_at": file_info.get("created_at"),
                "modified_at": file_info.get("modified_at"),
                "content_created_at": file_info.get("content_created_at"),
                "content_modified_at": file_info.get("content_modified_at"),
                "parent": {
                    "id": file_info.get("parent", {}).get("id"),
                    "name": file_info.get("parent", {}).get("name"),
                } if file_info.get("parent") else None,
                "path": "/".join([p.get("name", "") for p in file_info.get("path_collection", {}).get("entries", [])]),
                "shared_link": file_info.get("shared_link"),
                "owned_by": file_info.get("owned_by", {}).get("login"),
                "created_by": file_info.get("created_by", {}).get("login"),
                "modified_by": file_info.get("modified_by", {}).get("login"),
            }
        }
    return result


def upload_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upload a file to Box.

    Params:
        folder_id (str): Parent folder ID (default: "0" for root, or from profile)
        file_content (str): File content as string or base64-encoded binary
        file_name (str): Name for the uploaded file (required)
        content_encoding (str): 'utf-8' or 'base64' (default: 'utf-8')
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    folder_id = params.get("folder_id", profile.get("default_folder_id", "0"))
    file_content = params.get("file_content")
    file_name = params.get("file_name")
    content_encoding = params.get("content_encoding", "utf-8")

    if not file_content:
        return {"ok": False, "error": "file_content is required"}
    if not file_name:
        return {"ok": False, "error": "file_name is required"}

    # Decode content
    if content_encoding == "base64":
        try:
            content_bytes = base64.b64decode(file_content)
        except Exception as e:
            return {"ok": False, "error": f"Invalid base64 content: {e}"}
    else:
        content_bytes = file_content.encode("utf-8")

    # Build multipart form data
    boundary = f"----BoxUpload{uuid.uuid4().hex}"

    attributes = json.dumps({
        "name": file_name,
        "parent": {"id": folder_id}
    })

    body_parts = []
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(b'Content-Disposition: form-data; name="attributes"\r\n\r\n')
    body_parts.append(attributes.encode("utf-8"))
    body_parts.append(b"\r\n")
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'.encode())
    body_parts.append(b"Content-Type: application/octet-stream\r\n\r\n")
    body_parts.append(content_bytes)
    body_parts.append(b"\r\n")
    body_parts.append(f"--{boundary}--\r\n".encode())

    body = b"".join(body_parts)

    url = f"{BOX_UPLOAD_BASE}/files/content"
    result = _api_call(
        token,
        url,
        method="POST",
        data=body,
        content_type=f"multipart/form-data; boundary={boundary}"
    )

    if result.get("ok") and "result" in result:
        entries = result["result"].get("entries", [])
        if entries:
            uploaded_file = entries[0]
            return {
                "ok": True,
                "result": {
                    "id": uploaded_file.get("id"),
                    "name": uploaded_file.get("name"),
                    "size": uploaded_file.get("size"),
                    "sha1": uploaded_file.get("sha1"),
                    "created_at": uploaded_file.get("created_at"),
                    "modified_at": uploaded_file.get("modified_at"),
                    "parent_id": uploaded_file.get("parent", {}).get("id") if uploaded_file.get("parent") else None,
                }
            }
        return {"ok": False, "error": "Upload succeeded but no file entry returned"}
    return result


def download_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Download a file from Box.

    Params:
        file_id (str): File ID to download (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    file_id = params.get("file_id")
    if not file_id:
        return {"ok": False, "error": "file_id is required"}

    url = f"{BOX_API_BASE}/files/{file_id}/content"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            content = response.read()
            content_type = response.headers.get("Content-Type", "application/octet-stream")

            # Try to decode as text, otherwise return base64
            try:
                return {
                    "ok": True,
                    "data": content.decode("utf-8"),
                    "encoding": "utf-8",
                    "size": len(content),
                    "content_type": content_type,
                }
            except UnicodeDecodeError:
                return {
                    "ok": True,
                    "data": base64.b64encode(content).decode("ascii"),
                    "encoding": "base64",
                    "size": len(content),
                    "content_type": content_type,
                }
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def delete_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a file from Box.

    Params:
        file_id (str): File ID to delete (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    file_id = params.get("file_id")
    if not file_id:
        return {"ok": False, "error": "file_id is required"}

    url = f"{BOX_API_BASE}/files/{file_id}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        req = Request(url, headers=headers, method="DELETE")
        with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            # Box returns 204 No Content on successful delete
            return {"ok": True, "result": {"deleted": True, "file_id": file_id}}
    except HTTPError as e:
        if e.code == 204:
            return {"ok": True, "result": {"deleted": True, "file_id": file_id}}
        error_body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def create_folder(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new folder in Box.

    Params:
        parent_id (str): Parent folder ID (default: "0" for root, or from profile)
        name (str): Folder name (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    parent_id = params.get("parent_id", profile.get("default_folder_id", "0"))
    name = params.get("name")

    if not name:
        return {"ok": False, "error": "name is required"}

    url = f"{BOX_API_BASE}/folders"
    body = json.dumps({
        "name": name,
        "parent": {"id": parent_id}
    }).encode("utf-8")

    result = _api_call(token, url, method="POST", data=body)

    if result.get("ok") and "result" in result:
        folder = result["result"]
        return {
            "ok": True,
            "result": {
                "id": folder.get("id"),
                "type": folder.get("type"),
                "name": folder.get("name"),
                "created_at": folder.get("created_at"),
                "modified_at": folder.get("modified_at"),
                "parent_id": folder.get("parent", {}).get("id") if folder.get("parent") else None,
            }
        }
    return result


def search(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for files and folders in Box.

    Params:
        query (str): Search query (required)
        type (str): Filter by type: 'file', 'folder', or 'web_link' (optional)
        limit (int): Maximum results to return (default: 30, max: 200)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    query = params.get("query")
    if not query:
        return {"ok": False, "error": "query is required"}

    item_type = params.get("type")
    limit = min(params.get("limit", 30), 200)

    query_params = {
        "query": query,
        "limit": limit,
        "fields": "id,type,name,size,modified_at,created_at,parent,path_collection"
    }
    if item_type:
        query_params["type"] = item_type

    url = f"{BOX_API_BASE}/search?{urlencode(query_params)}"
    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        entries = result["result"].get("entries", [])
        return {
            "ok": True,
            "result": {
                "items": [
                    {
                        "id": item.get("id"),
                        "type": item.get("type"),
                        "name": item.get("name"),
                        "size": item.get("size"),
                        "modified_at": item.get("modified_at"),
                        "created_at": item.get("created_at"),
                        "parent_id": item.get("parent", {}).get("id") if item.get("parent") else None,
                        "path": "/".join([p.get("name", "") for p in item.get("path_collection", {}).get("entries", [])]),
                    }
                    for item in entries
                ],
                "total_count": result["result"].get("total_count", len(entries)),
            }
        }
    return result


def create_shared_link(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a shared link for a file.

    Params:
        file_id (str): File ID (required)
        access (str): Access level: 'open', 'company', or 'collaborators' (default: 'open')
        permissions (dict): Permissions object with 'can_download', 'can_preview', 'can_edit' (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    file_id = params.get("file_id")
    if not file_id:
        return {"ok": False, "error": "file_id is required"}

    access = params.get("access", "open")
    permissions = params.get("permissions", {})

    shared_link_config: Dict[str, Any] = {"access": access}
    if permissions:
        shared_link_config["permissions"] = permissions

    url = f"{BOX_API_BASE}/files/{file_id}?fields=shared_link"
    body = json.dumps({"shared_link": shared_link_config}).encode("utf-8")

    result = _api_call(token, url, method="PUT", data=body)

    if result.get("ok") and "result" in result:
        shared_link = result["result"].get("shared_link", {})
        return {
            "ok": True,
            "result": {
                "file_id": file_id,
                "url": shared_link.get("url"),
                "download_url": shared_link.get("download_url"),
                "vanity_url": shared_link.get("vanity_url"),
                "access": shared_link.get("access"),
                "effective_access": shared_link.get("effective_access"),
                "effective_permission": shared_link.get("effective_permission"),
                "is_password_enabled": shared_link.get("is_password_enabled"),
                "unshared_at": shared_link.get("unshared_at"),
                "download_count": shared_link.get("download_count"),
                "preview_count": shared_link.get("preview_count"),
                "permissions": shared_link.get("permissions"),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_folder": list_folder,
    "get_file_info": get_file_info,
    "upload_file": upload_file,
    "download_file": download_file,
    "delete_file": delete_file,
    "create_folder": create_folder,
    "search": search,
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
        logger.info(f"Executing box.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
