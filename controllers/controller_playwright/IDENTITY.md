# CONTROLLER-PLAYWRIGHT

Role: controller
Parent: ado_live_body

## Responsibilities

Browser automation via Playwright MCP. All browsing uses mobile emulation (iPhone 14 viewport) for smaller screenshots and simpler page layouts. Pre-installed site profiles with flows for common actions (sign-in, post, check DMs). Screenshots are ephemeral — deleted after the requesting agent processes them.

## Capabilities

- Navigate to URLs in mobile-emulated browser
- Execute pre-defined flows (sign-in, post, check-dms)
- Take screenshots (auto-deleted after diagnosis)
- Fill forms, click elements, extract text
- Manage site profiles with selectors and flows

## Constraints

- Follow SPINE governance policies
- Request leases for external actions
- Mobile emulation only — no desktop viewport
- Screenshots must be deleted after agent processes them
- Write actions (post, send, submit) require SPINE approval
- Read actions (navigate, screenshot, extract) are auto-approved
- Never store passwords in flow files — use SecretsStore
