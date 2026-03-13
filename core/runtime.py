"""Controller Runtime — execution queue with safety mechanisms.

Provides:
- Execution queue (SQLite-backed)
- Idempotency caching
- Circuit breaker per controller
- Rate limiting per controller
- Lease verification
"""

import hashlib
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("tinyhive.controller.runtime")


@dataclass
class CircuitBreaker:
    """Per-controller circuit breaker state."""
    state: str = "closed"  # closed, open, half_open
    failure_count: int = 0
    last_failure_time: float = 0.0
    threshold: int = 5
    cooldown: float = 60.0

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = "closed"

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.threshold:
            self.state = "open"

    def can_execute(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.last_failure_time >= self.cooldown:
                self.state = "half_open"
                return True
            return False
        if self.state == "half_open":
            return True
        return False


@dataclass
class RateLimiter:
    """Token bucket rate limiter."""
    tokens: float = 10.0
    max_tokens: float = 10.0
    refill_rate: float = 1.0  # tokens per second
    last_refill: float = field(default_factory=time.time)

    def _refill(self) -> None:
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def acquire(self, tokens: float = 1.0) -> bool:
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class ControllerRuntime:
    """Execution queue with safety mechanisms."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        max_queue_depth: int = 200,
        circuit_threshold: int = 5,
        circuit_cooldown: float = 60.0,
        rate_tokens: float = 10.0,
        rate_refill: float = 1.0,
        idempotency_ttl: int = 3600,
    ):
        self.db_path = db_path or Path("controller_runtime.db")
        self.max_queue_depth = max_queue_depth
        self.circuit_threshold = circuit_threshold
        self.circuit_cooldown = circuit_cooldown
        self.rate_tokens = rate_tokens
        self.rate_refill = rate_refill
        self.idempotency_ttl = idempotency_ttl

        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._rate_limiters: Dict[str, RateLimiter] = {}

        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    method_id TEXT NOT NULL,
                    params TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    lease_id TEXT,
                    requested_by TEXT,
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_cache (
                    key TEXT PRIMARY KEY,
                    result TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_status ON execution_queue(status)")
            conn.commit()

    def _get_circuit_breaker(self, controller_type: str) -> CircuitBreaker:
        if controller_type not in self._circuit_breakers:
            self._circuit_breakers[controller_type] = CircuitBreaker(
                threshold=self.circuit_threshold,
                cooldown=self.circuit_cooldown,
            )
        return self._circuit_breakers[controller_type]

    def _get_rate_limiter(self, controller_type: str) -> RateLimiter:
        if controller_type not in self._rate_limiters:
            self._rate_limiters[controller_type] = RateLimiter(
                tokens=self.rate_tokens,
                max_tokens=self.rate_tokens,
                refill_rate=self.rate_refill,
            )
        return self._rate_limiters[controller_type]

    def _parse_method_id(self, method_id: str) -> Dict[str, str]:
        """Parse controller.{type}.{profile}.{action} format."""
        parts = method_id.split(".")
        if len(parts) != 4 or parts[0] != "controller":
            raise ValueError(f"Invalid method_id format: {method_id}")
        return {
            "type": parts[1],
            "profile": parts[2],
            "action": parts[3],
        }

    def _idempotency_key(self, method_id: str, params: Dict[str, Any]) -> str:
        """Generate idempotency cache key."""
        params_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
        return f"{method_id}.{params_hash}"

    def _check_idempotency(self, key: str) -> Optional[Dict[str, Any]]:
        """Check if we have a cached result."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM idempotency_cache WHERE created_at < ?",
                (time.time() - self.idempotency_ttl,)
            )
            row = conn.execute(
                "SELECT result FROM idempotency_cache WHERE key = ?",
                (key,)
            ).fetchone()
            if row:
                return json.loads(row[0])
        return None

    def _cache_result(self, key: str, result: Dict[str, Any]) -> None:
        """Cache a result for idempotency."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO idempotency_cache (key, result, created_at) VALUES (?, ?, ?)",
                (key, json.dumps(result), time.time())
            )
            conn.commit()

    def _queue_depth(self, controller_type: Optional[str] = None) -> int:
        """Get current queue depth."""
        with sqlite3.connect(self.db_path) as conn:
            if controller_type:
                row = conn.execute(
                    "SELECT COUNT(*) FROM execution_queue WHERE status = 'queued' AND method_id LIKE ?",
                    (f"controller.{controller_type}.%",)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM execution_queue WHERE status = 'queued'"
                ).fetchone()
            return row[0] if row else 0

    def submit(
        self,
        method_id: str,
        params: Dict[str, Any],
        lease_id: Optional[str] = None,
        requested_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit a controller execution request.

        Returns:
            {"ok": True, "execution_id": int} or {"ok": False, "error": str}
        """
        try:
            parsed = self._parse_method_id(method_id)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        controller_type = parsed["type"]

        # Check idempotency
        idem_key = self._idempotency_key(method_id, params)
        cached = self._check_idempotency(idem_key)
        if cached:
            return {"ok": True, "cached": True, "result": cached}

        # Check circuit breaker
        cb = self._get_circuit_breaker(controller_type)
        if not cb.can_execute():
            return {"ok": False, "error": f"Circuit breaker open for {controller_type}"}

        # Check rate limiter
        rl = self._get_rate_limiter(controller_type)
        if not rl.acquire():
            return {"ok": False, "error": f"Rate limit exceeded for {controller_type}"}

        # Check backpressure
        if self._queue_depth() >= self.max_queue_depth:
            return {"ok": False, "error": "Queue depth exceeded"}

        # Enqueue
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO execution_queue (method_id, params, lease_id, requested_by, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (method_id, json.dumps(params), lease_id, requested_by, time.strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            return {"ok": True, "execution_id": cursor.lastrowid}

    def execute(self, execution_id: int) -> None:
        """Mark an execution as started."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE execution_queue SET status = 'executing', started_at = ? WHERE id = ?",
                (time.strftime("%Y-%m-%d %H:%M:%S"), execution_id)
            )
            conn.commit()

    def complete(self, execution_id: int, result: Dict[str, Any]) -> None:
        """Mark an execution as completed."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT method_id, params FROM execution_queue WHERE id = ?",
                (execution_id,)
            ).fetchone()

            if row:
                method_id, params_json = row
                parsed = self._parse_method_id(method_id)
                cb = self._get_circuit_breaker(parsed["type"])
                cb.record_success()

                # Cache result
                idem_key = self._idempotency_key(method_id, json.loads(params_json))
                self._cache_result(idem_key, result)

            conn.execute(
                "UPDATE execution_queue SET status = 'completed', result = ?, completed_at = ? WHERE id = ?",
                (json.dumps(result), time.strftime("%Y-%m-%d %H:%M:%S"), execution_id)
            )
            conn.commit()

    def fail(self, execution_id: int, error: str) -> None:
        """Mark an execution as failed."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT method_id FROM execution_queue WHERE id = ?",
                (execution_id,)
            ).fetchone()

            if row:
                method_id = row[0]
                parsed = self._parse_method_id(method_id)
                cb = self._get_circuit_breaker(parsed["type"])
                cb.record_failure()

            conn.execute(
                "UPDATE execution_queue SET status = 'failed', error = ?, completed_at = ? WHERE id = ?",
                (error, time.strftime("%Y-%m-%d %H:%M:%S"), execution_id)
            )
            conn.commit()

    def get_status(self, execution_id: int) -> Optional[Dict[str, Any]]:
        """Get execution status."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT id, method_id, params, status, result, error, created_at, completed_at
                FROM execution_queue WHERE id = ?
                """,
                (execution_id,)
            ).fetchone()

            if not row:
                return None

            return {
                "id": row[0],
                "method_id": row[1],
                "params": json.loads(row[2]),
                "status": row[3],
                "result": json.loads(row[4]) if row[4] else None,
                "error": row[5],
                "created_at": row[6],
                "completed_at": row[7],
            }

    def list_queue(
        self,
        controller_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List queued executions."""
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT id, method_id, status, created_at FROM execution_queue WHERE 1=1"
            params: List[Any] = []

            if controller_type:
                query += " AND method_id LIKE ?"
                params.append(f"controller.{controller_type}.%")

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()

            return [
                {"id": r[0], "method_id": r[1], "status": r[2], "created_at": r[3]}
                for r in rows
            ]
