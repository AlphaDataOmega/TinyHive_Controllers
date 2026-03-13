"""Controller Hub — multi-controller orchestration via execution scripts.

Reads execution scripts (JSON) from this directory that define
multi-step workflows across controllers. Think of it as a lightweight
workflow engine that sequences controller calls through BODY.

Method IDs:
  controller.hub.default.run_script
  controller.hub.default.list_scripts
  controller.hub.default.validate_script
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

log = logging.getLogger("tinyhive.controller.hub")

WORKSPACE = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = WORKSPACE / "projects"


# ---------------------------------------------------------------------------
# Script loading
# ---------------------------------------------------------------------------

def load_script(name: str) -> Dict[str, Any]:
    """Load an execution script by name (.json or .js)."""
    for ext in [".json", ".js"]:
        path = SCRIPTS_DIR / f"{name}{ext}"
        if path.exists():
            text = path.read_text()
            if ext == ".js":
                lines = [l for l in text.splitlines()
                         if not l.strip().startswith("//")]
                text = "\n".join(lines)
            return json.loads(text)
    raise FileNotFoundError(f"Script '{name}' not found in {SCRIPTS_DIR}")


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def run_script(params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a multi-step orchestration script.

    Script format:
    {
      "name": "daily-digest",
      "description": "Collect and send daily digest",
      "steps": [
        {
          "id": "fetch_emails",
          "controller": "google",
          "profile": "gmail",
          "action": "list_messages",
          "params": {"query": "is:unread", "limit": 10}
        },
        {
          "id": "notify",
          "controller": "telegram",
          "profile": "default",
          "action": "send_message",
          "params": {"text": "$fetch_emails.summary"}
        }
      ]
    }

    Params:
        - script: Script name (without extension)
        - dry_run: If true, don't execute, just plan

    Returns results keyed by step ID. Actual dispatch goes through
    BODY's ControllerRuntime — this builds the execution plan.
    """
    script_name = params.get("script", "")
    dry_run = params.get("dry_run", False)

    try:
        script = load_script(script_name)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}

    steps = script.get("steps", [])
    results: Dict[str, Any] = {}

    for step in steps:
        step_id = step.get("id", f"step_{len(results)}")
        method_id = (
            f"controller.{step['controller']}."
            f"{step.get('profile', 'default')}.{step['action']}"
        )

        if dry_run:
            results[step_id] = {
                "status": "dry_run",
                "method_id": method_id,
                "params": step.get("params", {}),
            }
        else:
            # Queue for dispatch via ControllerRuntime
            results[step_id] = {
                "status": "queued",
                "method_id": method_id,
                "params": step.get("params", {}),
                "queued_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

    return {
        "ok": True,
        "script": script_name,
        "steps_total": len(steps),
        "dry_run": dry_run,
        "results": results,
    }


def list_scripts(params: Dict[str, Any] = None) -> Dict[str, Any]:
    """List available execution scripts."""
    scripts: List[Dict[str, Any]] = []
    if SCRIPTS_DIR.exists():
        for p in sorted(SCRIPTS_DIR.glob("*.json")):
            if p.stem == "hub":
                continue  # skip self
            try:
                data = json.loads(p.read_text())
                scripts.append({
                    "name": p.stem,
                    "description": data.get("description", ""),
                    "steps": len(data.get("steps", [])),
                })
            except Exception:
                scripts.append({"name": p.stem, "description": "(parse error)", "steps": 0})
    return {"ok": True, "scripts": scripts}


def validate_script(params: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a script without executing it.

    Params:
        - script: Script name to validate
    """
    script_name = params.get("script", "")
    try:
        script = load_script(script_name)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}

    errors: List[str] = []
    for i, step in enumerate(script.get("steps", [])):
        if "controller" not in step:
            errors.append(f"Step {i}: missing 'controller'")
        if "action" not in step:
            errors.append(f"Step {i}: missing 'action'")

    return {
        "ok": len(errors) == 0,
        "script": script_name,
        "steps": len(script.get("steps", [])),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

ACTIONS = {
    "run_script": run_script,
    "list_scripts": list_scripts,
    "validate_script": validate_script,
}


def execute(action: str, params: Dict[str, Any]) -> Any:
    """Dispatch an action by name.

    Note: Hub uses action_only signature (no profile).
    """
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action '{action}'. Available: {list(ACTIONS.keys())}"}
    return ACTIONS[action](params)
