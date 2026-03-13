"""
Redis Controller for TinyHive

A Redis controller using direct socket connections with the RESP protocol.
No external dependencies - uses only Python standard library.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "url_env": "REDIS_URL",  // Environment variable containing Redis URL
    "timeout": 30,           // Connection timeout in seconds (default: 30)
    "max_retries": 3         // Max connection retries (default: 3)
}

Redis URL Format:
    redis://[:password@]host:port/db
    redis://:mypassword@localhost:6379/0
    redis://localhost:6379/0

Method IDs:
    controller.redis.{profile}.get
    controller.redis.{profile}.set
    controller.redis.{profile}.delete
    controller.redis.{profile}.exists
    controller.redis.{profile}.keys
    controller.redis.{profile}.hget
    controller.redis.{profile}.hset
    controller.redis.{profile}.lpush
    controller.redis.{profile}.lrange
    controller.redis.{profile}.expire

Dependencies:
------------
None - uses only Python standard library (socket)
"""

import json
import logging
import os
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

logger = logging.getLogger("tinyhive.controller.redis")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

DEFAULT_TIMEOUT = 30
DEFAULT_PORT = 6379
DEFAULT_DB = 0


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


# =============================================================================
# Redis URL Parser
# =============================================================================

def parse_redis_url(url: str) -> Dict[str, Any]:
    """
    Parse Redis URL into connection parameters.

    Format: redis://[:password@]host:port/db

    Returns:
        {
            "host": str,
            "port": int,
            "password": str or None,
            "db": int
        }
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("redis", "rediss"):
        raise ValueError(f"Invalid Redis URL scheme: {parsed.scheme}")

    host = parsed.hostname or "localhost"
    port = parsed.port or DEFAULT_PORT
    password = parsed.password

    # Parse database number from path
    db = DEFAULT_DB
    if parsed.path and parsed.path != "/":
        try:
            db = int(parsed.path.lstrip("/"))
        except ValueError:
            raise ValueError(f"Invalid database number in URL path: {parsed.path}")

    return {
        "host": host,
        "port": port,
        "password": password,
        "db": db,
        "ssl": parsed.scheme == "rediss"
    }


# =============================================================================
# RESP Protocol Implementation
# =============================================================================

class RESPProtocol:
    """Redis Serialization Protocol (RESP) encoder/decoder."""

    CRLF = b"\r\n"

    @staticmethod
    def encode(args: List[Union[str, int, bytes]]) -> bytes:
        """
        Encode a command as a RESP array.

        Example: ["SET", "key", "value"] -> *3\r\n$3\r\nSET\r\n$3\r\nkey\r\n$5\r\nvalue\r\n
        """
        parts = [f"*{len(args)}".encode()]

        for arg in args:
            if isinstance(arg, bytes):
                data = arg
            elif isinstance(arg, str):
                data = arg.encode("utf-8")
            else:
                data = str(arg).encode("utf-8")

            parts.append(f"${len(data)}".encode())
            parts.append(data)

        return RESPProtocol.CRLF.join(parts) + RESPProtocol.CRLF

    @staticmethod
    def decode(sock: socket.socket) -> Any:
        """
        Decode a RESP response from the socket.

        Returns:
            - Simple strings: str
            - Errors: raises Exception
            - Integers: int
            - Bulk strings: str or None
            - Arrays: list
        """
        def read_line() -> bytes:
            """Read a line terminated by CRLF."""
            buf = b""
            while True:
                char = sock.recv(1)
                if not char:
                    raise ConnectionError("Connection closed by server")
                buf += char
                if buf.endswith(RESPProtocol.CRLF):
                    return buf[:-2]

        def read_bytes(n: int) -> bytes:
            """Read exactly n bytes."""
            data = b""
            while len(data) < n:
                chunk = sock.recv(n - len(data))
                if not chunk:
                    raise ConnectionError("Connection closed by server")
                data += chunk
            return data

        line = read_line()
        if not line:
            raise ConnectionError("Empty response from server")

        prefix = chr(line[0])
        payload = line[1:].decode("utf-8")

        if prefix == "+":
            # Simple string
            return payload

        elif prefix == "-":
            # Error
            raise Exception(f"Redis error: {payload}")

        elif prefix == ":":
            # Integer
            return int(payload)

        elif prefix == "$":
            # Bulk string
            length = int(payload)
            if length == -1:
                return None
            data = read_bytes(length)
            read_bytes(2)  # Read trailing CRLF
            return data.decode("utf-8")

        elif prefix == "*":
            # Array
            count = int(payload)
            if count == -1:
                return None
            return [RESPProtocol.decode(sock) for _ in range(count)]

        else:
            raise ValueError(f"Unknown RESP prefix: {prefix}")


# =============================================================================
# Redis Connection
# =============================================================================

class RedisConnection:
    """A simple Redis connection using raw sockets."""

    def __init__(self, host: str, port: int, password: Optional[str] = None,
                 db: int = 0, timeout: int = DEFAULT_TIMEOUT, ssl: bool = False):
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self.timeout = timeout
        self.ssl = ssl
        self._sock: Optional[socket.socket] = None

    def connect(self) -> None:
        """Establish connection to Redis server."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(self.timeout)

        try:
            self._sock.connect((self.host, self.port))

            if self.ssl:
                import ssl as ssl_module
                context = ssl_module.create_default_context()
                self._sock = context.wrap_socket(self._sock, server_hostname=self.host)

            # Authenticate if password provided
            if self.password:
                self._send_command("AUTH", self.password)

            # Select database
            if self.db != 0:
                self._send_command("SELECT", str(self.db))

        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Close the connection."""
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _send_command(self, *args: Union[str, int, bytes]) -> Any:
        """Send a command and return the response."""
        if not self._sock:
            raise ConnectionError("Not connected to Redis")

        cmd = RESPProtocol.encode(list(args))
        self._sock.sendall(cmd)
        return RESPProtocol.decode(self._sock)

    def execute(self, *args: Union[str, int, bytes]) -> Any:
        """Execute a Redis command."""
        return self._send_command(*args)

    def __enter__(self) -> "RedisConnection":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def get_connection(profile_name: str) -> RedisConnection:
    """Get a Redis connection for the given profile."""
    profile = load_profile(profile_name)

    url_env = profile.get("url_env", "REDIS_URL")
    url = os.environ.get(url_env)

    if not url:
        raise ValueError(f"Environment variable '{url_env}' not set")

    params = parse_redis_url(url)

    return RedisConnection(
        host=params["host"],
        port=params["port"],
        password=params["password"],
        db=params["db"],
        timeout=profile.get("timeout", DEFAULT_TIMEOUT),
        ssl=params["ssl"]
    )


# =============================================================================
# Actions
# =============================================================================

def get(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the value of a key.

    Params:
        key (str): The key to get (required)

    Returns:
        {"ok": True, "data": <value or null>}
    """
    key = params.get("key")
    if not key:
        return {"ok": False, "error": "key is required"}

    try:
        with get_connection(profile_name) as conn:
            result = conn.execute("GET", key)
            return {"ok": True, "data": result}
    except Exception as e:
        logger.exception("get failed")
        return {"ok": False, "error": str(e)}


