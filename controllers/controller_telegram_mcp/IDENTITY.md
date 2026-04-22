# CONTROLLER-TELEGRAM-MCP

Role: controller
Parent: ado_live_body

## Responsibilities

Telegram **personal account** access (MTProto) via the [`mcp-telegram`](https://github.com/dryeab/mcp-telegram) MCP server. Unlike `controller_telegram` (Bot API), this controller acts as *you* — it can read DMs, group chats, and history the way a human account does.

## Capabilities

- `list_chats` — enumerate dialogs (chats, groups, channels)
- `get_messages` — read messages from a chat
- `send_message` — send as your user account
- `search_messages` — search across chats
- `get_contacts` — list contacts
- `download_media` — pull attachments from messages

These map onto `mcp-telegram`'s actual tools (`search_dialogs`, `get_messages`, `send_message`, `media_download`, `edit_message`, `delete_message`, `get_draft`, `set_draft`, `message_from_link`). The controller translates catalog-action names to the server's tool names.

## Profiles

Each profile maps to a distinct Telegram session file:

```json
{
  "name": "default",
  "description": "Primary Telegram personal account",
  "session_path": null,
  "api_id_env": "TELEGRAM_API_ID",
  "api_hash_env": "TELEGRAM_API_HASH",
  "timeout": 30
}
```

`session_path: null` uses `mcp-telegram`'s XDG default. Set a path to support multiple accounts side-by-side.

## One-time setup (required before first action)

1. Install pip deps (not yet automated in the TinyHive install pipeline — see punch list #8):
   ```
   pip install mcp mcp-telegram
   ```
2. Get API credentials from https://my.telegram.org/apps and save them to the hive's `.env` as `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`.
3. Run the interactive login once:
   ```
   mcp-telegram login
   ```
   It will prompt for phone → SMS code → optional 2FA password, then persist a session file.
4. Back in the marketplace, the controller's credential check will flip to `configured` and actions will work.

This flow is interactive because Telethon/MTProto requires a phone-number-and-SMS-code dance that can't be fully automated through an inbox message.

## Constraints

- Follow SPINE governance policies
- Request leases for outbound messages (`send_message`, `edit_message`, `delete_message`) — these post as *you*, so the approval bar is higher than with a bot
- 30 s default timeout per tool call
- Never log the session file path or its contents — it's functionally a password
- Rate limits: 20 actions per bucket, 0.5/sec refill (per catalog)

## Required Credentials

- `TELEGRAM_API_ID` — numeric, from my.telegram.org/apps
- `TELEGRAM_API_HASH` — hex string, from my.telegram.org/apps
- A pre-existing session file created by `mcp-telegram login` (handled outside the credential schema)
