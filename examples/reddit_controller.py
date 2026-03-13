"""
Reddit Controller for TinyHive

A controller for interacting with the Reddit API via OAuth2.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "client_id": "your_client_id",
    "client_secret_env": "REDDIT_CLIENT_SECRET",
    "username": "your_username",
    "password_env": "REDDIT_PASSWORD",
    "user_agent": "TinyHive/1.0 by your_username"
}

Or for script apps with token from environment:
{
    "token_env": "REDDIT_ACCESS_TOKEN",
    "user_agent": "TinyHive/1.0 by your_username"
}

Method IDs:
-----------
  controller.reddit.{profile}.get_me
  controller.reddit.{profile}.submit_post
  controller.reddit.{profile}.get_post
  controller.reddit.{profile}.list_subreddit_posts
  controller.reddit.{profile}.get_comments
  controller.reddit.{profile}.post_comment
  controller.reddit.{profile}.vote
  controller.reddit.{profile}.search

Dependencies:
------------
- Python standard library only (urllib, json, etc.)

Required Reddit API Scopes:
--------------------------
- identity: get_me
- submit: submit_post
- read: get_post, list_subreddit_posts, get_comments, search
- privatemessages: (optional)
- vote: vote
- any: post_comment (requires appropriate scope)
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.reddit")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Reddit API endpoints
REDDIT_BASE_URL = "https://oauth.reddit.com"
REDDIT_AUTH_URL = "https://www.reddit.com/api/v1/access_token"

# Token cache: profile_name -> (token, expiry_timestamp)
_token_cache: Dict[str, Tuple[str, float]] = {}

DEFAULT_TIMEOUT = 30
DEFAULT_USER_AGENT = "TinyHive/1.0"


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


def list_profiles() -> List[str]:
    """List available Reddit profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# OAuth2 Authentication
# =============================================================================

