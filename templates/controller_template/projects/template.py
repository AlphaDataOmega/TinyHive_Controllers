"""Template controller — [brief description].

Method IDs:
  controller.template.{profile}.action_one
  controller.template.{profile}.action_two
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

log = logging.getLogger("tinyhive.controller.template")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Available: {list_profiles()}")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def action_one(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Describe what action_one does.

    Args:
        profile_name: The profile to use
        params: Action parameters
            - param1: Description
            - param2: Description

    Returns:
        {"ok": True/False, "result": ..., "error": ...}
    """
    profile = load_profile(profile_name)

    # Your implementation here
    param1 = params.get("param1", "")

    if not param1:
        return {"ok": False, "error": "param1 is required"}

    # Do something with the profile and params
    result = f"Executed action_one with {param1}"

    return {"ok": True, "result": result}


def action_two(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Describe what action_two does."""
    profile = load_profile(profile_name)

    # Your implementation here

    return {"ok": True, "result": "action_two completed"}


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

ACTIONS = {
    "action_one": action_one,
    "action_two": action_two,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """Dispatch an action by name with a profile.

    This is the entry point called by the controller runtime.
    """
    if action not in ACTIONS:
        return {
            "ok": False,
            "error": f"Unknown action '{action}'. Available: {list(ACTIONS.keys())}"
        }
    return ACTIONS[action](profile, params)
