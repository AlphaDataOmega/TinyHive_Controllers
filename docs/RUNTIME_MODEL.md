# Controller Runtime Model

The controller runtime manages execution of controller actions with safety mechanisms.

## Execution Flow

```
Agent Message → Inbox Queue
       ↓
ControllerRuntime.submit()
  ├─ Check idempotency cache
  ├─ Verify lease (permissions)
  ├─ Check circuit breaker
  ├─ Check rate limiter
  └─ Enqueue to execution_queue

ControllerDispatch service (polling)
  ├─ Pull queued items
  ├─ Load controller module
  ├─ Dispatch to controller.execute()
  ├─ Record result/failure
  └─ Update circuit breaker
```

## Method ID Format

All controllers use:
```
controller.{type}.{profile}.{action}
```

**Parsing example:**
- Input: `controller.telegram.default.send_message`
- Type: `telegram`
- Profile: `default`
- Action: `send_message`

## Runtime Features

### Execution Queue

SQLite-backed job queue:

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| method_id | TEXT | Full method identifier |
| params | TEXT | JSON-encoded parameters |
| status | TEXT | queued → executing → completed/failed |
| created_at | TEXT | Timestamp |
| completed_at | TEXT | Completion timestamp |

**Backpressure:** Rejects submissions if queue exceeds `max_queue_depth` (default: 200).

### Idempotency Cache

Prevents duplicate executions:
- Auto-generates key: `controller.{type}.{profile}.{action}.{sha256(params)[:12]}`
- Caches results with 1-hour TTL
- Returns cached result for duplicate requests

### Circuit Breaker

Per-controller failure protection:

| State | Behavior |
|-------|----------|
| `closed` | Normal operation |
| `open` | All requests rejected |
| `half_open` | Single test request allowed |

- Opens after 5 consecutive failures (configurable)
- 60-second cooldown before half-open
- One success in half-open → closed

### Rate Limiting

Token bucket algorithm per controller:
- Default: 10 tokens, 1 token/second refill
- Prevents overwhelming external services
- Lazily refills on each access

### Lease Verification

Capability-based permissions:
- Derives capability from method_id: `controller.{type}.{action}`
- Derives scope: `{type}:{profile}`
- Blocks if lease is invalid, expired, or insufficient budget

## ControllerRuntime API

```python
class ControllerRuntime:
    def submit(method_id, params, lease_id, requested_by) -> execution_id
    def execute(execution_id) -> None  # Mark as executing
    def complete(execution_id, result) -> None  # Mark complete, cache
    def fail(execution_id, error) -> None  # Mark failed, circuit breaker
    def get_status(execution_id) -> Dict  # Poll status
    def list_queue(controller_type=None, status=None) -> List[Dict]
```

## Dispatch Registry

Controllers register with a signature type:

```python
CONTROLLER_REGISTRY = {
    "ssh": (_get_ssh_controller, "profile_action"),
    "hub": (_get_hub_controller, "action_only"),
    "playwright": (_get_playwright_controller, "profile_action"),
}
```

**Signature types:**
- `"profile_action"`: `execute(profile, action, params)`
- `"action_only"`: `execute(action, params)`

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTROLLER_QUEUE_DEPTH` | 200 | Max queue size |
| `CONTROLLER_CIRCUIT_THRESHOLD` | 5 | Failures before open |
| `CONTROLLER_CIRCUIT_COOLDOWN` | 60 | Seconds in open state |
| `CONTROLLER_RATE_TOKENS` | 10 | Token bucket size |
| `CONTROLLER_RATE_REFILL` | 1.0 | Tokens per second |
| `CONTROLLER_IDEMPOTENCY_TTL` | 3600 | Cache TTL in seconds |

## Error Handling

Controllers should return structured errors:

```python
# Success
{"ok": True, "result": {...}}

# Failure (doesn't trigger circuit breaker)
{"ok": False, "error": "Human-readable message"}

# Raising exceptions DOES trigger circuit breaker
raise ConnectionError("Service unreachable")
```

## Best Practices

1. **Return `ok: False` for expected failures** (invalid input, not found)
2. **Raise exceptions for infrastructure failures** (network, auth)
3. **Set appropriate timeouts** per action
4. **Log at INFO level** for operations, DEBUG for details
5. **Use idempotency keys** for non-idempotent operations
