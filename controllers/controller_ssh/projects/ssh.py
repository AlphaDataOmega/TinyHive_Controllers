"""SSH controller — remote and local command execution via profiles.

Profiles are JSON files in projects/profiles/ defining connection
targets (host, user, port, key path). Localhost profile is built-in.

Method IDs:
  controller.ssh.localhost.exec
  controller.ssh.{profile}.exec
  controller.ssh.{profile}.exec_script
  controller.ssh.{profile}.upload
  controller.ssh.{profile}.download
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List

log = logging.getLogger("tinyhive.controller.ssh")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"
SCRIPTS_DIR = WORKSPACE / "projects" / "scripts"

MAX_OUTPUT_BYTES = 64 * 1024  # 64KB output cap per command
DEFAULT_TIMEOUT = 30

# Built-in localhost profile — always available
LOCALHOST_PROFILE = {
    "host": "localhost",
    "user": "",
    "port": 22,
    "timeout": 30,
    "description": "Local execution (no SSH)",
}


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile. 'localhost' is built-in."""
    if name == "localhost":
        return LOCALHOST_PROFILE

    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Available: {list_profiles()}")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available profile names."""
    profiles = ["localhost"]
    if PROFILES_DIR.exists():
        profiles += [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]
    return profiles


# ---------------------------------------------------------------------------
# SSH command building
# ---------------------------------------------------------------------------

def _build_ssh_cmd(profile: Dict[str, Any]) -> List[str]:
    """Build base SSH command from profile."""
    host = profile.get("host", "localhost")
    if host == "localhost":
        return []  # local execution, no SSH

    user = profile.get("user", "")
    port = profile.get("port", 22)
    key_path = profile.get("key_path", "")

    cmd = ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-p", str(port)]
    if key_path:
        cmd.extend(["-i", key_path])
    target = f"{user}@{host}" if user else host
    cmd.append(target)
    return cmd


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def exec_cmd(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a command on the target host.

    Params:
        - command: The command to execute (required)
        - timeout: Command timeout in seconds (default: from profile or 30)
        - cwd: Working directory (default: from profile)
    """
    profile = load_profile(profile_name)
    command = params.get("command", "")
    timeout = params.get("timeout", profile.get("timeout", DEFAULT_TIMEOUT))
    cwd = params.get("cwd", profile.get("default_cwd"))

    if not command:
        return {"ok": False, "error": "No command provided"}

    ssh_base = _build_ssh_cmd(profile)

    if ssh_base:
        full_cmd = ssh_base + [command]
    else:
        full_cmd = ["bash", "-c", command]

    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
        )
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.decode("utf-8", errors="replace")[:MAX_OUTPUT_BYTES],
            "stderr": result.stderr.decode("utf-8", errors="replace")[:MAX_OUTPUT_BYTES],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timeout after {timeout}s"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def exec_script(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a script file from projects/scripts/.

    Params:
        - script: Script filename (required)
        - args: List of arguments to pass to script
        - timeout: Command timeout in seconds
    """
    script_name = params.get("script", "")
    script_args = params.get("args", [])

    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        return {"ok": False, "error": f"Script not found: {script_name}"}

    params["command"] = f"bash {script_path} {' '.join(str(a) for a in script_args)}"
    return exec_cmd(profile_name, params)


def upload(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Upload a file via SCP.

    Params:
        - local_path: Path to local file (required)
        - remote_path: Destination path on remote (required)
    """
    profile = load_profile(profile_name)
    local_path = params.get("local_path", "")
    remote_path = params.get("remote_path", "")

    if not local_path or not remote_path:
        return {"ok": False, "error": "local_path and remote_path required"}

    host = profile.get("host", "localhost")
    if host == "localhost":
        cmd = ["cp", local_path, remote_path]
    else:
        user = profile.get("user", "")
        port = profile.get("port", 22)
        key_path = profile.get("key_path", "")
        target = f"{user}@{host}:{remote_path}" if user else f"{host}:{remote_path}"
        cmd = ["scp", "-P", str(port)]
        if key_path:
            cmd.extend(["-i", key_path])
        cmd.extend([local_path, target])

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        return {"ok": result.returncode == 0, "returncode": result.returncode}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def download(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Download a file via SCP.

    Params:
        - remote_path: Path on remote host (required)
        - local_path: Destination path locally (required)
    """
    profile = load_profile(profile_name)
    remote_path = params.get("remote_path", "")
    local_path = params.get("local_path", "")

    if not remote_path or not local_path:
        return {"ok": False, "error": "remote_path and local_path required"}

    host = profile.get("host", "localhost")
    if host == "localhost":
        cmd = ["cp", remote_path, local_path]
    else:
        user = profile.get("user", "")
        port = profile.get("port", 22)
        key_path = profile.get("key_path", "")
        source = f"{user}@{host}:{remote_path}" if user else f"{host}:{remote_path}"
        cmd = ["scp", "-P", str(port)]
        if key_path:
            cmd.extend(["-i", key_path])
        cmd.extend([source, local_path])

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        return {"ok": result.returncode == 0, "returncode": result.returncode}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

ACTIONS = {
    "exec": exec_cmd,
    "exec_script": exec_script,
    "upload": upload,
    "download": download,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """Dispatch an action by name with a profile."""
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action '{action}'. Available: {list(ACTIONS.keys())}"}
    return ACTIONS[action](profile, params)
