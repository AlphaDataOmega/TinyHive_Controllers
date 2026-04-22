"""Telegram (Personal) controller — dispatches to the mcp-telegram MCP server.

Acts as a minimal MCP client: spawns ``mcp-telegram start`` as a stdio
subprocess, calls one tool, returns the result. First-pass skeleton —
each action call is a fresh subprocess. Persistent client sessions are
a follow-up (see package.json maturity="skeleton").

Authentication is a one-time user step performed outside this module:
``mcp-telegram login`` in a shell, which persists a session file that
the server reads on startup.

Method IDs:
  controller.telegram_mcp.{profile}.list_chats
  controller.telegram_mcp.{profile}.get_messages
  controller.telegram_mcp.{profile}.send_message
  controller.telegram_mcp.{profile}.search_messages
  controller.telegram_mcp.{profile}.get_contacts
  controller.telegram_mcp.{profile}.download_media
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

log = logging.getLogger("tinyhive.controller.telegram_mcp")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'")
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Action → MCP tool mapping
# ---------------------------------------------------------------------------
# Catalog-level action names (stable TinyHive vocabulary) map onto the
# actual tool names the mcp-telegram server exposes. These differ because
# the server folds some catalog actions into richer tools.
#
# Where a catalog action has no direct 1:1 tool, we translate arguments
# (e.g., search_messages → search_dialogs + get_messages shape).

_ACTION_TOOL_MAP = {
    "list_chats": "search_dialogs",      # empty query → all dialogs
    "get_messages": "get_messages",
    "send_message": "send_message",
    "search_messages": "search_dialogs", # argument-translated below
    "get_contacts": "search_dialogs",    # filtered to user type
    "download_media": "media_download",
}


def _translate_params(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Massage catalog-shape params into what mcp-telegram's tool expects."""
    if action == "list_chats":
        # search_dialogs with no query returns all dialogs
        return {"query": params.get("query", ""), "limit": params.get("limit", 50)}
    if action == "search_messages":
        # Fold into search_dialogs with query; message-level search is not
        # a separate tool in mcp-telegram.
        return {"query": params.get("query", ""), "limit": params.get("limit", 20)}
    if action == "get_contacts":
        # Contact filter — rely on search_dialogs with a user-type filter if
        # the server exposes one; otherwise return dialogs.
        return {"query": "", "limit": params.get("limit", 100), "chat_type": "user"}
    # Pass-through for 1:1 mapped actions
    return dict(params)


# ---------------------------------------------------------------------------
# MCP client (stdio) — minimal per-call session
# ---------------------------------------------------------------------------

async def _call_mcp_tool(
    profile: Dict[str, Any],
    tool_name: str,
    tool_args: Dict[str, Any],
) -> Dict[str, Any]:
    """Spawn mcp-telegram, call one tool, return its result.

    Returns TinyHive's canonical {"ok": bool, ...} envelope. Uses the MCP
    Python SDK's stdio transport. Requires `mcp` and `mcp-telegram` to be
    pip-installed in the Python environment that runs this controller.
    """
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        return {
            "ok": False,
            "error": (
                "MCP SDK not installed. Run `pip install mcp mcp-telegram` "
                "in the TinyHive Python environment."
            ),
        }

    # Env vars the mcp-telegram server reads at startup. The server reads
    # the credentials from env; auth is the pre-run `mcp-telegram login`
    # step, which writes a session file the server consumes automatically.
    api_id_env = profile.get("api_id_env", "TELEGRAM_API_ID")
    api_hash_env = profile.get("api_hash_env", "TELEGRAM_API_HASH")
    api_id = os.environ.get(api_id_env, "")
    api_hash = os.environ.get(api_hash_env, "")
    if not api_id or not api_hash:
        return {
            "ok": False,
            "error": (
                f"Missing {api_id_env} or {api_hash_env}. Set them via the "
                f"marketplace credential UI, then run `mcp-telegram login` once."
            ),
        }

    server_env = {
        **os.environ,
        "API_ID": api_id,
        "API_HASH": api_hash,
    }
    session_path = profile.get("session_path")
    if session_path:
        server_env["MCP_TELEGRAM_SESSION_PATH"] = session_path

    params = StdioServerParameters(
        command="mcp-telegram",
        args=["start"],
        env=server_env,
    )

    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, tool_args)
                # The SDK wraps tool output in a content list; unwrap
                # to the first text/JSON payload for TinyHive callers.
                content = getattr(result, "content", None) or []
                if not content:
                    return {"ok": True, "data": None}
                first = content[0]
                text = getattr(first, "text", None)
                if text is None:
                    return {"ok": True, "data": str(first)}
                try:
                    return {"ok": True, "data": json.loads(text)}
                except (ValueError, TypeError):
                    return {"ok": True, "data": text}
    except Exception as exc:
        log.error("mcp-telegram tool call failed: %s", exc)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Public action functions (catalog vocabulary)
# ---------------------------------------------------------------------------
# These are thin wrappers around _call_mcp_tool with action→tool mapping
# applied. They're async because the MCP SDK is async.

async def _dispatch(action: str, profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    profile = load_profile(profile_name)
    tool = _ACTION_TOOL_MAP.get(action)
    if tool is None:
        return {"ok": False, "error": f"Unknown action '{action}'. Available: {list(_ACTION_TOOL_MAP.keys())}"}
    translated = _translate_params(action, params)
    return await _call_mcp_tool(profile, tool, translated)


async def list_chats(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List dialogs (chats, groups, channels). Params: limit (default 50)."""
    return await _dispatch("list_chats", profile_name, params)


async def get_messages(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Read messages from a chat. Params: chat_id (required), limit."""
    return await _dispatch("get_messages", profile_name, params)


async def send_message(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Send a message as the user account.

    Params: chat_id, text (both required). Note: posts as YOU — SPINE
    approval bar is higher than a bot send.
    """
    return await _dispatch("send_message", profile_name, params)


async def search_messages(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Search across chats. Params: query (required), limit."""
    return await _dispatch("search_messages", profile_name, params)


async def get_contacts(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List contacts. Params: limit."""
    return await _dispatch("get_contacts", profile_name, params)


async def download_media(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Download media from a message. Params: chat_id, message_id."""
    return await _dispatch("download_media", profile_name, params)


# ---------------------------------------------------------------------------
# Action registry + sync-facing execute() shim
# ---------------------------------------------------------------------------

ACTIONS = {
    "list_chats": list_chats,
    "get_messages": get_messages,
    "send_message": send_message,
    "search_messages": search_messages,
    "get_contacts": get_contacts,
    "download_media": download_media,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """Dispatch an action by name with a profile.

    The controller runtime calls this synchronously. We bridge to the
    async MCP client by running the coroutine on a private loop if no
    loop is active, or scheduling onto the current loop otherwise.
    """
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action '{action}'. Available: {list(ACTIONS.keys())}"}

    import asyncio

    coro = ACTIONS[action](profile, params)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        # No running loop — run a fresh one synchronously.
        return asyncio.run(coro)

    # Running loop already exists. The safe pattern is a thread-pool
    # executor with its own loop so we don't try to nest loops.
    import concurrent.futures

    def _runner():
        inner_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(inner_loop)
        try:
            return inner_loop.run_until_complete(coro)
        finally:
            inner_loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_runner).result(timeout=60)
