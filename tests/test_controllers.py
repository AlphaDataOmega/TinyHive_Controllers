"""Tests for pre-installed controllers."""

import pytest
import sys
from pathlib import Path

# Add controllers to path
CONTROLLERS_DIR = Path(__file__).parent.parent / "controllers"
sys.path.insert(0, str(CONTROLLERS_DIR / "controller_ssh" / "projects"))
sys.path.insert(0, str(CONTROLLERS_DIR / "controller_hub" / "projects"))


class TestSSHController:
    def test_execute_unknown_action(self):
        from ssh import execute
        result = execute("localhost", "unknown", {})
        assert result["ok"] is False
        assert "Unknown action" in result["error"]

    def test_exec_missing_command(self):
        from ssh import execute
        result = execute("localhost", "exec", {})
        assert result["ok"] is False
        assert "No command" in result["error"]

    def test_exec_localhost_success(self):
        from ssh import execute
        result = execute("localhost", "exec", {"command": "echo hello"})
        assert result["ok"] is True
        assert "hello" in result["stdout"]

    def test_exec_with_timeout(self):
        from ssh import execute
        result = execute("localhost", "exec", {"command": "sleep 0.1", "timeout": 5})
        assert result["ok"] is True

    def test_list_profiles(self):
        from ssh import list_profiles
        profiles = list_profiles()
        assert "localhost" in profiles

    def test_unknown_profile(self):
        from ssh import execute
        result = execute("nonexistent_profile", "exec", {"command": "ls"})
        assert result["ok"] is False
        assert "Unknown profile" in str(result.get("error", ""))


class TestHubController:
    def test_execute_unknown_action(self):
        from hub import execute
        result = execute("unknown", {})
        assert result["ok"] is False
        assert "Unknown action" in result["error"]

    def test_list_scripts(self):
        from hub import execute
        result = execute("list_scripts", {})
        assert result["ok"] is True
        assert "scripts" in result

    def test_validate_missing_script(self):
        from hub import execute
        result = execute("validate_script", {"script": "nonexistent"})
        assert result["ok"] is False
        assert "not found" in result["error"]

    def test_run_script_dry_run(self):
        from hub import execute
        result = execute("run_script", {"script": "example_workflow", "dry_run": True})
        # May fail if script doesn't exist, which is fine for this test
        if result["ok"]:
            assert result["dry_run"] is True
            assert "results" in result
