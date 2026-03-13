# TinyHive Controllers

Controllers are the execution layer that connects TinyHive agents to external systems. They translate agent requests into real-world actions — running commands, automating browsers, calling APIs, and orchestrating workflows.

## Architecture

```
SPINE (governance) → BODY (execution) → MIND (orchestration)
                        ↳ Controllers live here
```

Controllers are child agents of BODY. They receive work through the inbox system and execute actions on external platforms, devices, and tools.

## Quick Start

### 1. Choose a Controller Template

```bash
cp -r templates/controller_template controllers/controller_myservice
```

### 2. Define Your Controller

Edit `controllers/controller_myservice/IDENTITY.md`:
- Set the role and description
- Define capabilities
- Specify constraints

### 3. Implement Actions

Edit `controllers/controller_myservice/projects/myservice.py`:
```python
ACTIONS = {
    "action_name": action_function,
}

def execute(profile: str, action: str, params: dict) -> dict:
    """Dispatch entry point."""
    return ACTIONS[action](profile, params)
```

### 4. Register in Blueprint

Add to your hive's `config/controllers_blueprint.json`:
```json
{
  "agent_id": "controller_myservice",
  "name": "CONTROLLER-MYSERVICE",
  "role": "controller",
  "parent": "ado_live_body",
  "description": "...",
  "capabilities": [...],
  "constraints": [...]
}
```

## Method ID Format

All controller invocations use:
```
controller.{type}.{profile}.{action}
```

Examples:
- `controller.ssh.localhost.exec`
- `controller.playwright.twitter.run_flow`
- `controller.telegram.default.send_message`

## Pre-installed Controllers

| Controller | Type | Description |
|------------|------|-------------|
| **hub** | Orchestration | Multi-step workflow engine |
| **ssh** | System | Local/remote command execution |
| **playwright** | Browser | Mobile-emulated web automation |

## Available Templates

| Template | Use Case |
|----------|----------|
| `controller_template` | Basic controller scaffold |
| `controller_api_template` | REST API integration |
| `controller_oauth_template` | OAuth-authenticated services |
| `controller_device_template` | Device/hardware control |

## Runtime Features

The controller runtime provides:

- **Execution queue** — SQLite-backed job queue with priority ordering
- **Circuit breaker** — Prevents cascading failures (5 failures → open)
- **Rate limiting** — Token bucket per controller type
- **Idempotency cache** — Prevents duplicate executions (1-hour TTL)
- **Lease verification** — SPINE-issued capability permissions

## Documentation

- [Controller Development Guide](docs/DEVELOPMENT.md)
- [Workspace Standard](docs/WORKSPACE_STANDARD.md)
- [Runtime Model](docs/RUNTIME_MODEL.md)
- [Governance & Constraints](docs/GOVERNANCE.md)

## Contributing

1. Fork this repository
2. Create your controller in `controllers/`
3. Add tests in `tests/`
4. Submit a pull request

## License

MIT
