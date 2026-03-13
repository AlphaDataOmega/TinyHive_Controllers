"""TinyHive Controller: Webhook management — send, receive, and verify webhooks.

This controller provides webhook functionality including:
- Sending HTTP POST webhooks with JSON payloads
- Verifying webhook signatures (GitHub, Stripe, Slack, custom HMAC)
- Running a lightweight HTTP server to receive webhooks
- Storing webhook events and handler registrations in SQLite

Method IDs:
  controller.webhook.{profile}.send_webhook
  controller.webhook.{profile}.verify_signature
  controller.webhook.{profile}.register_handler
  controller.webhook.{profile}.unregister_handler
  controller.webhook.{profile}.list_handlers
  controller.webhook.{profile}.get_recent_events
  controller.webhook.{profile}.start_server
  controller.webhook.{profile}.stop_server
"""

import hashlib
import hmac
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

log = logging.getLogger("tinyhive.controller.webhook")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"
DATA_DIR = WORKSPACE / "workspace" / "data"
DB_PATH = DATA_DIR / "webhooks.db"

# Global server instance for start/stop management
_server_instance: Optional[HTTPServer] = None
_server_thread: Optional[threading.Thread] = None
_server_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Database initialization
# ---------------------------------------------------------------------------

def _ensure_db() -> sqlite3.Connection:
    """Ensure database exists and return a connection."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS handlers (
            id TEXT PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            secret TEXT NOT NULL,
            provider TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL,
            active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            handler_id TEXT,
            path TEXT NOT NULL,
            method TEXT NOT NULL,
            headers TEXT,
            payload TEXT,
            signature_valid INTEGER,
            received_at TEXT NOT NULL,
            source_ip TEXT,
            FOREIGN KEY (handler_id) REFERENCES handlers(id)
        );

        CREATE INDEX IF NOT EXISTS idx_events_handler_id ON events(handler_id);
        CREATE INDEX IF NOT EXISTS idx_events_received_at ON events(received_at);
        CREATE INDEX IF NOT EXISTS idx_handlers_path ON handlers(path);
    """)
    conn.commit()

    return conn


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
# Signature verification helpers
# ---------------------------------------------------------------------------

