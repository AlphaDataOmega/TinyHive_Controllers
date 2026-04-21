<p align="center">
  <img src="https://alphadataomega.com/tinyhive-logo.png" alt="TinyHive" width="80" />
</p>

<h1 align="center">TinyHive Controllers</h1>

<p align="center">
  <strong>Execution Layer for TinyHive Agents</strong><br>
  Modular integrations that connect your AI to the real world.
</p>

---

## What Are Controllers?

Controllers are the **hands** of TinyHive — they translate agent decisions into real-world actions. Each controller:

- **Executes specific actions** (SSH commands, browser automation, API calls)
- **Defines required credentials** in `keys.json`
- **Operates under governance** from SPINE
- **Lives under BODY** as child agents

```
MIND (orchestration)
    ↓ requests action
SPINE (governance) ──→ validates lease/permissions
    ↓ approved
BODY (execution)
    ↓ dispatches to
CONTROLLER ──→ executes action ──→ external system
```

## Available Controllers

| Controller | Purpose | Keys Required |
|------------|---------|---------------|
| `controller_hub` | Multi-controller orchestration | None |
| `controller_ssh` | Local/remote command execution | Optional SSH config |
| `controller_playwright` | Browser automation | None |
| `controller_google` | Gmail, Calendar, Drive (skeleton, OAuth) | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` |

### Coming Soon

| Controller | Purpose |
|------------|---------|
| `controller_telegram` | Telegram bot notifications |
| `controller_gcp` | Google Cloud Platform |
| `controller_fal` | Fal.ai image/video generation |
| `controller_vapi` | Voice AI assistants |
| `controller_monday` | Monday.com project management |

## Installation

### Via TinyHive CLI

```bash
# List available controllers
python3 -m setup.registry_sync list controllers

# Fetch a specific controller
python3 -m setup.registry_sync fetch controller controller_ssh

# Sync all controllers from your controllers.json
python3 -m setup.registry_sync sync controllers
```

### Manual

```bash
# Clone the repo
git clone https://github.com/AlphaDataOmega/TinyHive-Controllers.git

# Copy a controller to your TinyHive
cp -r TinyHive-Controllers/controllers/controller_ssh \
      ~/.tinyhive/agents/ado_live_body/children/
```

## Controller Structure

```
controller_name/
├── IDENTITY.md      # Role, capabilities, constraints
├── keys.json        # Required credentials definition
├── projects/
│   └── name.py      # Action implementations
├── profiles/        # Service-specific configs
├── tools/           # Helper utilities
├── memory/          # Persistent state
├── output/          # Execution outputs
└── docs/            # Documentation
```

## keys.json Schema

Each controller defines its required credentials:

```json
{
  "controller_id": "controller_telegram",
  "name": "Controller Telegram",
  "description": "Telegram bot integration",
  "version": "1.0",
  "keys": [
    {
      "key": "TELEGRAM_BOT_TOKEN",
      "label": "Telegram Bot Token",
      "category": "Telegram",
      "required": true,
      "sensitive": true,
      "hint": "123456:ABC-DEF...",
      "description": "Bot token from @BotFather"
    },
    {
      "key": "TELEGRAM_CHAT_ID",
      "label": "Telegram Chat ID",
      "category": "Telegram",
      "required": true,
      "sensitive": false,
      "hint": "-1001234567890"
    }
  ]
}
```

The TinyHive UI reads `keys.json` to display credential forms during setup.

## Method ID Format

All controller invocations use:

```
controller.{type}.{profile}.{action}
```

Examples:
- `controller.ssh.localhost.exec`
- `controller.playwright.twitter.run_flow`
- `controller.telegram.default.send_message`

## Creating a Controller

### 1. Copy the template

```bash
cp -r templates/controller_template controllers/controller_myservice
```

### 2. Define IDENTITY.md

```markdown
# CONTROLLER-MYSERVICE

Agent ID: `controllers/controller_myservice`

## Role
What this controller does.

## Capabilities
- Action 1
- Action 2

## Constraints
- What requires approval
- Rate limits
- Forbidden actions
```

### 3. Define keys.json

```json
{
  "controller_id": "controller_myservice",
  "name": "Controller MyService",
  "description": "Integration with MyService",
  "version": "1.0",
  "keys": [
    {
      "key": "MYSERVICE_API_KEY",
      "label": "MyService API Key",
      "category": "MyService",
      "required": true,
      "sensitive": true,
      "hint": "ms_..."
    }
  ]
}
```

### 4. Implement actions

```python
# projects/myservice.py

ACTIONS = {
    "send": send_action,
    "fetch": fetch_action,
}

def send_action(profile: str, params: dict) -> dict:
    """Send something to MyService."""
    api_key = get_secret("MYSERVICE_API_KEY")
    # ... implementation
    return {"status": "ok", "result": ...}

def execute(profile: str, action: str, params: dict) -> dict:
    """Dispatch entry point."""
    if action not in ACTIONS:
        raise ValueError(f"Unknown action: {action}")
    return ACTIONS[action](profile, params)
```

## Templates

| Template | Use Case |
|----------|----------|
| `controller_template` | Basic scaffold |
| `controller_api_template` | REST API integration |

## Runtime Features

The controller runtime provides:

- **Execution queue** — SQLite-backed job queue with priority
- **Circuit breaker** — Prevents cascading failures (5 failures → open)
- **Rate limiting** — Token bucket per controller type
- **Idempotency cache** — Prevents duplicates (1-hour TTL)
- **Lease verification** — SPINE-issued capability permissions

## Documentation

- [Controller Development Guide](docs/controllers/DEVELOPMENT.md)
- [Workspace Standard](docs/controllers/WORKSPACE_STANDARD.md)

## Related Repositories

| Repo | Description |
|------|-------------|
| [tinyhive_v0-EX](https://github.com/AlphaDataOmega/tinyhive_v0-EX) | Standalone Linux edition |
| [TinyHive_Consultant-Children](https://github.com/AlphaDataOmega/TinyHive_Consultant-Children) | Consultant agents |

## Contributing

1. Fork this repository
2. Create your controller in `controllers/`
3. Include `IDENTITY.md` and `keys.json`
4. Add tests in `tests/`
5. Submit a pull request

## License

MIT

---

<p align="center">
  Part of the <a href="https://github.com/AlphaDataOmega">TinyHive</a> ecosystem
</p>
