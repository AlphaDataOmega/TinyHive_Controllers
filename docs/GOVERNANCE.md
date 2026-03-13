# Controller Governance

Controllers operate under SPINE governance policies. This document defines approval requirements and hard constraints.

## Approval Categories

### Always Require SPINE Approval

These actions require explicit human approval via SPINE:

- Financial transactions of any kind
- Sending emails to external recipients
- Public social media posts
- SSH to remote (non-localhost) hosts
- Browser form submissions
- Outbound phone calls
- Resource creation in cloud platforms (GCP, AWS, etc.)
- Message deletion
- File deletion on remote systems

### Autonomous (Auto-Approved)

These actions can proceed without approval:

- Reading and organizing information
- Local file operations
- Drafting content (not sending)
- Research and analysis
- Screenshot capture
- Calendar reading
- Board/project reading
- Local command execution

### Hard Stops (Never Execute)

These actions are **permanently blocked**:

- Never share life-agent data (health, finances, mental health) externally
- Never delete files without explicit approval
- Never modify SSH keys or `authorized_keys`
- Never send messages impersonating the human without instruction
- Never commit code without review
- Never expose seed phrase or master key
- Never bypass authentication

## Lease System

Controllers request capabilities via the lease system:

```python
# Lease request
{
    "capability": "controller.ssh.exec",
    "scope": "ssh:production-server",
    "budget": 100,  # max operations
    "ttl": 3600,    # seconds
}
```

SPINE approves or denies lease requests based on:
1. Action category (see above)
2. Current context
3. Human availability
4. Risk assessment

## Controller-Specific Constraints

### SSH Controller
- 64KB output cap per command
- 30s default timeout
- Remote hosts require lease
- Never modify SSH keys

### Playwright Controller
- Mobile emulation only
- Screenshots deleted after processing
- Write actions require approval
- Read actions auto-approved
- Never store passwords in flows

### Hub Controller
- Scripts >10 steps require SPINE review
- Cannot bypass individual controller rate limits
- Must log all script executions

### Telegram Controller
- Only send to pre-authorized chat IDs
- Rate limit: 30 msgs/sec
- No message deletion without approval

### Google Controller
- Sending email requires approval
- External calendar invites require approval
- No Drive file deletion without approval

### GCP Controller
- Resource creation requires approval
- Cost alerts above $10/day
- No IAM changes without approval

## Implementing Governance

In your controller, check approval requirements:

```python
def action_that_needs_approval(profile: str, params: dict) -> dict:
    # This action requires a valid lease
    # The runtime verifies leases before dispatch

    # Your implementation
    return {"ok": True, "result": ...}
```

For auto-approved actions:

```python
def read_only_action(profile: str, params: dict) -> dict:
    # This action is auto-approved
    # No lease verification needed

    # Your implementation
    return {"ok": True, "result": ...}
```

## Notification Preferences

Configure how SPINE notifies humans:
- `notification_prefs`: Primary channel (telegram, email, etc.)
- `urgent_channels`: Channels for urgent approvals
- `digest_schedule`: When to send non-urgent summaries

## Best Practices

1. **Err on the side of caution** — when unsure, require approval
2. **Log all operations** — for audit trail
3. **Respect rate limits** — both system and external service limits
4. **Fail gracefully** — report errors, don't retry silently
5. **Document constraints** — in IDENTITY.md for each controller