def _get_access_token(profile: Dict[str, Any], profile_name: str) -> str:
    """
    Get OAuth2 access token for Reddit API calls.

    Supports two authentication methods:
    1. Direct token from environment variable (token_env)
    2. Client credentials flow with username/password (script app)
    """
    # Check cache first
    if profile_name in _token_cache:
        token, expiry = _token_cache[profile_name]
        if time.time() < expiry:
            return token

    # Option 1: Direct token from environment
    token_env = profile.get("token_env")
    if token_env:
        token = os.environ.get(token_env, "")
        if not token:
            raise ValueError(f"Environment variable '{token_env}' not set.")
        # Cache with 1 hour expiry (we don't know actual expiry)
        _token_cache[profile_name] = (token, time.time() + 3600)
        return token

    # Option 2: Client credentials flow (script app)
    client_id = profile.get("client_id")
    client_secret_env = profile.get("client_secret_env", "REDDIT_CLIENT_SECRET")
    client_secret = os.environ.get(client_secret_env, "")

    username = profile.get("username")
    password_env = profile.get("password_env", "REDDIT_PASSWORD")
    password = os.environ.get(password_env, "")

    if not client_id:
        raise ValueError("Profile must specify either 'token_env' or 'client_id'.")

    if not client_secret:
        raise ValueError(f"Environment variable '{client_secret_env}' not set.")

    if not username or not password:
        raise ValueError(
            f"For client credentials flow, username and {password_env} are required."
        )

    # Request token using password grant
    import base64
    auth_string = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    user_agent = profile.get("user_agent", DEFAULT_USER_AGENT)

    data = urlencode({
        "grant_type": "password",
        "username": username,
        "password": password
    }).encode("utf-8")

    headers = {
        "Authorization": f"Basic {auth_string}",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": user_agent
    }

    try:
        req = Request(REDDIT_AUTH_URL, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            token_data = json.loads(response.read().decode("utf-8"))

        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError(f"Failed to get access token: {token_data}")

        expires_in = token_data.get("expires_in", 3600)
        expiry = time.time() + expires_in - 60  # Refresh 60 seconds early

        _token_cache[profile_name] = (access_token, expiry)
        return access_token

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"Failed to authenticate: HTTP {e.code}: {error_body}")


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    endpoint: str,
    user_agent: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Reddit API call."""
    url = f"{REDDIT_BASE_URL}{endpoint}"

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": user_agent,
    }

    body = None
    if data is not None:
        if method == "GET":
            # For GET requests, append to URL
            url += ("&" if "?" in url else "?") + urlencode(data)
        else:
            # For POST requests, encode as form data
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            body = urlencode(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
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
        logger.error("Reddit API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Reddit API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def get_me(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get authenticated user information.

    Params: None required

    Returns:
        User information including name, karma, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_access_token(profile, profile_name)
        user_agent = profile.get("user_agent", DEFAULT_USER_AGENT)

        result = _api_call(token, "/api/v1/me", user_agent)

        if result.get("ok") and "result" in result:
            user = result["result"]
            return {
                "ok": True,
                "data": {
                    "id": user.get("id"),
                    "name": user.get("name"),
                    "created_utc": user.get("created_utc"),
                    "link_karma": user.get("link_karma"),
                    "comment_karma": user.get("comment_karma"),
                    "is_gold": user.get("is_gold"),
                    "is_mod": user.get("is_mod"),
                    "has_verified_email": user.get("has_verified_email"),
                    "icon_img": user.get("icon_img"),
                }
            }
        return result
    except Exception as e:
        logger.exception("get_me failed")
        return {"ok": False, "error": str(e)}


def submit_post(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Submit a new post to a subreddit.

    Params:
        subreddit (str): Target subreddit name (required)
        title (str): Post title (required)
        text (str): Post body text (for self posts)
        url (str): URL to link (for link posts)
        kind (str): 'self' or 'link' (default: auto-detect based on text/url)
        flair_id (str): Flair template ID (optional)
        flair_text (str): Flair text (optional)
        nsfw (bool): Mark as NSFW (default: false)
        spoiler (bool): Mark as spoiler (default: false)
        send_replies (bool): Send inbox replies (default: true)

    Returns:
        Post submission result including post ID and URL
    """
    try:
        profile = load_profile(profile_name)
        token = _get_access_token(profile, profile_name)
        user_agent = profile.get("user_agent", DEFAULT_USER_AGENT)

        subreddit = params.get("subreddit", "")
        title = params.get("title", "")
        text = params.get("text")
        url = params.get("url")

        if not subreddit:
            return {"ok": False, "error": "subreddit is required"}
        if not title:
            return {"ok": False, "error": "title is required"}

        # Determine post kind
        kind = params.get("kind")
        if not kind:
            kind = "link" if url else "self"

        if kind == "link" and not url:
            return {"ok": False, "error": "url is required for link posts"}
        if kind == "self" and not text:
            return {"ok": False, "error": "text is required for self posts"}

        post_data: Dict[str, Any] = {
            "sr": subreddit,
            "title": title,
            "kind": kind,
            "api_type": "json",
            "sendreplies": str(params.get("send_replies", True)).lower(),
        }

        if kind == "self":
            post_data["text"] = text
        else:
            post_data["url"] = url

        if params.get("flair_id"):
            post_data["flair_id"] = params["flair_id"]
        if params.get("flair_text"):
            post_data["flair_text"] = params["flair_text"]
        if params.get("nsfw"):
            post_data["nsfw"] = "true"
        if params.get("spoiler"):
            post_data["spoiler"] = "true"

        result = _api_call(token, "/api/submit", user_agent, method="POST", data=post_data)

        if result.get("ok") and "result" in result:
            json_data = result["result"].get("json", {})
            errors = json_data.get("errors", [])
            if errors:
                return {"ok": False, "error": str(errors)}

            data = json_data.get("data", {})
            return {
                "ok": True,
                "data": {
                    "id": data.get("id"),
                    "name": data.get("name"),
                    "url": data.get("url"),
                }
            }
        return result
    except Exception as e:
        logger.exception("submit_post failed")
        return {"ok": False, "error": str(e)}


