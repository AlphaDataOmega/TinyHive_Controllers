# Controller Workspace Standard v0

This standard defines the workspace layout for all `controller-*` children under BODY.

## Controller Classification

Controllers follow Type-S / Type-E classification:

- **Type-S controllers** (majority): Direct execution only. No sub-agent spawning.
- **Type-E controllers** (hub, device controllers): May spawn sub-agents for delegated operations.

## Workspace Layout

```
controller-*/
  IDENTITY.md       # Required — agent identity, role, hard constraints
  memory/           # Required — persistent knowledge
  docs/             # Required — API docs, protocol references
  output/           # Required — operation artifacts (gitignored)
  tools/            # Required — tool definitions, helper scripts
  profiles/         # Recommended — profile-scoped configurations
  config/           # Optional — MCP server config
  HEARTBEAT.md      # Recommended — health check documentation
```

### Type-E Controllers Add

```
  subagents/        # Required — spawned worker sessions
```

## Directory Purposes

### `memory/`

Persistent knowledge that survives across sessions:
- Site-specific knowledge (selectors, auth flows, quirks)
- Workflow templates
- Operational history or indexes

### `docs/`

Reference documentation:
- API documentation
- Protocol references
- Runtime model docs
- Sub-agent patterns

### `output/`

Artifacts produced by operations:
- Timestamped results under `output/controllers/`
- Operation logs, screenshots, generated files
- **Ephemeral** — should be gitignored

### `tools/`

Tool definitions and helper scripts:
- Custom scripts (OAuth helpers, API wrappers)
- Tool registration files

### `profiles/`

Profile-scoped configurations:
- Named subdirectories or JSON files
- Each profile scopes the controller to a specific account/workspace
- Method ID format: `controller.{type}.{profile}.{action}`

### `config/`

Optional MCP server configuration:
- `mcporter.json` — MCP server definition
- Canonical location (not workspace root)

## Required Files

| File | Status | Purpose |
|------|--------|---------|
| IDENTITY.md | Required | Agent identity, role, type, constraints |
| HEARTBEAT.md | Recommended | Health check documentation |

## Routing

Controllers receive work through BODY's controller-hub via the inbox system:
- Messages flow through inbox.db queues
- Priority ordering and receipt contracts
- Method ID format: `controller.{type}.{profile}.{action}`

Controllers do NOT receive direct requests from non-BODY agents. All routing goes through controller-hub.

## Universal Constraints

1. Never execute destructive operations without explicit approval
2. Always use the correct profile for the target context
3. Never store credentials in workspace files — use env vars or SecretsStore
4. When unsure about an operation, escalate to BODY
5. When a service is unreachable, report failure clearly — do not retry silently