def _verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature (X-Hub-Signature-256).

    GitHub uses HMAC-SHA256 with format: sha256=<hex_digest>
    """
    if not signature.startswith("sha256="):
        return False

    expected_sig = signature[7:]  # Remove "sha256=" prefix
    computed = hmac.new(
        secret.encode("utf-8"),
        payload if isinstance(payload, bytes) else payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed, expected_sig)


def _verify_stripe_signature(
    payload: bytes,
    signature: str,
    secret: str,
    timestamp: Optional[int] = None,
    tolerance: int = 300
) -> bool:
    """Verify Stripe webhook signature.

    Stripe signature format: t=<timestamp>,v1=<signature>,v0=<legacy_signature>
    The signed payload is: <timestamp>.<payload>
    """
    if isinstance(payload, bytes):
        payload_str = payload.decode("utf-8")
    else:
        payload_str = payload

    # Parse signature header
    sig_parts = {}
    for part in signature.split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            sig_parts[key] = value

    sig_timestamp = sig_parts.get("t")
    sig_v1 = sig_parts.get("v1")

    if not sig_timestamp or not sig_v1:
        return False

    # Check timestamp tolerance if provided
    if timestamp is not None:
        try:
            sig_ts = int(sig_timestamp)
            if abs(timestamp - sig_ts) > tolerance:
                return False
        except ValueError:
            return False

    # Compute expected signature
    signed_payload = f"{sig_timestamp}.{payload_str}"
    computed = hmac.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed, sig_v1)


def _verify_slack_signature(
    payload: bytes,
    signature: str,
    secret: str,
    timestamp: str
) -> bool:
    """Verify Slack webhook signature (X-Slack-Signature).

    Slack signature format: v0=<hex_digest>
    Signed payload: v0:<timestamp>:<body>
    """
    if not signature.startswith("v0="):
        return False

    expected_sig = signature[3:]  # Remove "v0=" prefix

    if isinstance(payload, bytes):
        payload_str = payload.decode("utf-8")
    else:
        payload_str = payload

    # Slack signing format
    sig_basestring = f"v0:{timestamp}:{payload_str}"
    computed = hmac.new(
        secret.encode("utf-8"),
        sig_basestring.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed, expected_sig)


def _verify_custom_signature(
    payload: bytes,
    signature: str,
    secret: str,
    algorithm: str = "sha256",
    prefix: str = ""
) -> bool:
    """Verify custom HMAC signature.

    Supports configurable algorithm and optional prefix.
    """
    if isinstance(payload, bytes):
        payload_bytes = payload
    else:
        payload_bytes = payload.encode("utf-8")

    # Remove prefix if present
    if prefix and signature.startswith(prefix):
        signature = signature[len(prefix):]

    # Get hash algorithm
    hash_algo = getattr(hashlib, algorithm, None)
    if hash_algo is None:
        return False

    computed = hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hash_algo
    ).hexdigest()

    return hmac.compare_digest(computed, signature)


# ---------------------------------------------------------------------------
# Webhook HTTP Server
# ---------------------------------------------------------------------------

class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP request handler for receiving webhooks."""

    def log_message(self, format: str, *args) -> None:
        """Override to use our logger."""
        log.debug("Webhook server: %s", format % args)

    def do_POST(self) -> None:
        """Handle incoming webhook POST requests."""
        try:
            # Read request body
            content_length = int(self.headers.get("Content-Length", 0))
            payload = self.rfile.read(content_length)

            # Get headers as dict
            headers_dict = {k: v for k, v in self.headers.items()}

            # Get source IP
            source_ip = self.client_address[0] if self.client_address else None

            # Store event in database
            conn = _ensure_db()
            try:
                # Find matching handler
                cursor = conn.execute(
                    "SELECT id, secret, provider FROM handlers WHERE path = ? AND active = 1",
                    (self.path,)
                )
                handler_row = cursor.fetchone()

                handler_id = None
                signature_valid = None

                if handler_row:
                    handler_id = handler_row["id"]
                    secret = handler_row["secret"]
                    provider = handler_row["provider"]

                    # Verify signature based on provider
                    signature_valid = _verify_incoming_signature(
                        provider, payload, headers_dict, secret
                    )

                # Store event
                event_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO events
                       (id, handler_id, path, method, headers, payload, signature_valid, received_at, source_ip)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id,
                        handler_id,
                        self.path,
                        "POST",
                        json.dumps(headers_dict),
                        payload.decode("utf-8", errors="replace"),
                        1 if signature_valid else (0 if signature_valid is False else None),
                        datetime.utcnow().isoformat(),
                        source_ip
                    )
                )
                conn.commit()

                # Send response
                if handler_id:
                    if signature_valid:
                        self.send_response(200)
                        response_body = json.dumps({"status": "received", "event_id": event_id})
                    else:
                        self.send_response(401)
                        response_body = json.dumps({"error": "Invalid signature"})
                else:
                    self.send_response(404)
                    response_body = json.dumps({"error": "No handler registered for this path"})

            finally:
                conn.close()

            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response_body.encode("utf-8"))

        except Exception as e:
            log.exception("Error handling webhook")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def do_GET(self) -> None:
        """Handle GET requests (health check)."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "service": "webhook-receiver"}).encode("utf-8"))


def _verify_incoming_signature(
    provider: str,
    payload: bytes,
    headers: Dict[str, str],
    secret: str
) -> bool:
    """Verify signature for incoming webhook based on provider."""
    provider = provider.lower()

    if provider == "github":
        signature = headers.get("X-Hub-Signature-256", "")
        return _verify_github_signature(payload, signature, secret)

    elif provider == "stripe":
        signature = headers.get("Stripe-Signature", "")
        return _verify_stripe_signature(payload, signature, secret)

    elif provider == "slack":
        signature = headers.get("X-Slack-Signature", "")
        timestamp = headers.get("X-Slack-Request-Timestamp", "")
        return _verify_slack_signature(payload, signature, secret, timestamp)

    elif provider == "custom":
        # For custom, look for common signature headers
        signature = (
            headers.get("X-Signature") or
            headers.get("X-Webhook-Signature") or
            headers.get("X-Hub-Signature") or
            ""
        )
        return _verify_custom_signature(payload, signature, secret)

    return False


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def send_webhook(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Send an HTTP POST webhook to a URL with JSON payload.

    Params:
        - url: Target webhook URL (required)
        - payload: JSON-serializable payload data (required)
        - headers: Additional headers dict (optional)
        - timeout: Request timeout in seconds (optional, default: 30)
    """
    url = params.get("url")
    payload = params.get("payload")
    headers = params.get("headers", {})
    timeout = params.get("timeout", 30)

    if not url:
        return {"ok": False, "error": "url is required"}
    if payload is None:
        return {"ok": False, "error": "payload is required"}

    try:
        # Prepare request
        request_headers = {
            "Content-Type": "application/json",
            "User-Agent": "TinyHive-Webhook/1.0",
        }
        request_headers.update(headers)

        body = json.dumps(payload).encode("utf-8")

        req = Request(url, data=body, headers=request_headers, method="POST")

        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            try:
                response_data = json.loads(response_body)
            except json.JSONDecodeError:
                response_data = response_body

            return {
                "ok": True,
                "result": {
                    "status_code": response.status,
                    "response": response_data,
                    "headers": dict(response.headers)
                }
            }

    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "error": f"HTTP {e.code}: {body[:500]}",
            "status_code": e.code
        }
    except URLError as e:
        return {"ok": False, "error": f"URL error: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def verify_signature(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Verify a webhook signature for different providers.

    Params:
        - provider: Provider type - "github", "stripe", "slack", or "custom" (required)
        - payload: The raw webhook payload string or bytes (required)
        - signature: The signature to verify (required)
        - secret: The webhook secret (required)
        - timestamp: Timestamp for stripe/slack verification (optional)
        - algorithm: Hash algorithm for custom provider (optional, default: sha256)
        - prefix: Signature prefix for custom provider (optional)
    """
    provider = params.get("provider", "").lower()
    payload = params.get("payload")
    signature = params.get("signature")
    secret = params.get("secret")
    timestamp = params.get("timestamp")
    algorithm = params.get("algorithm", "sha256")
    prefix = params.get("prefix", "")

    if not provider:
        return {"ok": False, "error": "provider is required"}
    if payload is None:
        return {"ok": False, "error": "payload is required"}
    if not signature:
        return {"ok": False, "error": "signature is required"}
    if not secret:
        return {"ok": False, "error": "secret is required"}

    if provider not in ("github", "stripe", "slack", "custom"):
        return {"ok": False, "error": f"Unsupported provider: {provider}"}

    # Convert payload to bytes if string
    if isinstance(payload, str):
        payload_bytes = payload.encode("utf-8")
    else:
        payload_bytes = payload

    try:
        if provider == "github":
            valid = _verify_github_signature(payload_bytes, signature, secret)

        elif provider == "stripe":
            valid = _verify_stripe_signature(
                payload_bytes, signature, secret, timestamp
            )

        elif provider == "slack":
            if not timestamp:
                return {"ok": False, "error": "timestamp is required for slack verification"}
            valid = _verify_slack_signature(
                payload_bytes, signature, secret, str(timestamp)
            )

        elif provider == "custom":
            valid = _verify_custom_signature(
                payload_bytes, signature, secret, algorithm, prefix
            )
        else:
            valid = False

        return {
            "ok": True,
            "result": {
                "valid": valid,
                "provider": provider
            }
        }

    except Exception as e:
        return {"ok": False, "error": f"Verification error: {str(e)}"}


def register_handler(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Register a webhook handler endpoint.

    Params:
        - path: The endpoint path (e.g., "/webhooks/github") (required)
        - secret: The webhook secret for signature verification (required)
        - provider: Provider type - "github", "stripe", "slack", or "custom" (required)
        - description: Human-readable description (optional)
    """
    path = params.get("path")
    secret = params.get("secret")
    provider = params.get("provider", "").lower()
    description = params.get("description", "")

    if not path:
        return {"ok": False, "error": "path is required"}
    if not secret:
        return {"ok": False, "error": "secret is required"}
    if not provider:
        return {"ok": False, "error": "provider is required"}
    if provider not in ("github", "stripe", "slack", "custom"):
        return {"ok": False, "error": f"Unsupported provider: {provider}"}

    # Ensure path starts with /
    if not path.startswith("/"):
        path = "/" + path

    try:
        conn = _ensure_db()
        try:
            handler_id = str(uuid.uuid4())

            conn.execute(
                """INSERT INTO handlers (id, path, secret, provider, description, created_at, active)
                   VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (handler_id, path, secret, provider, description, datetime.utcnow().isoformat())
            )
            conn.commit()

            return {
                "ok": True,
                "result": {
                    "handler_id": handler_id,
                    "path": path,
                    "provider": provider,
                    "description": description
                }
            }

        except sqlite3.IntegrityError:
            return {"ok": False, "error": f"Handler already exists for path: {path}"}
        finally:
            conn.close()

    except Exception as e:
        return {"ok": False, "error": str(e)}


def unregister_handler(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Remove a registered webhook handler.

    Params:
        - path: The endpoint path to unregister (optional)
        - handler_id: The handler ID to unregister (optional)

    One of path or handler_id must be provided.
    """
    path = params.get("path")
    handler_id = params.get("handler_id")

    if not path and not handler_id:
        return {"ok": False, "error": "Either path or handler_id is required"}

    try:
        conn = _ensure_db()
        try:
            if handler_id:
                cursor = conn.execute(
                    "DELETE FROM handlers WHERE id = ?",
                    (handler_id,)
                )
            else:
                # Ensure path starts with /
                if not path.startswith("/"):
                    path = "/" + path
                cursor = conn.execute(
                    "DELETE FROM handlers WHERE path = ?",
                    (path,)
                )

            conn.commit()

            if cursor.rowcount > 0:
                return {
                    "ok": True,
                    "result": {
                        "deleted": True,
                        "path": path,
                        "handler_id": handler_id
                    }
                }
            else:
                return {"ok": False, "error": "Handler not found"}

        finally:
            conn.close()

    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_handlers(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List all registered webhook handlers.

    Params:
        - active_only: Only show active handlers (optional, default: True)
    """
    active_only = params.get("active_only", True)

    try:
        conn = _ensure_db()
        try:
            if active_only:
                cursor = conn.execute(
                    "SELECT id, path, provider, description, created_at, active FROM handlers WHERE active = 1"
                )
            else:
                cursor = conn.execute(
                    "SELECT id, path, provider, description, created_at, active FROM handlers"
                )

            handlers = []
            for row in cursor.fetchall():
                handlers.append({
                    "handler_id": row["id"],
                    "path": row["path"],
                    "provider": row["provider"],
                    "description": row["description"],
                    "created_at": row["created_at"],
                    "active": bool(row["active"])
                })

            return {
                "ok": True,
                "result": {
                    "handlers": handlers,
                    "count": len(handlers)
                }
            }

        finally:
            conn.close()

    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_recent_events(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get recent webhook events from storage.

    Params:
        - limit: Maximum number of events to return (optional, default: 50)
        - handler_id: Filter by handler ID (optional)
        - since: Filter events after this ISO timestamp (optional)
    """
    limit = params.get("limit", 50)
    handler_id = params.get("handler_id")
    since = params.get("since")

    try:
        conn = _ensure_db()
        try:
            query = "SELECT * FROM events WHERE 1=1"
            query_params: List[Any] = []

            if handler_id:
                query += " AND handler_id = ?"
                query_params.append(handler_id)

            if since:
                query += " AND received_at > ?"
                query_params.append(since)

            query += " ORDER BY received_at DESC LIMIT ?"
            query_params.append(limit)

            cursor = conn.execute(query, query_params)

            events = []
            for row in cursor.fetchall():
                # Parse headers and payload from JSON
                try:
                    headers = json.loads(row["headers"]) if row["headers"] else {}
                except json.JSONDecodeError:
                    headers = {}

                try:
                    payload = json.loads(row["payload"]) if row["payload"] else None
                except json.JSONDecodeError:
                    payload = row["payload"]

                events.append({
                    "event_id": row["id"],
                    "handler_id": row["handler_id"],
                    "path": row["path"],
                    "method": row["method"],
                    "headers": headers,
                    "payload": payload,
                    "signature_valid": row["signature_valid"],
                    "received_at": row["received_at"],
                    "source_ip": row["source_ip"]
                })

            return {
                "ok": True,
                "result": {
                    "events": events,
                    "count": len(events)
                }
            }

        finally:
            conn.close()

    except Exception as e:
        return {"ok": False, "error": str(e)}


def start_server(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Start the HTTP server to receive webhooks.

    The server runs in a background thread (non-blocking).

    Params:
        - host: Host to bind to (optional, default: "0.0.0.0")
        - port: Port to listen on (optional, default: 8080)
    """
    global _server_instance, _server_thread

    host = params.get("host", "0.0.0.0")
    port = params.get("port", 8080)

    with _server_lock:
        if _server_instance is not None:
            return {
                "ok": False,
                "error": "Server is already running"
            }

        try:
            # Ensure database is initialized
            _ensure_db().close()

            # Create server
            server = HTTPServer((host, port), WebhookHandler)

            # Start server in background thread
            def serve_forever():
                log.info("Webhook server starting on %s:%d", host, port)
                server.serve_forever()

            thread = threading.Thread(target=serve_forever, daemon=True)
            thread.start()

            _server_instance = server
            _server_thread = thread

            return {
                "ok": True,
                "result": {
                    "status": "running",
                    "host": host,
                    "port": port,
                    "message": f"Webhook server started on {host}:{port}"
                }
            }

        except Exception as e:
            return {"ok": False, "error": f"Failed to start server: {str(e)}"}


def stop_server(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Stop the webhook receiver server.

    Params: None required.
    """
    global _server_instance, _server_thread

    with _server_lock:
        if _server_instance is None:
            return {
                "ok": False,
                "error": "Server is not running"
            }

        try:
            _server_instance.shutdown()
            _server_instance.server_close()

            if _server_thread is not None:
                _server_thread.join(timeout=5.0)

            _server_instance = None
            _server_thread = None

            return {
                "ok": True,
                "result": {
                    "status": "stopped",
                    "message": "Webhook server stopped"
                }
            }

        except Exception as e:
            return {"ok": False, "error": f"Failed to stop server: {str(e)}"}


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

ACTIONS = {
    "send_webhook": send_webhook,
    "verify_signature": verify_signature,
    "register_handler": register_handler,
    "unregister_handler": unregister_handler,
    "list_handlers": list_handlers,
    "get_recent_events": get_recent_events,
    "start_server": start_server,
    "stop_server": stop_server,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """Dispatch an action by name with a profile."""
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action '{action}'"}
    return ACTIONS[action](profile, params)
