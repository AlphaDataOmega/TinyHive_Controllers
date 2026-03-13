# Controller Development Guide

This guide walks you through creating a new TinyHive controller from scratch.

## Overview

Controllers are specialized agents that bridge TinyHive to external systems. Each controller:

1. Lives under `ado_live_body/children/`
2. Follows a standard workspace layout
3. Implements an `execute()` entry point
4. Registers actions in an `ACTIONS` dictionary

## Step 1: Create the Workspace

Copy a template to get started:

```bash
cp -r templates/controller_template controllers/controller_myservice
cd controllers/controller_myservice
```

Your workspace structure:

```
controller_myservice/
  IDENTITY.md           # Required: agent identity and constraints
  memory/               # Persistent knowledge
  docs/                 # API references, protocols
  output/               # Operation artifacts (gitignored)
  tools/                # Helper scripts
  profiles/             # Profile configurations
  projects/
    myservice.py        # Main implementation
```

## Step 2: Define Identity

Edit `IDENTITY.md`:

```markdown
# CONTROLLER-MYSERVICE

Role: controller
Parent: ado_live_body

## Responsibilities

Brief description of what this controller does.

## Capabilities

- What actions it can perform
- What systems it integrates with

## Constraints

- Follow SPINE governance policies
- Request leases for external actions
- Rate limits and timeouts
- Security restrictions
```

## Step 3: Implement Actions

Edit `projects/myservice.py`:

```python
"""MyService controller — brief description.

Method IDs:
  controller.myservice.{profile}.action_one
  controller.myservice.{profile}.action_two
"""

import logging
from pathlib import Path
from typing import Any, Dict

log = logging.getLogger("tinyhive.controller.myservice")

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
# Actions
# ---------------------------------------------------------------------------

def action_one(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Describe what this action does."""
    # Your implementation here
    return {"ok": True, "result": "..."}


def action_two(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Describe what this action does."""
    # Your implementation here
    return {"ok": True, "result": "..."}


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

ACTIONS = {
    "action_one": action_one,
    "action_two": action_two,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """Dispatch an action by name with a profile."""
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action '{action}'"}
    return ACTIONS[action](profile, params)
```

## Step 4: Create Profiles

Profiles scope controller behavior to specific accounts/contexts.

Create `profiles/default.json`:

```json
{
  "name": "default",
  "description": "Default profile",
  "api_key_env": "MYSERVICE_API_KEY",
  "base_url": "https://api.myservice.com",
  "timeout": 30
}
```

Reference env vars for secrets — never hardcode credentials!

## Step 5: Register in Blueprint

Add your controller to `config/controllers_blueprint.json`:

```json
{
  "agent_id": "controller_myservice",
  "name": "CONTROLLER-MYSERVICE",
  "role": "controller",
  "parent": "ado_live_body",
  "description": "Integration with MyService API",
  "capabilities": [
    "Perform action one",
    "Perform action two"
  ],
  "constraints": [
    "Rate limit: 100 requests/minute",
    "Action two requires SPINE approval"
  ]
}
```

## Step 6: Write Tests

Create `tests/test_controller_myservice.py`:

```python
import pytest
from controllers.controller_myservice.projects.myservice import execute

def test_action_one_success():
    result = execute("default", "action_one", {"param": "value"})
    assert result["ok"] is True

def test_unknown_action():
    result = execute("default", "unknown", {})
    assert result["ok"] is False
    assert "Unknown action" in result["error"]
```

## Return Value Convention

All actions should return a dictionary:

```python
# Success
{"ok": True, "result": ..., "metadata": ...}

# Failure
{"ok": False, "error": "Human-readable error message"}
```

## Dispatch Signatures

Controllers use one of two signatures:

**Profile + Action** (most controllers):
```python
def execute(profile: str, action: str, params: dict) -> dict
```

**Action Only** (hub, orchestration):
```python
def execute(action: str, params: dict) -> dict
```

The controller runtime determines which to use based on the registry.

## Best Practices

1. **Idempotency** — Actions should be safe to retry
2. **Timeouts** — Always set reasonable timeouts
3. **Error handling** — Return structured errors, don't raise
4. **Logging** — Use the controller's logger for debugging
5. **Secrets** — Reference env vars, never hardcode
6. **Output limits** — Cap output size (e.g., 64KB for SSH)

## Next Steps

- Read [Workspace Standard](WORKSPACE_STANDARD.md) for layout details
- Read [Runtime Model](RUNTIME_MODEL.md) for execution details
- Read [Governance](GOVERNANCE.md) for approval requirements