def set_(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Set the value of a key.

    Params:
        key (str): The key to set (required)
        value (str): The value to set (required)
        ex (int): Expire time in seconds (optional)
        px (int): Expire time in milliseconds (optional)
        nx (bool): Only set if key does not exist (optional)
        xx (bool): Only set if key exists (optional)

    Returns:
        {"ok": True, "result": "OK"} or {"ok": True, "result": null} if NX/XX condition not met
    """
    key = params.get("key")
    value = params.get("value")

    if not key:
        return {"ok": False, "error": "key is required"}
    if value is None:
        return {"ok": False, "error": "value is required"}

    try:
        with get_connection(profile_name) as conn:
            args: List[Union[str, int]] = ["SET", key, str(value)]

            # Handle expiry options
            if params.get("ex"):
                args.extend(["EX", int(params["ex"])])
            elif params.get("px"):
                args.extend(["PX", int(params["px"])])

            # Handle NX/XX options
            if params.get("nx"):
                args.append("NX")
            elif params.get("xx"):
                args.append("XX")

            result = conn.execute(*args)
            return {"ok": True, "result": result}
    except Exception as e:
        logger.exception("set failed")
        return {"ok": False, "error": str(e)}


def delete(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete one or more keys.

    Params:
        keys (list[str]): List of keys to delete (required)

    Returns:
        {"ok": True, "result": <number of keys deleted>}
    """
    keys = params.get("keys")
    if not keys:
        return {"ok": False, "error": "keys is required"}

    if isinstance(keys, str):
        keys = [keys]

    try:
        with get_connection(profile_name) as conn:
            result = conn.execute("DEL", *keys)
            return {"ok": True, "result": result}
    except Exception as e:
        logger.exception("delete failed")
        return {"ok": False, "error": str(e)}


def exists(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check if a key exists.

    Params:
        key (str): The key to check (required)

    Returns:
        {"ok": True, "data": True/False}
    """
    key = params.get("key")
    if not key:
        return {"ok": False, "error": "key is required"}

    try:
        with get_connection(profile_name) as conn:
            result = conn.execute("EXISTS", key)
            return {"ok": True, "data": result == 1}
    except Exception as e:
        logger.exception("exists failed")
        return {"ok": False, "error": str(e)}


def keys(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Find all keys matching a pattern.

    Params:
        pattern (str): The pattern to match (required, e.g., "user:*")

    Returns:
        {"ok": True, "data": [<list of matching keys>]}

    Warning: KEYS is O(N) and should be used with caution in production.
    Consider using SCAN for large datasets.
    """
    pattern = params.get("pattern")
    if not pattern:
        return {"ok": False, "error": "pattern is required"}

    try:
        with get_connection(profile_name) as conn:
            result = conn.execute("KEYS", pattern)
            return {"ok": True, "data": result or []}
    except Exception as e:
        logger.exception("keys failed")
        return {"ok": False, "error": str(e)}


def hget(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the value of a hash field.

    Params:
        key (str): The hash key (required)
        field (str): The field name (required)

    Returns:
        {"ok": True, "data": <value or null>}
    """
    key = params.get("key")
    field = params.get("field")

    if not key:
        return {"ok": False, "error": "key is required"}
    if not field:
        return {"ok": False, "error": "field is required"}

    try:
        with get_connection(profile_name) as conn:
            result = conn.execute("HGET", key, field)
            return {"ok": True, "data": result}
    except Exception as e:
        logger.exception("hget failed")
        return {"ok": False, "error": str(e)}


def hset(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Set the value of a hash field.

    Params:
        key (str): The hash key (required)
        field (str): The field name (required)
        value (str): The value to set (required)

    Returns:
        {"ok": True, "result": <1 if new field, 0 if updated>}
    """
    key = params.get("key")
    field = params.get("field")
    value = params.get("value")

    if not key:
        return {"ok": False, "error": "key is required"}
    if not field:
        return {"ok": False, "error": "field is required"}
    if value is None:
        return {"ok": False, "error": "value is required"}

    try:
        with get_connection(profile_name) as conn:
            result = conn.execute("HSET", key, field, str(value))
            return {"ok": True, "result": result}
    except Exception as e:
        logger.exception("hset failed")
        return {"ok": False, "error": str(e)}


def lpush(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Push values to the head of a list.

    Params:
        key (str): The list key (required)
        values (list[str]): Values to push (required)

    Returns:
        {"ok": True, "result": <length of list after push>}
    """
    key = params.get("key")
    values = params.get("values")

    if not key:
        return {"ok": False, "error": "key is required"}
    if not values:
        return {"ok": False, "error": "values is required"}

    if isinstance(values, str):
        values = [values]

    try:
        with get_connection(profile_name) as conn:
            result = conn.execute("LPUSH", key, *[str(v) for v in values])
            return {"ok": True, "result": result}
    except Exception as e:
        logger.exception("lpush failed")
        return {"ok": False, "error": str(e)}


def lrange(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a range of elements from a list.

    Params:
        key (str): The list key (required)
        start (int): Start index (default: 0)
        stop (int): Stop index (default: -1, meaning end of list)

    Returns:
        {"ok": True, "data": [<list of elements>]}
    """
    key = params.get("key")
    if not key:
        return {"ok": False, "error": "key is required"}

    start = params.get("start", 0)
    stop = params.get("stop", -1)

    try:
        with get_connection(profile_name) as conn:
            result = conn.execute("LRANGE", key, str(start), str(stop))
            return {"ok": True, "data": result or []}
    except Exception as e:
        logger.exception("lrange failed")
        return {"ok": False, "error": str(e)}


def expire(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Set a timeout on a key.

    Params:
        key (str): The key (required)
        seconds (int): Expire time in seconds (required)

    Returns:
        {"ok": True, "result": True} if timeout was set
        {"ok": True, "result": False} if key does not exist
    """
    key = params.get("key")
    seconds = params.get("seconds")

    if not key:
        return {"ok": False, "error": "key is required"}
    if seconds is None:
        return {"ok": False, "error": "seconds is required"}

    try:
        with get_connection(profile_name) as conn:
            result = conn.execute("EXPIRE", key, str(int(seconds)))
            return {"ok": True, "result": result == 1}
    except Exception as e:
        logger.exception("expire failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "get": get,
    "set": set_,
    "delete": delete,
    "exists": exists,
    "keys": keys,
    "hget": hget,
    "hset": hset,
    "lpush": lpush,
    "lrange": lrange,
    "expire": expire,
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
        return {"ok": False, "error": f"Unknown action: {action}"}

    logger.info(f"Executing redis.{profile}.{action}")
    return ACTIONS[action](profile, params)
