"""
WordPress Controller for TinyHive

A controller for WordPress REST API integration using application passwords.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "site_url": "https://example.com",
    "username_env": "WP_USERNAME",
    "app_password_env": "WP_APP_PASSWORD"
}

Environment Variables:
---------------------
- WP_USERNAME: WordPress username (or custom env var from profile)
- WP_APP_PASSWORD: WordPress application password (or custom env var from profile)

Required Permissions:
--------------------
- Posts: edit_posts, publish_posts, delete_posts
- Pages: edit_pages, publish_pages
- Media: upload_files
- Categories: manage_categories

Method IDs:
----------
  controller.wordpress.{profile}.list_posts
  controller.wordpress.{profile}.get_post
  controller.wordpress.{profile}.create_post
  controller.wordpress.{profile}.update_post
  controller.wordpress.{profile}.delete_post
  controller.wordpress.{profile}.list_pages
  controller.wordpress.{profile}.list_categories
  controller.wordpress.{profile}.upload_media

Dependencies:
------------
None - uses Python standard library only
"""

import base64
import json
import logging
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

logger = logging.getLogger("tinyhive.controller.wordpress")

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


def _get_credentials(profile: Dict[str, Any]) -> tuple:
    """Get WordPress credentials from environment variables."""
    username_env = profile.get("username_env", "WP_USERNAME")
    password_env = profile.get("app_password_env", "WP_APP_PASSWORD")

    username = os.environ.get(username_env)
    app_password = os.environ.get(password_env)

    if not username:
        raise ValueError(f"Environment variable '{username_env}' not set")
    if not app_password:
        raise ValueError(f"Environment variable '{password_env}' not set")

    return username, app_password


def _get_base_url(profile: Dict[str, Any]) -> str:
    """Get the WordPress REST API base URL."""
    site_url = profile.get("site_url", "").rstrip("/")
    if not site_url:
        raise ValueError("site_url is required in profile")
    return f"{site_url}/wp-json/wp/v2"


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    profile: Dict[str, Any],
    endpoint: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    content_type: str = "application/json",
    timeout: int = DEFAULT_TIMEOUT,
    extra_headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Make an authenticated WordPress REST API call."""
    username, app_password = _get_credentials(profile)
    base_url = _get_base_url(profile)

    # Build Basic Auth header
    auth_string = f"{username}:{app_password}"
    auth_bytes = base64.b64encode(auth_string.encode("utf-8")).decode("ascii")

    headers = {
        "Authorization": f"Basic {auth_bytes}",
        "Content-Type": content_type,
        "Accept": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    url = f"{base_url}/{endpoint.lstrip('/')}"

    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                result = json.loads(response_body)
                return {"ok": True, "result": result}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_body[:500])
            error_code = error_data.get("code", "unknown")
        except json.JSONDecodeError:
            error_message = error_body[:500]
            error_code = "unknown"
        logger.error("WordPress API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}", "code": error_code}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in WordPress API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Post Actions
# =============================================================================

def list_posts(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List WordPress posts.

    Params:
        per_page (int): Number of posts per page (default: 10, max: 100)
        page (int): Page number (default: 1)
        status (str): Post status - publish, draft, pending, private, future, trash (default: publish)
        categories (list[int]): Filter by category IDs
        search (str): Search term
    """
    try:
        profile = load_profile(profile_name)

        query_params = {}
        if "per_page" in params:
            query_params["per_page"] = min(int(params["per_page"]), 100)
        if "page" in params:
            query_params["page"] = int(params["page"])
        if "status" in params:
            query_params["status"] = params["status"]
        if "categories" in params:
            cats = params["categories"]
            if isinstance(cats, list):
                query_params["categories"] = ",".join(str(c) for c in cats)
            else:
                query_params["categories"] = str(cats)
        if "search" in params:
            query_params["search"] = params["search"]

        endpoint = "posts"
        if query_params:
            endpoint += "?" + urlencode(query_params)

        result = _api_call(profile, endpoint)

        if result.get("ok") and "result" in result:
            posts = result["result"]
            return {
                "ok": True,
                "data": [
                    {
                        "id": p.get("id"),
                        "title": p.get("title", {}).get("rendered", ""),
                        "slug": p.get("slug"),
                        "status": p.get("status"),
                        "date": p.get("date"),
                        "modified": p.get("modified"),
                        "link": p.get("link"),
                        "author": p.get("author"),
                        "categories": p.get("categories", []),
                        "tags": p.get("tags", []),
                        "excerpt": p.get("excerpt", {}).get("rendered", ""),
                    }
                    for p in posts
                ],
                "count": len(posts)
            }
        return result
    except Exception as e:
        logger.exception("list_posts failed")
        return {"ok": False, "error": str(e)}


