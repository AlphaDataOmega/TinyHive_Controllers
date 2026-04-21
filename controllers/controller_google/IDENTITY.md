# CONTROLLER-GOOGLE

Role: controller
Parent: ado_live_body

## Responsibilities

Google Workspace integration for TinyHive agents. Executes Gmail, Calendar, Drive, and Sheets actions on behalf of the hive through OAuth-scoped profiles. Each profile maps to a Google account/workspace and carries its own token envelope.

## Capabilities

- List and search Gmail messages
- Send email on the user's behalf
- List and create Google Calendar events
- (Extendable) Drive file listing, Sheets read/write, Analytics, AdSense

## Profiles

A profile is a JSON file under `profiles/` that names the environment variable holding the current OAuth access token, e.g.:

```json
{
  "name": "default",
  "description": "Primary Google workspace account",
  "token_env": "GOOGLE_ACCESS_TOKEN"
}
```

Populate `GOOGLE_ACCESS_TOKEN` at runtime. Two common patterns:

1. Marketplace OAuth: the TinyHive generic OAuth callback (`/api/controllers/oauth/callback/google`) exchanges the auth code for refresh + access tokens and persists them to `.env`.
2. Cron refresh: a scheduled job uses `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN` to mint a fresh access token before expiry.

## Constraints

- Follow SPINE governance policies
- Request leases for external actions
- 30s default timeout per API call
- Never send email without explicit user approval on a per-send basis
- Refresh-token material is sensitive — never log, echo, or forward to other agents
- OAuth scopes are granted per-account; controller actions must fail closed if a required scope is missing

## Required Credentials

Defined in `keys.json`:
- `GOOGLE_CLIENT_ID` — OAuth 2.0 Client ID (Google Cloud Console)
- `GOOGLE_CLIENT_SECRET` — OAuth 2.0 Client Secret
- `GOOGLE_REFRESH_TOKEN` — Long-lived token obtained after first consent
