# TinyHive Controllers - Batch 8

Documentation for Storage, Stripe, Supabase, Teams, Telegram, Terraform, TikTok, Trello, Twilio, and Twitch controllers.

---

## Table of Contents

1. [Storage Controller](#storage-controller)
2. [Stripe Controller](#stripe-controller)
3. [Supabase Controller](#supabase-controller)
4. [Teams Controller](#teams-controller)
5. [Telegram Controller](#telegram-controller)
6. [Terraform Controller](#terraform-controller)
7. [TikTok Controller](#tiktok-controller)
8. [Trello Controller](#trello-controller)
9. [Twilio Controller](#twilio-controller)
10. [Twitch Controller](#twitch-controller)

---

## Storage Controller

### Overview

A unified storage controller supporting multiple backends for file operations. Supports local filesystem, S3-compatible storage (AWS S3, MinIO, Cloudflare R2, DigitalOcean Spaces), and SFTP.

**Use Cases:**
- Upload and download files across multiple storage providers
- Generate presigned URLs for temporary file access
- Manage files on remote servers via SFTP
- Unified file operations for multi-cloud environments

### Authentication

**Local Filesystem:**
- No environment variables required
- Read/write access to `base_path`

**S3-Compatible:**
| Environment Variable | Description |
|---------------------|-------------|
| `AWS_ACCESS_KEY_ID` | AWS/S3 access key (or custom via `access_key_env`) |
| `AWS_SECRET_ACCESS_KEY` | AWS/S3 secret key (or custom via `secret_key_env`) |

**SFTP:**
| Environment Variable | Description |
|---------------------|-------------|
| `SFTP_PASSWORD` | SFTP password (or custom via `password_env`) |

**How to get credentials:**
- **AWS S3:** Create IAM user with S3 permissions in AWS Console
- **MinIO:** Generate access keys from MinIO Console
- **SFTP:** Use server credentials or SSH key file

### Profile Configuration

**Local Filesystem:**
```json
{
    "backend": "local",
    "base_path": "/data/storage",
    "create_dirs": true
}
```

**S3-Compatible:**
```json
{
    "backend": "s3",
    "bucket": "my-bucket",
    "region": "us-east-1",
    "endpoint_url": null,
    "access_key_env": "AWS_ACCESS_KEY_ID",
    "secret_key_env": "AWS_SECRET_ACCESS_KEY",
    "presigned_expiry": 3600
}
```

**SFTP:**
```json
{
    "backend": "sftp",
    "host": "sftp.example.com",
    "port": 22,
    "username": "user",
    "password_env": "SFTP_PASSWORD",
    "key_path": null,
    "base_path": "/upload"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_files` | List files at a path | - | `path`, `recursive` |
| `upload_file` | Upload a file | `remote_path` | `local_path`, `content`, `content_encoding` |
| `download_file` | Download a file | `remote_path` | `local_path` |
| `delete_file` | Delete a file | `path` | - |
| `get_file_info` | Get file metadata | `path` | - |
| `copy_file` | Copy a file | `src`, `dst` | - |
| `move_file` | Move a file | `src`, `dst` | - |
| `get_presigned_url` | Get presigned URL (S3 only) | `path` | `expiry` |

### Usage Example

```python
from tinyhive.controllers import storage_controller

# List files in a directory
result = storage_controller.execute("my_s3", "list_files", {
    "path": "documents/",
    "recursive": True
})

# Upload content directly
result = storage_controller.execute("my_s3", "upload_file", {
    "remote_path": "reports/monthly.pdf",
    "content": base64_content,
    "content_encoding": "base64"
})

# Generate presigned URL for download
result = storage_controller.execute("my_s3", "get_presigned_url", {
    "path": "reports/monthly.pdf",
    "expiry": 7200  # 2 hours
})
print(f"Download URL: {result['url']}")
```

---

## Stripe Controller

### Overview

Stripe payment processing controller for managing customers, payments, subscriptions, and invoices. Integrates with the Stripe REST API for comprehensive payment operations.

**Use Cases:**
- Create and manage customers
- Process payment intents
- List and manage subscriptions
- Generate invoices
- Check account balance

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `STRIPE_SECRET_KEY` | Stripe secret API key (or custom via `api_key_env`) |

**How to get credentials:**
1. Log into [Stripe Dashboard](https://dashboard.stripe.com)
2. Navigate to Developers > API Keys
3. Copy your Secret key (use test key for development)

### Profile Configuration

```json
{
    "api_key_env": "STRIPE_SECRET_KEY"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_customers` | List customers with pagination | - | `limit`, `starting_after`, `email` |
| `create_customer` | Create a new customer | - | `email`, `name`, `description`, `phone`, `metadata` |
| `list_payments` | List payment intents | - | `limit`, `starting_after`, `customer`, `created_gte`, `created_lte` |
| `create_payment_intent` | Create a payment intent | `amount`, `currency` | `customer`, `description`, `metadata`, `automatic_payment_methods` |
| `list_subscriptions` | List subscriptions | - | `limit`, `starting_after`, `customer`, `status`, `price` |
| `create_invoice` | Create a draft invoice | `customer` | `description`, `metadata`, `auto_advance`, `collection_method`, `days_until_due` |
| `get_balance` | Get account balance | - | - |

### Usage Example

```python
from tinyhive.controllers import stripe_controller

# Create a customer
result = stripe_controller.execute("production", "create_customer", {
    "email": "customer@example.com",
    "name": "John Doe",
    "metadata": {"plan": "enterprise"}
})
customer_id = result["data"]["id"]

# Create a payment intent
result = stripe_controller.execute("production", "create_payment_intent", {
    "amount": 2000,  # $20.00 in cents
    "currency": "usd",
    "customer": customer_id,
    "description": "Monthly subscription"
})

# Check account balance
result = stripe_controller.execute("production", "get_balance", {})
print(f"Available: {result['data']['available']}")
```

---

## Supabase Controller

### Overview

Controller for interacting with Supabase REST API and Storage. Provides PostgREST-compatible database operations and file storage management.

**Use Cases:**
- Query and modify database tables via REST
- Perform upserts with conflict resolution
- Call stored procedures (RPC functions)
- Upload files to Supabase Storage
- Manage storage buckets

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `SUPABASE_API_KEY` | Supabase anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key for admin operations |

**How to get credentials:**
1. Go to your Supabase project dashboard
2. Navigate to Settings > API
3. Copy the `anon` public key and `service_role` key

### Profile Configuration

```json
{
    "project_ref": "your-project-ref",
    "api_key_env": "SUPABASE_API_KEY",
    "service_role_key_env": "SUPABASE_SERVICE_ROLE_KEY"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `select` | Query rows from a table | `table` | `select`, `where`, `order`, `limit`, `offset` |
| `insert` | Insert rows into a table | `table`, `data` | `return_data`, `on_conflict` |
| `update` | Update rows in a table | `table`, `data`, `where` | `return_data` |
| `delete` | Delete rows from a table | `table`, `where` | `return_data` |
| `upsert` | Insert or update rows | `table`, `data` | `on_conflict`, `return_data`, `ignore_duplicates` |
| `rpc` | Call a stored procedure | `function_name` | `params`, `method` |
| `upload_file` | Upload file to storage | `bucket`, `path`, `file_content` | `content_type`, `encoding`, `upsert` |
| `list_buckets` | List storage buckets | - | - |

### Usage Example

```python
from tinyhive.controllers import supabase_controller

# Query users with filters
result = supabase_controller.execute("production", "select", {
    "table": "users",
    "select": "id,name,email,created_at",
    "where": {"status": "active", "role": {"in": ["admin", "moderator"]}},
    "order": "created_at.desc",
    "limit": 50
})

# Upsert a record
result = supabase_controller.execute("production", "upsert", {
    "table": "profiles",
    "data": {"user_id": "123", "bio": "Hello world", "updated_at": "2024-01-15"},
    "on_conflict": "user_id"
})

# Call an RPC function
result = supabase_controller.execute("production", "rpc", {
    "function_name": "get_user_stats",
    "params": {"user_id": "123"}
})

# Upload a file
result = supabase_controller.execute("production", "upload_file", {
    "bucket": "avatars",
    "path": "user-123/profile.png",
    "file_content": base64_image,
    "encoding": "base64",
    "content_type": "image/png"
})
```

---

## Teams Controller

### Overview

Microsoft Teams integration via Microsoft Graph API. Send messages to channels and chats, manage teams and channels, and create online meetings.

**Use Cases:**
- Send notifications to Teams channels
- Create and manage channels
- Schedule online meetings
- List team members
- Automate team communications

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `TEAMS_ACCESS_TOKEN` | Microsoft Graph access token (or custom via `token_env`) |

**How to get credentials:**
1. Register an app in [Azure Portal](https://portal.azure.com) > App registrations
2. Configure API permissions (see Required Permissions below)
3. Obtain OAuth 2.0 access token via auth flow

**Required Microsoft Graph API Permissions:**
- `ChannelMessage.Send` - send channel messages
- `Chat.ReadWrite`, `ChatMessage.Send` - send chat messages
- `Team.ReadBasic.All`, `TeamMember.Read.All` - list teams and members
- `Channel.ReadBasic.All`, `Channel.Create` - list/create channels
- `OnlineMeetings.ReadWrite` - create meetings

### Profile Configuration

```json
{
    "token_env": "TEAMS_ACCESS_TOKEN",
    "default_team_id": "team-guid-here",
    "timezone": "UTC"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `send_message` | Send message to channel | `team_id`, `channel_id`, `content` | `content_type` |
| `send_chat` | Send message to chat | `chat_id`, `content` | `content_type` |
| `list_teams` | List joined teams | - | `filter`, `top` |
| `list_channels` | List channels in a team | `team_id` | `filter` |
| `create_channel` | Create a new channel | `team_id`, `display_name` | `description`, `membership_type` |
| `list_chats` | List user's chats | - | `top`, `filter`, `expand` |
| `create_meeting` | Create online meeting | `subject`, `start_time`, `end_time` | `attendees`, `lobby_bypass`, `auto_admit` |
| `list_members` | List team members | `team_id` | `filter`, `top` |

### Usage Example

```python
from tinyhive.controllers import teams_controller

# List teams
result = teams_controller.execute("work", "list_teams", {})
teams = result["data"]["teams"]

# Send a channel message
result = teams_controller.execute("work", "send_message", {
    "team_id": "team-guid",
    "channel_id": "channel-guid",
    "content": "<p>Build completed successfully!</p>",
    "content_type": "html"
})

# Create an online meeting
result = teams_controller.execute("work", "create_meeting", {
    "subject": "Sprint Review",
    "start_time": "2024-01-20T14:00:00Z",
    "end_time": "2024-01-20T15:00:00Z",
    "attendees": ["alice@company.com", "bob@company.com"]
})
print(f"Join URL: {result['data']['join_url']}")
```

---

## Telegram Controller

### Overview

Telegram Bot API controller for sending messages and media, and retrieving updates. Simple integration for bot-based notifications and interactions.

**Use Cases:**
- Send text messages and photos via bot
- Retrieve incoming messages and updates
- Build notification systems
- Create interactive bots

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot token (or custom via `token_env`) |

**How to get credentials:**
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the bot token provided

### Profile Configuration

```json
{
    "token_env": "TELEGRAM_BOT_TOKEN",
    "default_chat_id": "123456789"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `send_message` | Send a text message | `chat_id`, `text` | `parse_mode` |
| `send_photo` | Send a photo | `chat_id`, `photo` | `caption` |
| `get_updates` | Get recent messages | - | `offset`, `limit` |

### Usage Example

```python
from tinyhive.controllers import telegram_controller

# Send a message
result = telegram_controller.execute("notifications", "send_message", {
    "chat_id": "123456789",
    "text": "*Alert:* Server CPU usage above 90%",
    "parse_mode": "Markdown"
})

# Send a photo
result = telegram_controller.execute("notifications", "send_photo", {
    "chat_id": "123456789",
    "photo": "https://example.com/chart.png",
    "caption": "Daily metrics report"
})

# Get recent updates
result = telegram_controller.execute("notifications", "get_updates", {
    "limit": 10
})
for update in result.get("result", []):
    print(update["message"]["text"])
```

---

## Terraform Controller

### Overview

Terraform Cloud/Enterprise API controller for managing infrastructure as code. Control workspaces, trigger runs, and manage state.

**Use Cases:**
- List and manage workspaces
- Trigger infrastructure runs
- Apply or cancel pending runs
- View state versions and outputs
- Automate infrastructure deployments

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `TFC_TOKEN` | Terraform Cloud API token (or custom via `token_env`) |

**How to get credentials:**
1. Log into [Terraform Cloud](https://app.terraform.io)
2. Go to User Settings > Tokens
3. Create an API token with appropriate permissions

### Profile Configuration

```json
{
    "organization": "my-terraform-org",
    "token_env": "TFC_TOKEN",
    "base_url": "https://app.terraform.io/api/v2",
    "timeout": 60
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_workspaces` | List workspaces in org | - | `organization`, `page_number`, `page_size`, `search_name` |
| `get_workspace` | Get workspace details | `workspace_name` | `organization` |
| `create_run` | Create a new run | `workspace_id` | `message`, `auto_apply`, `is_destroy`, `target_addrs`, `replace_addrs`, `refresh`, `refresh_only` |
| `get_run` | Get run details | `run_id` | - |
| `apply_run` | Apply a pending run | `run_id` | `comment` |
| `cancel_run` | Cancel a run | `run_id` | `comment`, `force` |
| `list_runs` | List runs for workspace | `workspace_id` | `page_number`, `page_size`, `status` |
| `get_state_version` | Get current state | `workspace_id` | `include_outputs` |

### Usage Example

```python
from tinyhive.controllers import terraform_controller

# List workspaces
result = terraform_controller.execute("production", "list_workspaces", {
    "search_name": "prod-"
})

# Create a run
result = terraform_controller.execute("production", "create_run", {
    "workspace_id": "ws-abc123",
    "message": "Deploy v2.1.0",
    "auto_apply": False
})
run_id = result["result"]["id"]

# Check run status
result = terraform_controller.execute("production", "get_run", {
    "run_id": run_id
})
print(f"Status: {result['result']['status']}")

# Apply when ready
if result["result"]["status"] == "planned":
    terraform_controller.execute("production", "apply_run", {
        "run_id": run_id,
        "comment": "Approved by automation"
    })

# Get state outputs
result = terraform_controller.execute("production", "get_state_version", {
    "workspace_id": "ws-abc123",
    "include_outputs": True
})
for output in result["result"]["outputs"]:
    print(f"{output['name']}: {output['value']}")
```

---

## TikTok Controller

### Overview

TikTok API v2 controller for accessing user information, videos, and analytics. Supports content retrieval and research API features.

**Use Cases:**
- Retrieve user profile information
- List and query videos
- Get video comments
- Search videos (research API)
- Track follower/following counts

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `TIKTOK_ACCESS_TOKEN` | TikTok OAuth access token (or custom via `access_token_env`) |

**How to get credentials:**
1. Register at [TikTok Developer Portal](https://developers.tiktok.com)
2. Create an application
3. Implement OAuth flow to obtain access token

**Required Scopes:**
- `user.info.basic` - user info
- `video.list` - list/query videos
- `research.data.basic` - search videos
- `user.info.stats` - follower/following counts

### Profile Configuration

```json
{
    "access_token_env": "TIKTOK_ACCESS_TOKEN",
    "default_video_fields": ["id", "title", "create_time", "cover_image_url", "share_url"]
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `get_user_info` | Get authenticated user info | - | `fields` |
| `list_videos` | List user's videos | - | `cursor`, `max_count`, `fields` |
| `get_video_info` | Get video details | `video_id` | `fields` |
| `query_videos` | Query multiple videos | `video_ids` | `fields` |
| `get_video_comments` | List video comments | `video_id` | `cursor`, `max_count`, `fields` |
| `search_videos` | Search videos by keyword | `keyword` | `cursor`, `max_count`, `start_date`, `end_date`, `region_code`, `fields` |
| `get_user_followers` | Get follower count | - | - |
| `get_user_following` | Get following count | - | - |

### Usage Example

```python
from tinyhive.controllers import tiktok_controller

# Get user info
result = tiktok_controller.execute("my_account", "get_user_info", {
    "fields": ["open_id", "display_name", "avatar_url", "follower_count"]
})
print(f"Followers: {result['data']['user']['follower_count']}")

# List videos
result = tiktok_controller.execute("my_account", "list_videos", {
    "max_count": 20,
    "fields": ["id", "title", "view_count", "like_count", "create_time"]
})

for video in result["data"]["videos"]:
    print(f"{video['title']}: {video['view_count']} views")

# Search videos (requires research API access)
result = tiktok_controller.execute("my_account", "search_videos", {
    "keyword": "cooking tutorial",
    "max_count": 50,
    "region_code": "US"
})
```

---

## Trello Controller

### Overview

Trello REST API controller for board and card management. Create and organize tasks, manage lists, and add comments.

**Use Cases:**
- List and manage boards
- Create and organize lists
- Create, update, and move cards
- Add comments to cards
- Automate project management workflows

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `TRELLO_API_KEY` | Trello API key (or custom via `api_key_env`) |
| `TRELLO_TOKEN` | Trello authorization token (or custom via `token_env`) |

**How to get credentials:**
1. Get API key from [Trello Developer](https://trello.com/app-key)
2. Generate a token by clicking the "Token" link on the same page
3. Authorize your application

### Profile Configuration

```json
{
    "api_key_env": "TRELLO_API_KEY",
    "token_env": "TRELLO_TOKEN"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_boards` | List user's boards | - | `filter`, `fields` |
| `get_board` | Get board details | `board_id` | `fields` |
| `list_lists` | Get lists on a board | `board_id` | `filter`, `fields` |
| `create_list` | Create a new list | `board_id`, `name` | `pos` |
| `list_cards` | Get cards in a list | `list_id` | `filter`, `fields` |
| `create_card` | Create a new card | `list_id`, `name` | `desc`, `due`, `labels`, `pos`, `idMembers` |
| `update_card` | Update a card | `card_id`, `fields` | - |
| `add_comment` | Add comment to card | `card_id`, `text` | - |

### Usage Example

```python
from tinyhive.controllers import trello_controller

# List boards
result = trello_controller.execute("personal", "list_boards", {
    "filter": "open"
})

# Get lists on a board
result = trello_controller.execute("personal", "list_lists", {
    "board_id": "board123"
})
todo_list_id = next(l["id"] for l in result["result"]["lists"] if l["name"] == "To Do")

# Create a card
result = trello_controller.execute("personal", "create_card", {
    "list_id": todo_list_id,
    "name": "Review pull request",
    "desc": "Review and merge PR #42",
    "due": "2024-01-20T17:00:00Z",
    "labels": "red,blue"
})
card_id = result["result"]["id"]

# Update card (move to different list)
result = trello_controller.execute("personal", "update_card", {
    "card_id": card_id,
    "fields": {
        "idList": "in_progress_list_id",
        "dueComplete": True
    }
})

# Add a comment
trello_controller.execute("personal", "add_comment", {
    "card_id": card_id,
    "text": "Started working on this."
})
```

---

## Twilio Controller

### Overview

Twilio REST API controller for SMS, WhatsApp, Voice calls, and phone number lookups. Full communication platform integration.

**Use Cases:**
- Send SMS messages
- Send WhatsApp messages
- Make voice calls
- Look up phone number information
- List and retrieve message/call history

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `TWILIO_ACCOUNT_SID` | Twilio Account SID (or custom via `account_sid_env`) |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token (or custom via `auth_token_env`) |

**How to get credentials:**
1. Sign up at [Twilio Console](https://console.twilio.com)
2. Find Account SID and Auth Token on the dashboard
3. Purchase a phone number for sending messages/calls

### Profile Configuration

```json
{
    "account_sid_env": "TWILIO_ACCOUNT_SID",
    "auth_token_env": "TWILIO_AUTH_TOKEN",
    "default_from": "+15551234567"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `send_sms` | Send SMS message | `to`, `body` | `from_`, `status_callback`, `messaging_service_sid` |
| `send_whatsapp` | Send WhatsApp message | `to`, `body` | `from_`, `media_url`, `content_sid`, `content_variables` |
| `make_call` | Initiate voice call | `to`, (`url` or `twiml`) | `from_`, `status_callback`, `status_callback_event`, `timeout`, `record`, `machine_detection` |
| `list_messages` | List messages | - | `to`, `from_`, `date_sent`, `date_sent_after`, `date_sent_before`, `limit`, `page_size` |
| `get_message` | Get message details | `message_sid` | - |
| `lookup_phone` | Look up phone number | `phone_number` | `type`, `country_code`, `fields` |
| `list_calls` | List calls | - | `to`, `from_`, `status`, `start_time`, `start_time_after`, `start_time_before`, `page_size` |
| `get_recordings` | Get call recordings | `call_sid` | `date_created`, `date_created_after`, `date_created_before`, `page_size` |

### Usage Example

```python
from tinyhive.controllers import twilio_controller

# Send SMS
result = twilio_controller.execute("production", "send_sms", {
    "to": "+15559876543",
    "body": "Your order #1234 has shipped!"
})
print(f"Message SID: {result['data']['sid']}")

# Send WhatsApp message
result = twilio_controller.execute("production", "send_whatsapp", {
    "to": "+15559876543",
    "body": "Your appointment is confirmed for tomorrow at 2 PM."
})

# Make a call with TwiML
result = twilio_controller.execute("production", "make_call", {
    "to": "+15559876543",
    "twiml": "<Response><Say>Hello! Your verification code is 1 2 3 4.</Say></Response>"
})

# Look up phone number
result = twilio_controller.execute("production", "lookup_phone", {
    "phone_number": "+15559876543",
    "type": "carrier"
})
print(f"Carrier: {result['data']['carrier']['name']}")

# List recent messages
result = twilio_controller.execute("production", "list_messages", {
    "date_sent_after": "2024-01-01",
    "page_size": 20
})
```

---

## Twitch Controller

### Overview

Twitch Helix API controller for accessing streams, users, videos, clips, and games. Monitor live streams and retrieve content metadata.

**Use Cases:**
- Get user and channel information
- Monitor live streams
- Search for channels
- Retrieve videos and clips
- Get game/category information
- Access chat settings

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `TWITCH_CLIENT_ID` | Twitch application Client ID |
| `TWITCH_OAUTH_TOKEN` | OAuth Bearer token |

**How to get credentials:**
1. Register an app at [Twitch Developer Console](https://dev.twitch.tv/console/apps)
2. Copy the Client ID from the app dashboard
3. Generate OAuth token via [OAuth flow](https://dev.twitch.tv/docs/authentication) or use [Token Generator](https://twitchtokengenerator.com)

### Profile Configuration

```json
{
    "client_id_env": "TWITCH_CLIENT_ID",
    "oauth_token_env": "TWITCH_OAUTH_TOKEN"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `get_users` | Get user information | (`id` or `login`) | - |
| `get_streams` | Get active streams | - | `user_id`, `user_login`, `game_id`, `type`, `language`, `first`, `before`, `after` |
| `get_channel` | Get channel information | `broadcaster_id` | - |
| `search_channels` | Search channels | `query` | `first`, `after`, `live_only` |
| `get_videos` | Get videos | (`id` or `user_id` or `game_id`) | `type`, `language`, `period`, `sort`, `first`, `before`, `after` |
| `get_clips` | Get clips | (`id` or `broadcaster_id` or `game_id`) | `started_at`, `ended_at`, `first`, `before`, `after` |
| `get_games` | Get game information | (`id` or `name` or `igdb_id`) | - |
| `get_chat_settings` | Get chat settings | `broadcaster_id` | `moderator_id` |

### Usage Example

```python
from tinyhive.controllers import twitch_controller

# Get user info
result = twitch_controller.execute("default", "get_users", {
    "login": ["ninja", "shroud"]
})
for user in result["data"]["data"]:
    print(f"{user['display_name']}: {user['description']}")

# Get live streams for a game
result = twitch_controller.execute("default", "get_streams", {
    "game_id": "21779",  # League of Legends
    "first": 10
})
for stream in result["data"]["data"]:
    print(f"{stream['user_name']}: {stream['title']} ({stream['viewer_count']} viewers)")

# Search channels
result = twitch_controller.execute("default", "search_channels", {
    "query": "speedrun",
    "live_only": True,
    "first": 20
})

# Get top clips for a broadcaster
result = twitch_controller.execute("default", "get_clips", {
    "broadcaster_id": "12345678",
    "first": 10
})
for clip in result["data"]["data"]:
    print(f"{clip['title']}: {clip['view_count']} views - {clip['url']}")

# Get game info
result = twitch_controller.execute("default", "get_games", {
    "name": "Minecraft"
})
print(f"Game ID: {result['data']['data'][0]['id']}")
```

---

## Common Patterns

### Error Handling

All controllers return a consistent response format:

```python
# Success
{"ok": True, "data": {...}}

# Error
{"ok": False, "error": "Error message"}
```

Always check the `ok` field before accessing data:

```python
result = controller.execute(profile, action, params)
if result["ok"]:
    process_data(result["data"])
else:
    handle_error(result["error"])
```

### Profile Management

Profiles are stored in `profiles/{name}.json`. Create separate profiles for different environments:

- `production.json` - Production credentials
- `staging.json` - Staging environment
- `development.json` - Development/test credentials

### Environment Variables

Store sensitive credentials in environment variables, not in profile files:

```bash
export STRIPE_SECRET_KEY="sk_live_..."
export TWILIO_ACCOUNT_SID="AC..."
export TWILIO_AUTH_TOKEN="..."
```
