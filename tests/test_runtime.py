"""Tests for ControllerRuntime."""

import pytest
import tempfile
from pathlib import Path

from core.runtime import ControllerRuntime, CircuitBreaker, RateLimiter


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == "closed"
        assert cb.can_execute() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"
        assert cb.can_execute() is False

    def test_success_resets_count(self):
        cb = CircuitBreaker(threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == "closed"


class TestRateLimiter:
    def test_initial_tokens(self):
        rl = RateLimiter(tokens=5.0)
        assert rl.acquire(1.0) is True
        assert rl.tokens == 4.0

    def test_exhausted(self):
        rl = RateLimiter(tokens=1.0, refill_rate=0.0)
        assert rl.acquire(1.0) is True
        assert rl.acquire(1.0) is False


class TestControllerRuntime:
    @pytest.fixture
    def runtime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_runtime.db"
            yield ControllerRuntime(db_path=db_path)

    def test_submit_valid(self, runtime):
        result = runtime.submit(
            method_id="controller.ssh.localhost.exec",
            params={"command": "ls"},
        )
        assert result["ok"] is True
        assert "execution_id" in result

    def test_submit_invalid_method_id(self, runtime):
        result = runtime.submit(
            method_id="invalid",
            params={},
        )
        assert result["ok"] is False
        assert "Invalid method_id" in result["error"]

    def test_idempotency_cache(self, runtime):
        # First submission
        result1 = runtime.submit(
            method_id="controller.ssh.localhost.exec",
            params={"command": "ls"},
        )
        assert result1["ok"] is True
        exec_id = result1["execution_id"]

        # Complete it
        runtime.complete(exec_id, {"ok": True, "output": "file.txt"})

        # Second submission with same params should be cached
        result2 = runtime.submit(
            method_id="controller.ssh.localhost.exec",
            params={"command": "ls"},
        )
        assert result2["ok"] is True
        assert result2.get("cached") is True

    def test_get_status(self, runtime):
        result = runtime.submit(
            method_id="controller.ssh.localhost.exec",
            params={"command": "ls"},
        )
        exec_id = result["execution_id"]

        status = runtime.get_status(exec_id)
        assert status is not None
        assert status["status"] == "queued"
        assert status["method_id"] == "controller.ssh.localhost.exec"

    def test_execute_and_complete(self, runtime):
        result = runtime.submit(
            method_id="controller.ssh.localhost.exec",
            params={"command": "ls"},
        )
        exec_id = result["execution_id"]

        runtime.execute(exec_id)
        status = runtime.get_status(exec_id)
        assert status["status"] == "executing"

        runtime.complete(exec_id, {"ok": True, "output": "done"})
        status = runtime.get_status(exec_id)
        assert status["status"] == "completed"
        assert status["result"]["ok"] is True

    def test_fail_triggers_circuit_breaker(self, runtime):
        # Submit and fail multiple times
        for _ in range(5):
            result = runtime.submit(
                method_id="controller.test.default.action",
                params={"x": _},  # Different params to avoid idempotency
            )
            if result["ok"]:
                runtime.fail(result["execution_id"], "test failure")

        # Next submission should be blocked by circuit breaker
        result = runtime.submit(
            method_id="controller.test.default.action",
            params={"x": "final"},
        )
        assert result["ok"] is False
        assert "Circuit breaker" in result["error"]

    def test_list_queue(self, runtime):
        runtime.submit("controller.ssh.localhost.exec", {"command": "ls"})
        runtime.submit("controller.ssh.localhost.exec", {"command": "pwd"})
        runtime.submit("controller.hub.default.list_scripts", {})

        # List all
        items = runtime.list_queue()
        assert len(items) == 3

        # List by type
        ssh_items = runtime.list_queue(controller_type="ssh")
        assert len(ssh_items) == 2

        hub_items = runtime.list_queue(controller_type="hub")
        assert len(hub_items) == 1