def get_post(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a single WordPress post by ID.

    Params:
        post_id (int): Post ID (required)
    """
    try:
        profile = load_profile(profile_name)

        post_id = params.get("post_id")
        if not post_id:
            return {"ok": False, "error": "post_id is required"}

        result = _api_call(profile, f"posts/{post_id}")

        if result.get("ok") and "result" in result:
            p = result["result"]
            return {
                "ok": True,
                "data": {
                    "id": p.get("id"),
                    "title": p.get("title", {}).get("rendered", ""),
                    "content": p.get("content", {}).get("rendered", ""),
                    "content_raw": p.get("content", {}).get("raw", ""),
                    "slug": p.get("slug"),
                    "status": p.get("status"),
                    "date": p.get("date"),
                    "modified": p.get("modified"),
                    "link": p.get("link"),
                    "author": p.get("author"),
                    "featured_media": p.get("featured_media"),
                    "categories": p.get("categories", []),
                    "tags": p.get("tags", []),
                    "excerpt": p.get("excerpt", {}).get("rendered", ""),
                }
            }
        return result
    except Exception as e:
        logger.exception("get_post failed")
        return {"ok": False, "error": str(e)}


def create_post(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new WordPress post.

    Params:
        title (str): Post title (required)
        content (str): Post content (required)
        status (str): Post status - publish, draft, pending, private, future (default: draft)
        categories (list[int]): Category IDs
        tags (list[int]): Tag IDs
    """
    try:
        profile = load_profile(profile_name)

        title = params.get("title")
        content = params.get("content")

        if not title:
            return {"ok": False, "error": "title is required"}
        if not content:
            return {"ok": False, "error": "content is required"}

        post_data = {
            "title": title,
            "content": content,
            "status": params.get("status", "draft"),
        }

        if "categories" in params:
            cats = params["categories"]
            if isinstance(cats, list):
                post_data["categories"] = cats
            else:
                post_data["categories"] = [cats]

        if "tags" in params:
            tags = params["tags"]
            if isinstance(tags, list):
                post_data["tags"] = tags
            else:
                post_data["tags"] = [tags]

        data = json.dumps(post_data).encode("utf-8")
        result = _api_call(profile, "posts", method="POST", data=data)

        if result.get("ok") and "result" in result:
            p = result["result"]
            return {
                "ok": True,
                "data": {
                    "id": p.get("id"),
                    "title": p.get("title", {}).get("rendered", ""),
                    "slug": p.get("slug"),
                    "status": p.get("status"),
                    "link": p.get("link"),
                }
            }
        return result
    except Exception as e:
        logger.exception("create_post failed")
        return {"ok": False, "error": str(e)}


def update_post(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing WordPress post.

    Params:
        post_id (int): Post ID (required)
        fields (dict): Fields to update - title, content, status, categories, tags, etc.
    """
    try:
        profile = load_profile(profile_name)

        post_id = params.get("post_id")
        fields = params.get("fields", {})

        if not post_id:
            return {"ok": False, "error": "post_id is required"}
        if not fields:
            return {"ok": False, "error": "fields is required"}

        data = json.dumps(fields).encode("utf-8")
        result = _api_call(profile, f"posts/{post_id}", method="POST", data=data)

        if result.get("ok") and "result" in result:
            p = result["result"]
            return {
                "ok": True,
                "data": {
                    "id": p.get("id"),
                    "title": p.get("title", {}).get("rendered", ""),
                    "slug": p.get("slug"),
                    "status": p.get("status"),
                    "modified": p.get("modified"),
                    "link": p.get("link"),
                }
            }
        return result
    except Exception as e:
        logger.exception("update_post failed")
        return {"ok": False, "error": str(e)}


def delete_post(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a WordPress post.

    Params:
        post_id (int): Post ID (required)
        force (bool): Whether to bypass trash and force delete (default: false)
    """
    try:
        profile = load_profile(profile_name)

        post_id = params.get("post_id")
        if not post_id:
            return {"ok": False, "error": "post_id is required"}

        force = params.get("force", False)
        endpoint = f"posts/{post_id}"
        if force:
            endpoint += "?force=true"

        result = _api_call(profile, endpoint, method="DELETE")

        if result.get("ok"):
            return {
                "ok": True,
                "data": {
                    "deleted": True,
                    "post_id": post_id,
                    "force": force,
                }
            }
        return result
    except Exception as e:
        logger.exception("delete_post failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Page Actions
# =============================================================================

def list_pages(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List WordPress pages.

    Params:
        per_page (int): Number of pages per page (default: 10, max: 100)
        page (int): Page number (default: 1)
        status (str): Page status - publish, draft, pending, private (default: publish)
    """
    try:
        profile = load_profile(profile_name)

        query_params = {}
        if "per_page" in params:
            query_params["per_page"] = min(int(params["per_page"]), 100)
        if "page" in params:
            query_params["page"] = int(params["page"])
        if "status" in params:
            query_params["status"] = params["status"]

        endpoint = "pages"
        if query_params:
            endpoint += "?" + urlencode(query_params)

        result = _api_call(profile, endpoint)

        if result.get("ok") and "result" in result:
            pages = result["result"]
            return {
                "ok": True,
                "data": [
                    {
                        "id": p.get("id"),
                        "title": p.get("title", {}).get("rendered", ""),
                        "slug": p.get("slug"),
                        "status": p.get("status"),
                        "date": p.get("date"),
                        "modified": p.get("modified"),
                        "link": p.get("link"),
                        "parent": p.get("parent"),
                        "menu_order": p.get("menu_order"),
                    }
                    for p in pages
                ],
                "count": len(pages)
            }
        return result
    except Exception as e:
        logger.exception("list_pages failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Category Actions
# =============================================================================

def list_categories(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List WordPress categories.

    Params:
        per_page (int): Number of categories per page (default: 10, max: 100)
        page (int): Page number (default: 1)
        hide_empty (bool): Hide categories with no posts (default: false)
    """
    try:
        profile = load_profile(profile_name)

        query_params = {}
        if "per_page" in params:
            query_params["per_page"] = min(int(params["per_page"]), 100)
        if "page" in params:
            query_params["page"] = int(params["page"])
        if "hide_empty" in params:
            query_params["hide_empty"] = str(params["hide_empty"]).lower()

        endpoint = "categories"
        if query_params:
            endpoint += "?" + urlencode(query_params)

        result = _api_call(profile, endpoint)

        if result.get("ok") and "result" in result:
            categories = result["result"]
            return {
                "ok": True,
                "data": [
                    {
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "slug": c.get("slug"),
                        "description": c.get("description"),
                        "parent": c.get("parent"),
                        "count": c.get("count"),
                        "link": c.get("link"),
                    }
                    for c in categories
                ],
                "count": len(categories)
            }
        return result
    except Exception as e:
        logger.exception("list_categories failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Media Actions
# =============================================================================

def upload_media(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upload a media file to WordPress.

    Params:
        file_path (str): Path to the file to upload (required)
        title (str): Media title (optional, defaults to filename)
        alt_text (str): Alt text for the media (optional)
    """
    try:
        profile = load_profile(profile_name)

        file_path = params.get("file_path")
        if not file_path:
            return {"ok": False, "error": "file_path is required"}

        path = Path(file_path)
        if not path.exists():
            return {"ok": False, "error": f"File not found: {file_path}"}

        # Read file content
        file_content = path.read_bytes()
        filename = path.name

        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = "application/octet-stream"

        # Get credentials and build URL
        username, app_password = _get_credentials(profile)
        base_url = _get_base_url(profile)

        auth_string = f"{username}:{app_password}"
        auth_bytes = base64.b64encode(auth_string.encode("utf-8")).decode("ascii")

        # Build multipart form data
        boundary = f"----TinyHiveBoundary{uuid.uuid4().hex}"

        # Build the multipart body
        body_parts = []

        # File part
        body_parts.append(f"--{boundary}".encode("utf-8"))
        body_parts.append(
            f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode("utf-8")
        )
        body_parts.append(f"Content-Type: {mime_type}".encode("utf-8"))
        body_parts.append(b"")
        body_parts.append(file_content)

        # Title part (optional)
        title = params.get("title", path.stem)
        body_parts.append(f"--{boundary}".encode("utf-8"))
        body_parts.append(b'Content-Disposition: form-data; name="title"')
        body_parts.append(b"")
        body_parts.append(title.encode("utf-8"))

        # Alt text part (optional)
        if "alt_text" in params:
            body_parts.append(f"--{boundary}".encode("utf-8"))
            body_parts.append(b'Content-Disposition: form-data; name="alt_text"')
            body_parts.append(b"")
            body_parts.append(params["alt_text"].encode("utf-8"))

        # End boundary
        body_parts.append(f"--{boundary}--".encode("utf-8"))
        body_parts.append(b"")

        body = b"\r\n".join(body_parts)

        headers = {
            "Authorization": f"Basic {auth_bytes}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        }

        url = f"{base_url}/media"

        try:
            req = Request(url, data=body, headers=headers, method="POST")
            with urlopen(req, timeout=DEFAULT_TIMEOUT * 2) as response:
                response_body = response.read().decode("utf-8")
                media = json.loads(response_body)

                return {
                    "ok": True,
                    "data": {
                        "id": media.get("id"),
                        "title": media.get("title", {}).get("rendered", ""),
                        "source_url": media.get("source_url"),
                        "media_type": media.get("media_type"),
                        "mime_type": media.get("mime_type"),
                        "link": media.get("link"),
                        "alt_text": media.get("alt_text", ""),
                    }
                }
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            try:
                error_data = json.loads(error_body)
                error_message = error_data.get("message", error_body[:500])
            except json.JSONDecodeError:
                error_message = error_body[:500]
            return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
        except URLError as e:
            return {"ok": False, "error": f"Network error: {e.reason}"}

    except Exception as e:
        logger.exception("upload_media failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_posts": list_posts,
    "get_post": get_post,
    "create_post": create_post,
    "update_post": update_post,
    "delete_post": delete_post,
    "list_pages": list_pages,
    "list_categories": list_categories,
    "upload_media": upload_media,
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

    logger.info(f"Executing wordpress.{profile}.{action}")
    return ACTIONS[action](profile, params)