def get_post(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific post.

    Params:
        post_id (str): The post ID (with or without t3_ prefix) (required)

    Returns:
        Post details including title, body, score, etc.
    """
    try:
        profile = load_profile(profile_name)
        token = _get_access_token(profile, profile_name)
        user_agent = profile.get("user_agent", DEFAULT_USER_AGENT)

        post_id = params.get("post_id", "")
        if not post_id:
            return {"ok": False, "error": "post_id is required"}

        # Remove t3_ prefix if present
        if post_id.startswith("t3_"):
            post_id = post_id[3:]

        result = _api_call(token, f"/api/info?id=t3_{post_id}", user_agent)

        if result.get("ok") and "result" in result:
            children = result["result"].get("data", {}).get("children", [])
            if not children:
                return {"ok": False, "error": "Post not found"}

            post = children[0].get("data", {})
            return {
                "ok": True,
                "data": {
                    "id": post.get("id"),
                    "name": post.get("name"),
                    "title": post.get("title"),
                    "selftext": post.get("selftext"),
                    "url": post.get("url"),
                    "permalink": post.get("permalink"),
                    "subreddit": post.get("subreddit"),
                    "author": post.get("author"),
                    "score": post.get("score"),
                    "upvote_ratio": post.get("upvote_ratio"),
                    "num_comments": post.get("num_comments"),
                    "created_utc": post.get("created_utc"),
                    "is_self": post.get("is_self"),
                    "over_18": post.get("over_18"),
                    "spoiler": post.get("spoiler"),
                    "locked": post.get("locked"),
                    "archived": post.get("archived"),
                }
            }
        return result
    except Exception as e:
        logger.exception("get_post failed")
        return {"ok": False, "error": str(e)}


def list_subreddit_posts(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List posts from a subreddit.

    Params:
        subreddit (str): Subreddit name (required)
        sort (str): Sort method: 'hot', 'new', 'top', 'rising' (default: 'hot')
        limit (int): Number of posts to return (default: 25, max: 100)
        time (str): Time filter for 'top': 'hour', 'day', 'week', 'month', 'year', 'all' (default: 'day')
        after (str): Fullname of item to fetch after (for pagination)
        before (str): Fullname of item to fetch before (for pagination)

    Returns:
        List of posts with basic details
    """
    try:
        profile = load_profile(profile_name)
        token = _get_access_token(profile, profile_name)
        user_agent = profile.get("user_agent", DEFAULT_USER_AGENT)

        subreddit = params.get("subreddit", "")
        if not subreddit:
            return {"ok": False, "error": "subreddit is required"}

        sort = params.get("sort", "hot")
        if sort not in ["hot", "new", "top", "rising"]:
            return {"ok": False, "error": "sort must be one of: hot, new, top, rising"}

        limit = min(int(params.get("limit", 25)), 100)

        query_params: Dict[str, Any] = {"limit": limit}

        if sort == "top":
            query_params["t"] = params.get("time", "day")
        if params.get("after"):
            query_params["after"] = params["after"]
        if params.get("before"):
            query_params["before"] = params["before"]

        endpoint = f"/r/{subreddit}/{sort}"
        result = _api_call(token, endpoint, user_agent, data=query_params)

        if result.get("ok") and "result" in result:
            listing = result["result"].get("data", {})
            children = listing.get("children", [])

            posts = []
            for child in children:
                post = child.get("data", {})
                posts.append({
                    "id": post.get("id"),
                    "name": post.get("name"),
                    "title": post.get("title"),
                    "author": post.get("author"),
                    "score": post.get("score"),
                    "num_comments": post.get("num_comments"),
                    "created_utc": post.get("created_utc"),
                    "url": post.get("url"),
                    "permalink": post.get("permalink"),
                    "is_self": post.get("is_self"),
                })

            return {
                "ok": True,
                "data": {
                    "posts": posts,
                    "after": listing.get("after"),
                    "before": listing.get("before"),
                    "count": len(posts),
                }
            }
        return result
    except Exception as e:
        logger.exception("list_subreddit_posts failed")
        return {"ok": False, "error": str(e)}


def get_comments(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get comments for a specific post.

    Params:
        post_id (str): The post ID (with or without t3_ prefix) (required)
        subreddit (str): Subreddit name (optional, improves performance)
        sort (str): Sort method: 'confidence', 'top', 'new', 'controversial', 'old', 'qa' (default: 'confidence')
        limit (int): Number of comments to return (default: 100)
        depth (int): Maximum depth of comment tree (optional)

    Returns:
        List of comments with nested replies
    """
    try:
        profile = load_profile(profile_name)
        token = _get_access_token(profile, profile_name)
        user_agent = profile.get("user_agent", DEFAULT_USER_AGENT)

        post_id = params.get("post_id", "")
        if not post_id:
            return {"ok": False, "error": "post_id is required"}

        # Remove t3_ prefix if present
        if post_id.startswith("t3_"):
            post_id = post_id[3:]

        subreddit = params.get("subreddit", "all")
        sort = params.get("sort", "confidence")
        limit = min(int(params.get("limit", 100)), 500)

        query_params: Dict[str, Any] = {
            "sort": sort,
            "limit": limit,
        }
        if params.get("depth"):
            query_params["depth"] = params["depth"]

        endpoint = f"/r/{subreddit}/comments/{post_id}"
        result = _api_call(token, endpoint, user_agent, data=query_params)

        if result.get("ok") and "result" in result:
            # Reddit returns [post_listing, comments_listing]
            data = result["result"]
            if isinstance(data, list) and len(data) >= 2:
                comments_listing = data[1].get("data", {}).get("children", [])

                def parse_comment(comment_data: Dict[str, Any]) -> Dict[str, Any]:
                    c = comment_data.get("data", {})
                    parsed = {
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "author": c.get("author"),
                        "body": c.get("body"),
                        "score": c.get("score"),
                        "created_utc": c.get("created_utc"),
                        "is_submitter": c.get("is_submitter"),
                        "parent_id": c.get("parent_id"),
                        "depth": c.get("depth"),
                        "replies": [],
                    }

                    # Parse nested replies
                    replies = c.get("replies")
                    if replies and isinstance(replies, dict):
                        reply_children = replies.get("data", {}).get("children", [])
                        for reply in reply_children:
                            if reply.get("kind") == "t1":  # Comment type
                                parsed["replies"].append(parse_comment(reply))

                    return parsed

                comments = []
                for child in comments_listing:
                    if child.get("kind") == "t1":  # Comment type
                        comments.append(parse_comment(child))

                return {
                    "ok": True,
                    "data": {
                        "comments": comments,
                        "count": len(comments),
                    }
                }

            return {"ok": False, "error": "Unexpected response format"}
        return result
    except Exception as e:
        logger.exception("get_comments failed")
        return {"ok": False, "error": str(e)}


def post_comment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post a comment on a post or reply to a comment.

    Params:
        thing_id (str): The fullname of the post (t3_xxx) or comment (t1_xxx) to reply to (required)
        text (str): The comment text in Markdown (required)

    Returns:
        Comment details including ID
    """
    try:
        profile = load_profile(profile_name)
        token = _get_access_token(profile, profile_name)
        user_agent = profile.get("user_agent", DEFAULT_USER_AGENT)

        thing_id = params.get("thing_id", "")
        text = params.get("text", "")

        if not thing_id:
            return {"ok": False, "error": "thing_id is required"}
        if not text:
            return {"ok": False, "error": "text is required"}

        # Ensure proper prefix
        if not thing_id.startswith(("t1_", "t3_")):
            # Assume it's a post ID
            thing_id = f"t3_{thing_id}"

        post_data = {
            "thing_id": thing_id,
            "text": text,
            "api_type": "json",
        }

        result = _api_call(token, "/api/comment", user_agent, method="POST", data=post_data)

        if result.get("ok") and "result" in result:
            json_data = result["result"].get("json", {})
            errors = json_data.get("errors", [])
            if errors:
                return {"ok": False, "error": str(errors)}

            data = json_data.get("data", {})
            things = data.get("things", [])
            if things:
                comment = things[0].get("data", {})
                return {
                    "ok": True,
                    "data": {
                        "id": comment.get("id"),
                        "name": comment.get("name"),
                        "author": comment.get("author"),
                        "body": comment.get("body"),
                        "parent_id": comment.get("parent_id"),
                    }
                }
            return {"ok": True, "data": data}
        return result
    except Exception as e:
        logger.exception("post_comment failed")
        return {"ok": False, "error": str(e)}


def vote(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Vote on a post or comment.

    Params:
        thing_id (str): The fullname of the post (t3_xxx) or comment (t1_xxx) to vote on (required)
        direction (int): Vote direction: 1 (upvote), 0 (remove vote), -1 (downvote) (required)

    Returns:
        Success status
    """
    try:
        profile = load_profile(profile_name)
        token = _get_access_token(profile, profile_name)
        user_agent = profile.get("user_agent", DEFAULT_USER_AGENT)

        thing_id = params.get("thing_id", "")
        direction = params.get("direction")

        if not thing_id:
            return {"ok": False, "error": "thing_id is required"}
        if direction is None:
            return {"ok": False, "error": "direction is required (1, 0, or -1)"}

        direction = int(direction)
        if direction not in [1, 0, -1]:
            return {"ok": False, "error": "direction must be 1 (upvote), 0 (remove), or -1 (downvote)"}

        # Ensure proper prefix
        if not thing_id.startswith(("t1_", "t3_")):
            thing_id = f"t3_{thing_id}"

        post_data = {
            "id": thing_id,
            "dir": direction,
        }

        result = _api_call(token, "/api/vote", user_agent, method="POST", data=post_data)

        if result.get("ok"):
            return {
                "ok": True,
                "data": {
                    "thing_id": thing_id,
                    "direction": direction,
                    "status": "voted"
                }
            }
        return result
    except Exception as e:
        logger.exception("vote failed")
        return {"ok": False, "error": str(e)}


def search(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for posts on Reddit.

    Params:
        query (str): Search query (required)
        subreddit (str): Limit search to a specific subreddit (optional)
        sort (str): Sort method: 'relevance', 'hot', 'top', 'new', 'comments' (default: 'relevance')
        time (str): Time filter: 'hour', 'day', 'week', 'month', 'year', 'all' (default: 'all')
        limit (int): Number of results to return (default: 25, max: 100)
        after (str): Fullname of item to fetch after (for pagination)
        type (str): Type of results: 'link' (posts), 'sr' (subreddits), 'user' (default: 'link')

    Returns:
        List of search results
    """
    try:
        profile = load_profile(profile_name)
        token = _get_access_token(profile, profile_name)
        user_agent = profile.get("user_agent", DEFAULT_USER_AGENT)

        query = params.get("query", "")
        if not query:
            return {"ok": False, "error": "query is required"}

        subreddit = params.get("subreddit")
        sort = params.get("sort", "relevance")
        time_filter = params.get("time", "all")
        limit = min(int(params.get("limit", 25)), 100)
        result_type = params.get("type", "link")

        query_params: Dict[str, Any] = {
            "q": query,
            "sort": sort,
            "t": time_filter,
            "limit": limit,
            "type": result_type,
            "restrict_sr": "true" if subreddit else "false",
        }

        if params.get("after"):
            query_params["after"] = params["after"]

        if subreddit:
            endpoint = f"/r/{subreddit}/search"
        else:
            endpoint = "/search"

        result = _api_call(token, endpoint, user_agent, data=query_params)

        if result.get("ok") and "result" in result:
            listing = result["result"].get("data", {})
            children = listing.get("children", [])

            results = []
            for child in children:
                item = child.get("data", {})
                kind = child.get("kind")

                if kind == "t3":  # Post
                    results.append({
                        "type": "post",
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "title": item.get("title"),
                        "author": item.get("author"),
                        "subreddit": item.get("subreddit"),
                        "score": item.get("score"),
                        "num_comments": item.get("num_comments"),
                        "created_utc": item.get("created_utc"),
                        "url": item.get("url"),
                        "permalink": item.get("permalink"),
                        "is_self": item.get("is_self"),
                    })
                elif kind == "t5":  # Subreddit
                    results.append({
                        "type": "subreddit",
                        "id": item.get("id"),
                        "name": item.get("display_name"),
                        "title": item.get("title"),
                        "description": item.get("public_description"),
                        "subscribers": item.get("subscribers"),
                        "created_utc": item.get("created_utc"),
                    })
                elif kind == "t2":  # User
                    results.append({
                        "type": "user",
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "link_karma": item.get("link_karma"),
                        "comment_karma": item.get("comment_karma"),
                        "created_utc": item.get("created_utc"),
                    })

            return {
                "ok": True,
                "data": {
                    "results": results,
                    "after": listing.get("after"),
                    "before": listing.get("before"),
                    "count": len(results),
                }
            }
        return result
    except Exception as e:
        logger.exception("search failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "get_me": get_me,
    "submit_post": submit_post,
    "get_post": get_post,
    "list_subreddit_posts": list_subreddit_posts,
    "get_comments": get_comments,
    "post_comment": post_comment,
    "vote": vote,
    "search": search,
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

    logger.info(f"Executing reddit.{profile}.{action}")
    return ACTIONS[action](profile, params)
