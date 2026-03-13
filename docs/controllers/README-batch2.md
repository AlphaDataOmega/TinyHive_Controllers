# TinyHive Controllers - Batch 2

This document covers the following controllers: CircleCI, ClickUp, Cloudflare, Confluence, Contentful, Database, Datadog, Discord, Docker Hub, and DocuSign.

---

## Table of Contents

1. [CircleCI Controller](#circleci-controller)
2. [ClickUp Controller](#clickup-controller)
3. [Cloudflare Controller](#cloudflare-controller)
4. [Confluence Controller](#confluence-controller)
5. [Contentful Controller](#contentful-controller)
6. [Database Controller](#database-controller)
7. [Datadog Controller](#datadog-controller)
8. [Discord Controller](#discord-controller)
9. [Docker Hub Controller](#docker-hub-controller)
10. [DocuSign Controller](#docusign-controller)

---

## CircleCI Controller

### Overview

CircleCI is a continuous integration and continuous delivery (CI/CD) platform. This controller integrates with the CircleCI API v2 to manage pipelines, workflows, and jobs.

**Use Cases:**
- Trigger CI/CD pipelines programmatically
- Monitor build status and workflow progress
- Retrieve job artifacts
- Cancel running workflows

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `CIRCLECI_TOKEN` | CircleCI API token (default) |

**How to get credentials:**
1. Log in to CircleCI
2. Go to User Settings > Personal API Tokens
3. Click "Create New Token"
4. Copy the generated token and set it as `CIRCLECI_TOKEN`

### Profile Configuration

```json
{
  "token_env": "CIRCLECI_TOKEN",
  "default_org_slug": "gh/myorg",
  "default_project_slug": "gh/myorg/myrepo"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `token_env` | No | Environment variable name for API token (default: `CIRCLECI_TOKEN`) |
| `default_org_slug` | No | Default organization slug (e.g., `gh/myorg` or `bb/myorg`) |
| `default_project_slug` | No | Default project slug (e.g., `gh/myorg/myrepo`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_pipelines` | List pipelines for a project or org | - | `project_slug`, `org_slug`, `branch`, `page_token` |
| `get_pipeline` | Get a specific pipeline by ID | `pipeline_id` | - |
| `trigger_pipeline` | Trigger a new pipeline | `project_slug` (or from profile) | `branch`, `tag`, `parameters` |
| `list_workflows` | List workflows for a pipeline | `pipeline_id` | `page_token` |
| `get_workflow` | Get a specific workflow | `workflow_id` | - |
| `cancel_workflow` | Cancel a running workflow | `workflow_id` | - |
| `list_jobs` | List jobs in a workflow | `workflow_id` | `page_token` |
| `get_job_artifacts` | Get artifacts for a job | `job_number`, `project_slug` | `page_token` |

### Usage Example

```python
from tinyhive.controller import execute

# Trigger a pipeline on main branch
result = execute("circleci", "myprofile", "trigger_pipeline", {
    "project_slug": "gh/myorg/myrepo",
    "branch": "main",
    "parameters": {
        "deploy_env": "staging"
    }
})

if result["ok"]:
    pipeline_id = result["data"]["id"]

    # List workflows for the pipeline
    workflows = execute("circleci", "myprofile", "list_workflows", {
        "pipeline_id": pipeline_id
    })

    # Get job artifacts
    artifacts = execute("circleci", "myprofile", "get_job_artifacts", {
        "project_slug": "gh/myorg/myrepo",
        "job_number": 123
    })
```

---

## ClickUp Controller

### Overview

ClickUp is a project management and productivity platform. This controller integrates with ClickUp API v2 to manage workspaces, spaces, tasks, and comments.

**Use Cases:**
- Create and update tasks programmatically
- Automate task assignments and status updates
- Add comments to tasks
- Query and filter tasks across workspaces

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `CLICKUP_TOKEN` | ClickUp API token or OAuth2 access token |

**How to get credentials:**
1. Log in to ClickUp
2. Go to Settings > Apps > API Token
3. Generate a personal API token
4. Alternatively, use OAuth2 flow for user-context access

### Profile Configuration

```json
{
  "token_env": "CLICKUP_TOKEN"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `token_env` | No | Environment variable name for API token (default: `CLICKUP_TOKEN`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_workspaces` | List authorized workspaces | - | - |
| `list_spaces` | List spaces in a workspace | `team_id` | `archived` |
| `list_folders` | List folders in a space | `space_id` | `archived` |
| `list_lists` | List lists in a folder | `folder_id` | `archived` |
| `list_tasks` | List tasks in a list | `list_id` | `include_closed`, `subtasks`, `page`, `order_by`, `reverse`, `statuses`, `assignees`, `due_date_gt`, `due_date_lt` |
| `create_task` | Create a new task | `list_id`, `name` | `description`, `assignees`, `due_date`, `due_date_time`, `priority`, `status`, `tags`, `parent`, `notify_all`, `custom_fields` |
| `update_task` | Update an existing task | `task_id` | `name`, `description`, `status`, `priority`, `due_date`, `due_date_time`, `start_date`, `start_date_time`, `assignees`, `archived`, `parent` |
| `add_comment` | Add a comment to a task | `task_id`, `comment_text` | `assignee`, `notify_all` |

### Usage Example

```python
from tinyhive.controller import execute

# List workspaces
workspaces = execute("clickup", "myprofile", "list_workspaces", {})

# Create a new task
result = execute("clickup", "myprofile", "create_task", {
    "list_id": "123456789",
    "name": "Implement new feature",
    "description": "Build the authentication module",
    "priority": 2,  # High priority
    "due_date": 1735689600000,  # Unix timestamp in ms
    "assignees": [12345678],
    "tags": ["backend", "auth"]
})

if result["ok"]:
    task_id = result["data"]["id"]

    # Add a comment
    execute("clickup", "myprofile", "add_comment", {
        "task_id": task_id,
        "comment_text": "Started working on this task"
    })
```

---

## Cloudflare Controller

### Overview

Cloudflare provides CDN, DNS, DDoS protection, and web security services. This controller integrates with Cloudflare API v4 to manage zones, DNS records, cache, and settings.

**Use Cases:**
- Manage DNS records programmatically
- Purge CDN cache
- Toggle development mode
- Retrieve zone analytics

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token |

**How to get credentials:**
1. Log in to Cloudflare Dashboard
2. Go to My Profile > API Tokens
3. Click "Create Token"
4. Use a template or create custom token with required permissions
5. Copy the token and set as `CLOUDFLARE_API_TOKEN`

**Required API Token Permissions:**
- Zone Read (for `list_zones`, `get_zone`)
- Zone Settings Edit (for `toggle_dev_mode`)
- Cache Purge (for `purge_cache`)
- DNS Edit (for create/update/delete DNS records)
- DNS Read (for `list_dns_records`)
- Analytics Read (for `get_analytics`)

### Profile Configuration

```json
{
  "token_env": "CLOUDFLARE_API_TOKEN",
  "account_id": "optional-account-id"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `token_env` | No | Environment variable name for API token (default: `CLOUDFLARE_API_TOKEN`) |
| `account_id` | No | Optional Cloudflare account ID |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_zones` | List all zones/domains | - | `name`, `status`, `per_page`, `page` |
| `get_zone` | Get zone details | `zone_id` | - |
| `purge_cache` | Purge cache for a zone | `zone_id` | `purge_everything`, `files`, `tags`, `hosts`, `prefixes` |
| `list_dns_records` | List DNS records | `zone_id` | `type`, `name`, `content`, `per_page`, `page` |
| `create_dns_record` | Create a DNS record | `zone_id`, `type`, `name`, `content` | `ttl`, `proxied`, `priority` |
| `update_dns_record` | Update a DNS record | `zone_id`, `record_id`, `type`, `name`, `content` | `ttl`, `proxied`, `priority` |
| `delete_dns_record` | Delete a DNS record | `zone_id`, `record_id` | - |
| `toggle_dev_mode` | Enable/disable development mode | `zone_id`, `enabled` | - |
| `get_analytics` | Get zone analytics | `zone_id` | `since`, `until` |

### Usage Example

```python
from tinyhive.controller import execute

# List all zones
zones = execute("cloudflare", "myprofile", "list_zones", {})

zone_id = zones["data"]["zones"][0]["id"]

# Create an A record
result = execute("cloudflare", "myprofile", "create_dns_record", {
    "zone_id": zone_id,
    "type": "A",
    "name": "api.example.com",
    "content": "192.168.1.1",
    "ttl": 3600,
    "proxied": True
})

# Purge entire cache
execute("cloudflare", "myprofile", "purge_cache", {
    "zone_id": zone_id,
    "purge_everything": True
})

# Enable development mode
execute("cloudflare", "myprofile", "toggle_dev_mode", {
    "zone_id": zone_id,
    "enabled": True
})
```

---

## Confluence Controller

### Overview

Confluence is Atlassian's team collaboration and wiki software. This controller integrates with the Confluence REST API to manage spaces, pages, and comments. Supports both Confluence Cloud and Server/Data Center.

**Use Cases:**
- Create and update documentation pages
- Search content using CQL
- Automate documentation workflows
- Add comments to pages

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `CONFLUENCE_EMAIL` | Your Atlassian account email (Cloud) or username (Server) |
| `CONFLUENCE_API_TOKEN` | API token (Cloud) or password (Server) |

**How to get credentials (Cloud):**
1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Copy the token and set as `CONFLUENCE_API_TOKEN`
4. Set your Atlassian email as `CONFLUENCE_EMAIL`

### Profile Configuration

**Confluence Cloud:**
```json
{
  "base_url": "https://yoursite.atlassian.net/wiki",
  "email_env": "CONFLUENCE_EMAIL",
  "api_token_env": "CONFLUENCE_API_TOKEN"
}
```

**Confluence Server/Data Center:**
```json
{
  "base_url": "https://confluence.yourcompany.com",
  "email_env": "CONFLUENCE_USERNAME",
  "api_token_env": "CONFLUENCE_PASSWORD"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `base_url` | Yes | Confluence instance URL |
| `email_env` | No | Environment variable for email/username |
| `api_token_env` | No | Environment variable for API token/password |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_spaces` | List Confluence spaces | - | `limit`, `start`, `type` |
| `get_space` | Get space details | `space_key` | - |
| `list_pages` | List pages | - | `space_key`, `title`, `limit`, `start` |
| `get_page` | Get page with content | `page_id` | `expand` |
| `create_page` | Create a new page | `space_key`, `title`, `body` | `parent_id` |
| `update_page` | Update a page | `page_id`, `title`, `body`, `version` | - |
| `search` | Search using CQL | `cql` | `limit`, `start` |
| `add_comment` | Add a comment to a page | `page_id`, `body` | - |

### Usage Example

```python
from tinyhive.controller import execute

# List spaces
spaces = execute("confluence", "myprofile", "list_spaces", {
    "type": "global",
    "limit": 25
})

# Create a new page
result = execute("confluence", "myprofile", "create_page", {
    "space_key": "DOCS",
    "title": "API Documentation",
    "body": "<p>This is the API documentation page.</p>",
    "parent_id": "123456"
})

# Search for content
search_results = execute("confluence", "myprofile", "search", {
    "cql": 'space = "DOCS" AND title ~ "API"',
    "limit": 50
})

# Update a page (requires current version number)
page = execute("confluence", "myprofile", "get_page", {"page_id": "123456"})
execute("confluence", "myprofile", "update_page", {
    "page_id": "123456",
    "title": "Updated Title",
    "body": "<p>Updated content</p>",
    "version": page["data"]["version"]
})
```

---

## Contentful Controller

### Overview

Contentful is a headless CMS (Content Management System) that provides content infrastructure for digital products. This controller integrates with both the Content Delivery API (CDA) for reading and Content Management API (CMA) for writing.

**Use Cases:**
- Retrieve and display content entries
- Create and publish content programmatically
- Manage assets and content types
- Full-text content search

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `CONTENTFUL_CDA_TOKEN` | Content Delivery API token (read-only) |
| `CONTENTFUL_CMA_TOKEN` | Content Management API token (read/write) |

**How to get credentials:**
1. Log in to Contentful
2. Go to Settings > API Keys
3. Create or use existing API key
4. Copy the Content Delivery API access token for CDA
5. Create a Content Management API personal access token for CMA

### Profile Configuration

```json
{
  "space_id": "your-space-id",
  "environment": "master",
  "cda_token_env": "CONTENTFUL_CDA_TOKEN",
  "cma_token_env": "CONTENTFUL_CMA_TOKEN"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `space_id` | Yes | Contentful space ID |
| `environment` | No | Environment name (default: `master`) |
| `cda_token_env` | No | Environment variable for CDA token |
| `cma_token_env` | No | Environment variable for CMA token |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `get_entries` | Get entries (CDA) | - | `content_type`, `limit`, `skip`, `order`, `query` |
| `get_entry` | Get single entry (CDA) | `entry_id` | `locale` |
| `create_entry` | Create entry (CMA) | `content_type`, `fields` | - |
| `update_entry` | Update entry (CMA) | `entry_id`, `fields`, `version` | - |
| `publish_entry` | Publish entry (CMA) | `entry_id`, `version` | - |
| `get_assets` | Get assets (CDA) | - | `limit`, `skip`, `mimetype_group`, `query` |
| `get_content_types` | Get content types (CDA) | - | `limit`, `skip` |
| `search` | Full-text search (CDA) | `query` | `content_type`, `limit`, `skip`, `include` |

### Usage Example

```python
from tinyhive.controller import execute

# Get all blog posts
posts = execute("contentful", "myprofile", "get_entries", {
    "content_type": "blogPost",
    "limit": 10,
    "order": "-sys.createdAt"
})

# Create a new entry
result = execute("contentful", "myprofile", "create_entry", {
    "content_type": "blogPost",
    "fields": {
        "title": {"en-US": "My New Blog Post"},
        "body": {"en-US": "This is the blog content..."},
        "slug": {"en-US": "my-new-blog-post"}
    }
})

if result["ok"]:
    entry_id = result["data"]["id"]
    version = result["data"]["version"]

    # Publish the entry
    execute("contentful", "myprofile", "publish_entry", {
        "entry_id": entry_id,
        "version": version
    })

# Search content
search_results = execute("contentful", "myprofile", "search", {
    "query": "kubernetes",
    "content_type": "article",
    "include": 2
})
```

---

## Database Controller

### Overview

A unified database controller supporting multiple backends: SQLite, PostgreSQL, and MySQL. Provides secure, parameterized query execution with connection pooling.

**Use Cases:**
- Execute SQL queries across different database types
- Perform CRUD operations with parameterized queries
- Inspect database schema (tables and columns)
- Batch operations with execute_many

**Security Features:**
- Parameterized queries only (SQL injection prevention)
- Table name validation with regex
- Optional readonly mode
- Connection pooling with thread-safety

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `MYSQL_URL` | MySQL connection string |

**Connection string formats:**
- PostgreSQL: `postgresql://user:password@host:port/database`
- MySQL: `mysql://user:password@host:port/database`
- SQLite: No environment variable needed (uses file path)

### Profile Configuration

**SQLite:**
```json
{
  "db_type": "sqlite",
  "database": "/path/to/database.db",
  "readonly": false
}
```

**PostgreSQL:**
```json
{
  "db_type": "postgresql",
  "connection_env": "DATABASE_URL",
  "pool_size": 5,
  "pool_timeout": 30,
  "readonly": false
}
```

**MySQL:**
```json
{
  "db_type": "mysql",
  "connection_env": "MYSQL_URL",
  "pool_size": 5,
  "pool_timeout": 30,
  "readonly": false
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `db_type` | Yes | Database type: `sqlite`, `postgresql`, `mysql` |
| `database` | SQLite only | Path to SQLite database file |
| `connection_env` | PG/MySQL | Environment variable with connection string |
| `pool_size` | No | Connection pool size (default: 5) |
| `pool_timeout` | No | Pool timeout in seconds (default: 30) |
| `readonly` | No | Restrict to SELECT/SHOW/DESCRIBE only |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `execute_query` | Execute INSERT/UPDATE/DELETE | `query` | `values` |
| `execute_many` | Batch execute with multiple values | `query`, `values_list` | - |
| `fetch_one` | SELECT returning single row | `query` | `values` |
| `fetch_all` | SELECT returning all rows | `query` | `values`, `limit` |
| `list_tables` | List all tables | - | - |
| `describe_table` | Get column info for a table | `table` | - |

### Usage Example

```python
from tinyhive.controller import execute

# List all tables
tables = execute("database", "myprofile", "list_tables", {})

# Describe table structure
schema = execute("database", "myprofile", "describe_table", {
    "table": "users"
})

# Fetch all users (parameterized query)
users = execute("database", "myprofile", "fetch_all", {
    "query": "SELECT id, name, email FROM users WHERE status = ?",
    "values": ["active"],
    "limit": 100
})

# Insert a new record
result = execute("database", "myprofile", "execute_query", {
    "query": "INSERT INTO users (name, email) VALUES (?, ?)",
    "values": ["John Doe", "john@example.com"]
})

# Batch insert
execute("database", "myprofile", "execute_many", {
    "query": "INSERT INTO logs (event, timestamp) VALUES (?, ?)",
    "values_list": [
        ["login", "2024-01-01T10:00:00Z"],
        ["logout", "2024-01-01T12:00:00Z"],
        ["login", "2024-01-01T14:00:00Z"]
    ]
})
```

---

## Datadog Controller

### Overview

Datadog is a monitoring and observability platform for cloud-scale applications. This controller integrates with Datadog APIs to submit metrics, create monitors, post events, search logs, and manage incidents.

**Use Cases:**
- Submit custom metrics
- Create and manage monitoring alerts
- Post events for tracking deployments
- Search and analyze logs
- Create and manage incidents

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `DD_API_KEY` | Datadog API key (required) |
| `DD_APP_KEY` | Datadog Application key (required for most endpoints) |

**How to get credentials:**
1. Log in to Datadog
2. Go to Organization Settings > API Keys
3. Create a new API Key
4. Go to Organization Settings > Application Keys
5. Create a new Application Key

### Profile Configuration

```json
{
  "site": "datadoghq.com",
  "api_key_env": "DD_API_KEY",
  "app_key_env": "DD_APP_KEY"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `site` | No | Datadog site (default: `datadoghq.com`). Options: `datadoghq.eu`, `us3.datadoghq.com`, etc. |
| `api_key_env` | No | Environment variable for API key |
| `app_key_env` | No | Environment variable for Application key |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `submit_metrics` | Submit custom metrics | `series` | - |
| `query_metrics` | Query time series data | `query`, `from_ts`, `to_ts` | - |
| `create_monitor` | Create a monitor/alert | `name`, `type`, `query`, `message` | `tags`, `priority`, `options` |
| `list_monitors` | List monitors | - | `name`, `tags`, `page`, `page_size` |
| `create_event` | Post an event | `title`, `text` | `tags`, `alert_type`, `priority`, `host`, `aggregation_key`, `source_type_name`, `date_happened` |
| `search_logs` | Search logs | `query`, `from_ts`, `to_ts` | `limit`, `sort`, `indexes` |
| `list_dashboards` | List dashboards | - | `filter_shared`, `filter_deleted`, `count`, `start` |
| `create_incident` | Create an incident | `title`, `customer_impact` | `severity`, `fields`, `notification_handles` |

### Usage Example

```python
from tinyhive.controller import execute
import time

# Submit custom metrics
execute("datadog", "myprofile", "submit_metrics", {
    "series": [
        {
            "metric": "custom.api.response_time",
            "points": [[int(time.time()), 0.256]],
            "type": "gauge",
            "tags": ["env:prod", "service:api"]
        }
    ]
})

# Create a monitor
result = execute("datadog", "myprofile", "create_monitor", {
    "name": "High CPU Usage Alert",
    "type": "metric alert",
    "query": "avg(last_5m):avg:system.cpu.user{*} > 80",
    "message": "CPU usage is above 80%! @slack-alerts",
    "tags": ["env:prod", "team:platform"],
    "options": {
        "thresholds": {"critical": 80, "warning": 70},
        "notify_no_data": True
    }
})

# Post a deployment event
execute("datadog", "myprofile", "create_event", {
    "title": "Deployment: api-service v2.1.0",
    "text": "Deployed new version with bug fixes",
    "tags": ["env:prod", "service:api"],
    "alert_type": "info"
})

# Search logs
logs = execute("datadog", "myprofile", "search_logs", {
    "query": "service:api status:error",
    "from_ts": int(time.time()) - 3600,
    "to_ts": int(time.time()),
    "limit": 100
})
```

---

## Discord Controller

### Overview

Discord is a communication platform for communities and teams. This controller integrates with the Discord REST API v10 to send messages, manage channels, and handle roles.

**Use Cases:**
- Send messages and embeds to channels
- Send direct messages to users
- Create threads for discussions
- Manage roles and reactions
- Create webhooks for integrations

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `DISCORD_BOT_TOKEN` | Discord bot token |

**How to get credentials:**
1. Go to https://discord.com/developers/applications
2. Create a new application or select existing
3. Go to "Bot" section
4. Copy the token (you may need to reset it to see it)
5. Enable required intents (Server Members Intent if using `list_members`)
6. Invite bot to your server with appropriate permissions

**Required Bot Permissions:**
- Send Messages, Embed Links (for `send_message`)
- Create Public Threads, Create Private Threads (for `create_thread`)
- Add Reactions (for `add_reaction`)
- View Channels (for `list_channels`)
- Server Members Intent (for `list_members` - privileged)
- Manage Roles (for `add_role`, `remove_role`)
- Manage Webhooks (for `create_webhook`)

### Profile Configuration

```json
{
  "token_env": "DISCORD_BOT_TOKEN",
  "default_guild_id": "123456789012345678"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `token_env` | No | Environment variable for bot token (default: `DISCORD_BOT_TOKEN`) |
| `default_guild_id` | No | Default guild/server ID |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `send_message` | Send message to channel | `channel_id`, (`content` or `embeds`) | `tts`, `allowed_mentions` |
| `send_dm` | Send direct message | `user_id`, (`content` or `embeds`) | - |
| `create_thread` | Create a thread | `channel_id`, `name` | `message_id`, `auto_archive_duration`, `type`, `invitable` |
| `add_reaction` | Add reaction to message | `channel_id`, `message_id`, `emoji` | - |
| `list_channels` | List guild channels | `guild_id` (or from profile) | - |
| `list_members` | List guild members | `guild_id` (or from profile) | `limit`, `after` |
| `add_role` | Add role to member | `user_id`, `role_id`, `guild_id` | - |
| `remove_role` | Remove role from member | `user_id`, `role_id`, `guild_id` | - |
| `create_webhook` | Create a webhook | `channel_id`, `name` | `avatar` |

### Usage Example

```python
from tinyhive.controller import execute

# Send a message to a channel
result = execute("discord", "myprofile", "send_message", {
    "channel_id": "123456789012345678",
    "content": "Hello from TinyHive!",
    "embeds": [
        {
            "title": "Deployment Complete",
            "description": "v2.1.0 has been deployed",
            "color": 3066993,  # Green
            "fields": [
                {"name": "Environment", "value": "Production", "inline": True},
                {"name": "Status", "value": "Success", "inline": True}
            ]
        }
    ]
})

# Create a thread
execute("discord", "myprofile", "create_thread", {
    "channel_id": "123456789012345678",
    "name": "Bug Discussion - Issue #123",
    "auto_archive_duration": 1440  # 24 hours
})

# Add a role to a user
execute("discord", "myprofile", "add_role", {
    "guild_id": "123456789012345678",
    "user_id": "987654321098765432",
    "role_id": "111222333444555666"
})

# Create a webhook
webhook = execute("discord", "myprofile", "create_webhook", {
    "channel_id": "123456789012345678",
    "name": "Build Notifications"
})
```

---

## Docker Hub Controller

### Overview

Docker Hub is a container registry service for sharing container images. This controller integrates with Docker Hub API v2 to search, list, and manage repositories and tags.

**Use Cases:**
- Search for public images
- List repositories in an organization
- View and manage image tags
- Monitor rate limits
- Manage webhooks

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `DOCKERHUB_USERNAME` | Docker Hub username |
| `DOCKERHUB_PAT` | Personal Access Token |

**How to get credentials:**
1. Log in to Docker Hub
2. Go to Account Settings > Security
3. Click "New Access Token"
4. Set permissions (Read for queries, Read/Write for delete operations)
5. Copy the token and set as `DOCKERHUB_PAT`

### Profile Configuration

```json
{
  "username_env": "DOCKERHUB_USERNAME",
  "pat_env": "DOCKERHUB_PAT",
  "default_namespace": "myorg"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `username_env` | No | Environment variable for username |
| `pat_env` | No | Environment variable for Personal Access Token |
| `default_namespace` | No | Default namespace (organization or user) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `search` | Search for images | `query` | `page_size`, `page` |
| `list_repos` | List repositories | - | `namespace`, `page_size`, `page` |
| `get_repo` | Get repository details | `namespace`, `repository` | - |
| `list_tags` | List repository tags | `namespace`, `repository` | `page_size`, `page` |
| `get_tag` | Get tag details | `namespace`, `repository`, `tag` | - |
| `delete_tag` | Delete a tag | `namespace`, `repository`, `tag` | - |
| `get_rate_limits` | Get rate limit status | - | - |
| `list_webhooks` | List repository webhooks | `namespace`, `repository` | - |

### Usage Example

```python
from tinyhive.controller import execute

# Search for images
results = execute("dockerhub", "myprofile", "search", {
    "query": "nginx",
    "page_size": 10
})

# List organization repositories
repos = execute("dockerhub", "myprofile", "list_repos", {
    "namespace": "myorg"
})

# List tags for a repository
tags = execute("dockerhub", "myprofile", "list_tags", {
    "namespace": "myorg",
    "repository": "myapp",
    "page_size": 25
})

# Get specific tag details
tag_info = execute("dockerhub", "myprofile", "get_tag", {
    "namespace": "myorg",
    "repository": "myapp",
    "tag": "v2.1.0"
})

# Check rate limits
rate_limits = execute("dockerhub", "myprofile", "get_rate_limits", {})

# Delete an old tag (WARNING: destructive!)
execute("dockerhub", "myprofile", "delete_tag", {
    "namespace": "myorg",
    "repository": "myapp",
    "tag": "v1.0.0-deprecated"
})
```

---

## DocuSign Controller

### Overview

DocuSign is an electronic signature platform for managing digital agreements and signatures. This controller integrates with the DocuSign eSignature REST API to create, send, and manage envelopes.

**Use Cases:**
- Create and send documents for signature
- Use templates for recurring documents
- Track envelope status
- Download signed documents
- Void or resend envelopes

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `DOCUSIGN_ACCESS_TOKEN` | OAuth access token |

**How to get credentials:**
1. Create a DocuSign developer account
2. Create an integration key (client ID)
3. Obtain an access token via OAuth flow (Authorization Code Grant or JWT Grant)
4. Set the access token as `DOCUSIGN_ACCESS_TOKEN`

**Required OAuth Scopes:**
- `signature`: Basic eSignature operations
- `extended`: Extended operations (void, etc.)
- `impersonation`: For JWT Grant user impersonation

### Profile Configuration

**Demo/Sandbox:**
```json
{
  "account_id": "your-docusign-account-id",
  "token_env": "DOCUSIGN_ACCESS_TOKEN",
  "base_url": "https://demo.docusign.net/restapi/v2.1"
}
```

**Production:**
```json
{
  "account_id": "your-docusign-account-id",
  "token_env": "DOCUSIGN_ACCESS_TOKEN",
  "base_url": "https://na2.docusign.net/restapi/v2.1"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `account_id` | Yes | DocuSign account ID |
| `token_env` | No | Environment variable for access token |
| `base_url` | No | API base URL (default: demo) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `create_envelope` | Create and send envelope | `email_subject`, `recipients`, `documents` | `status`, `email_blurb` |
| `get_envelope` | Get envelope details | `envelope_id` | `include` |
| `list_envelopes` | List envelopes | `from_date` | `to_date`, `status`, `folder_types`, `count`, `start_position`, `search_text` |
| `void_envelope` | Void an envelope | `envelope_id`, `void_reason` | - |
| `download_document` | Download document | `envelope_id`, `document_id` | `local_path` |
| `get_recipients` | Get envelope recipients | `envelope_id` | `include_tabs`, `include_extended` |
| `create_from_template` | Create envelope from template | `template_id`, `recipients` | `email_subject`, `email_blurb`, `status` |
| `resend_envelope` | Resend notifications | `envelope_id` | `resend_reason` |

### Usage Example

```python
from tinyhive.controller import execute
import base64

# Read document and encode to base64
with open("contract.pdf", "rb") as f:
    doc_base64 = base64.b64encode(f.read()).decode("ascii")

# Create and send an envelope
result = execute("docusign", "myprofile", "create_envelope", {
    "email_subject": "Please sign: Service Agreement",
    "email_blurb": "Please review and sign the attached agreement.",
    "status": "sent",
    "documents": [
        {
            "documentId": "1",
            "name": "Service Agreement.pdf",
            "fileExtension": "pdf",
            "documentBase64": doc_base64
        }
    ],
    "recipients": {
        "signers": [
            {
                "email": "signer@example.com",
                "name": "John Doe",
                "recipientId": "1",
                "routingOrder": "1"
            }
        ],
        "carbonCopies": [
            {
                "email": "cc@example.com",
                "name": "Jane Smith",
                "recipientId": "2",
                "routingOrder": "2"
            }
        ]
    }
})

if result["ok"]:
    envelope_id = result["result"]["envelope_id"]

    # Check status
    status = execute("docusign", "myprofile", "get_envelope", {
        "envelope_id": envelope_id
    })

    # Download signed document when complete
    if status["result"]["status"] == "completed":
        execute("docusign", "myprofile", "download_document", {
            "envelope_id": envelope_id,
            "document_id": "combined",
            "local_path": "/path/to/signed_contract.pdf"
        })

# Create from template
execute("docusign", "myprofile", "create_from_template", {
    "template_id": "template-uuid-here",
    "status": "sent",
    "recipients": {
        "signers": [
            {
                "email": "signer@example.com",
                "name": "John Doe",
                "roleName": "Signer 1"
            }
        ]
    }
})
```

---

## Dependencies Summary

| Controller | Dependencies |
|------------|--------------|
| CircleCI | None (stdlib only) |
| ClickUp | None (stdlib only) |
| Cloudflare | None (stdlib only) |
| Confluence | None (stdlib only) |
| Contentful | None (stdlib only) |
| Database (SQLite) | None (stdlib only) |
| Database (PostgreSQL) | `psycopg2-binary` |
| Database (MySQL) | `mysql-connector-python` |
| Datadog | None (stdlib only) |
| Discord | None (stdlib only) |
| Docker Hub | None (stdlib only) |
| DocuSign | None (stdlib only) |
