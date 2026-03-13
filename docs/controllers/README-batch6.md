# TinyHive Controllers Documentation - Batch 6

This document covers the following controllers:
- [Pinterest](#pinterest-controller)
- [Pipedrive](#pipedrive-controller)
- [Plausible](#plausible-controller)
- [PostHog](#posthog-controller)
- [Prometheus](#prometheus-controller)
- [QuickBooks](#quickbooks-controller)
- [Reddit](#reddit-controller)
- [Redis](#redis-controller)
- [Replicate](#replicate-controller)
- [Retool](#retool-controller)

---

## Pinterest Controller

### Overview

The Pinterest Controller provides integration with Pinterest's API v5 for managing boards, pins, and accessing analytics. Pinterest is a visual discovery platform where users can save and share ideas through images (pins) organized into collections (boards).

**Use Cases:**
- Automate pin creation for marketing campaigns
- Schedule and manage Pinterest content
- Retrieve analytics data for performance tracking
- Programmatically create and organize boards
- Build social media management tools

### Authentication

Pinterest uses OAuth2 for authentication. You'll need to obtain an access token with appropriate scopes.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `PINTEREST_ACCESS_TOKEN` | OAuth2 access token from Pinterest |

**How to Get Credentials:**
1. Go to [Pinterest for Developers](https://developers.pinterest.com/)
2. Create a new app in the developer portal
3. Configure OAuth2 settings with required redirect URIs
4. Request required scopes and obtain access token via OAuth flow

**Required OAuth Scopes:**
- `user_accounts:read` - For get_user_account
- `boards:read` - For list_boards
- `boards:write` - For create_board
- `pins:read` - For get_pin, list_pins, search_pins
- `pins:write` - For create_pin
- `analytics:read` - For get_analytics

### Profile Configuration

```json
{
    "token_env": "PINTEREST_ACCESS_TOKEN"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `get_user_account` | Get authenticated user's account info | None | None |
| `list_boards` | List all boards for the user | None | `bookmark`, `page_size` (default: 25, max: 250), `privacy` (PUBLIC/PROTECTED/SECRET) |
| `create_board` | Create a new board | `name` | `description`, `privacy` (default: PUBLIC) |
| `create_pin` | Create a new pin on a board | `board_id`, `media_source` | `title`, `description`, `link`, `alt_text` |
| `get_pin` | Get details of a specific pin | `pin_id` | `ad_account_id` |
| `list_pins` | List pins on a board | `board_id` | `bookmark`, `page_size` (default: 25, max: 250) |
| `get_analytics` | Get analytics for a pin | `pin_id`, `start_date`, `end_date`, `metric_types` | `app_types`, `split_field`, `ad_account_id` |
| `search_pins` | Search for pins | `query` | `bookmark` |

### Usage Example

```python
from tinyhive.controllers import pinterest_controller

# Get user account info
result = pinterest_controller.execute("default", "get_user_account", {})
print(f"Username: {result['result']['username']}")

# Create a new board
result = pinterest_controller.execute("default", "create_board", {
    "name": "Travel Inspiration",
    "description": "Amazing places to visit",
    "privacy": "PUBLIC"
})
board_id = result["result"]["id"]

# Create a pin with an image URL
result = pinterest_controller.execute("default", "create_pin", {
    "board_id": board_id,
    "title": "Beautiful Sunset in Bali",
    "description": "Stunning sunset view from Uluwatu Temple",
    "link": "https://example.com/bali-guide",
    "media_source": {
        "source_type": "image_url",
        "url": "https://example.com/images/bali-sunset.jpg"
    },
    "alt_text": "Sunset over the ocean at Uluwatu Temple, Bali"
})

# Get analytics for a pin
result = pinterest_controller.execute("default", "get_analytics", {
    "pin_id": "12345678901234567",
    "start_date": "2024-01-01",
    "end_date": "2024-01-31",
    "metric_types": ["IMPRESSION", "SAVE", "PIN_CLICK", "OUTBOUND_CLICK"]
})
```

---

## Pipedrive Controller

### Overview

The Pipedrive Controller provides integration with Pipedrive CRM for managing deals, contacts (persons), and activities. Pipedrive is a sales-focused CRM platform designed to help teams track deals through customizable pipelines.

**Use Cases:**
- Automate deal creation and updates
- Sync contacts from external systems
- Schedule and track sales activities
- Build custom CRM integrations
- Generate sales reports and dashboards

### Authentication

Pipedrive uses API tokens for authentication. Each user can generate their own API token.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `PIPEDRIVE_API_TOKEN` | API token from Pipedrive settings |

**How to Get Credentials:**
1. Log into your Pipedrive account
2. Go to Settings > Personal Preferences > API
3. Copy your API token

### Profile Configuration

```json
{
    "company_domain": "yourcompany",
    "token_env": "PIPEDRIVE_API_TOKEN"
}
```

| Field | Description |
|-------|-------------|
| `company_domain` | Your Pipedrive subdomain (e.g., "yourcompany" for yourcompany.pipedrive.com) |
| `token_env` | Environment variable containing the API token |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_deals` | List deals from Pipedrive | None | `status`, `filter_id`, `start`, `limit` (max: 500) |
| `get_deal` | Get a specific deal by ID | `deal_id` | None |
| `create_deal` | Create a new deal | `title` | `value`, `currency`, `person_id`, `org_id`, `pipeline_id`, `stage_id` |
| `update_deal` | Update an existing deal | `deal_id`, `fields` | None |
| `list_persons` | List persons (contacts) | None | `filter_id`, `start`, `limit` (max: 500) |
| `create_person` | Create a new person | `name` | `email`, `phone`, `org_id` |
| `list_activities` | List activities | None | `type`, `filter_id`, `start_date`, `end_date`, `start`, `limit` |
| `create_activity` | Create a new activity | `subject`, `type` | `deal_id`, `person_id`, `due_date`, `due_time`, `duration`, `note` |

### Usage Example

```python
from tinyhive.controllers import pipedrive_controller

# Create a new contact
result = pipedrive_controller.execute("default", "create_person", {
    "name": "John Smith",
    "email": "john.smith@example.com",
    "phone": "+1-555-123-4567"
})
person_id = result["data"]["id"]

# Create a deal associated with the contact
result = pipedrive_controller.execute("default", "create_deal", {
    "title": "Enterprise Software License",
    "value": 50000,
    "currency": "USD",
    "person_id": person_id,
    "pipeline_id": 1,
    "stage_id": 1
})
deal_id = result["data"]["id"]

# Schedule a follow-up call
result = pipedrive_controller.execute("default", "create_activity", {
    "subject": "Follow-up call with John",
    "type": "call",
    "deal_id": deal_id,
    "person_id": person_id,
    "due_date": "2024-02-15",
    "due_time": "14:00",
    "note": "Discuss pricing and implementation timeline"
})

# List open deals
result = pipedrive_controller.execute("default", "list_deals", {
    "status": "open",
    "limit": 50
})
for deal in result["data"]:
    print(f"Deal: {deal['title']} - Value: {deal['value']}")
```

---

## Plausible Controller

### Overview

The Plausible Controller provides integration with Plausible Analytics, a privacy-focused, open-source web analytics platform. It supports both Plausible Cloud and self-hosted instances.

**Use Cases:**
- Retrieve real-time visitor counts
- Access aggregated website statistics
- Generate time-series analytics data
- Break down traffic by various dimensions (source, country, page, etc.)
- Manage sites and shared dashboard links

### Authentication

Plausible uses API keys for authentication.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `PLAUSIBLE_API_KEY` | API key from Plausible settings |

**How to Get Credentials:**
1. Log into your Plausible account
2. Go to Account Settings > API Keys
3. Create a new API key with appropriate permissions

### Profile Configuration

```json
{
    "api_key_env": "PLAUSIBLE_API_KEY",
    "base_url": "https://plausible.io",
    "site_id": "example.com"
}
```

| Field | Description |
|-------|-------------|
| `api_key_env` | Environment variable containing the API key |
| `base_url` | Plausible instance URL (default: https://plausible.io for cloud) |
| `site_id` | Default site domain to query (can be overridden per request) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `get_realtime_visitors` | Get current visitor count | None | `site_id` |
| `get_aggregate` | Get aggregate stats | None | `site_id`, `period`, `date`, `metrics`, `filters`, `compare` |
| `get_timeseries` | Get timeseries data | None | `site_id`, `period`, `date`, `metrics`, `interval`, `filters` |
| `get_breakdown` | Get stats broken down by property | `property` | `site_id`, `period`, `date`, `metrics`, `filters`, `limit`, `page` |
| `list_sites` | List all accessible sites | None | None |
| `create_site` | Create a new site | `domain` | `timezone` |
| `delete_site` | Delete a site | `site_id` | None |
| `create_shared_link` | Create a shared dashboard link | `name` | `site_id` |

**Available Periods:** `12mo`, `6mo`, `month`, `30d`, `7d`, `day`, `custom`

**Available Metrics:** `visitors`, `visits`, `pageviews`, `views_per_visit`, `bounce_rate`, `visit_duration`, `events`, `conversion_rate`

**Breakdown Properties:** `visit:source`, `visit:referrer`, `visit:utm_medium`, `visit:utm_source`, `visit:utm_campaign`, `visit:device`, `visit:browser`, `visit:os`, `visit:country`, `visit:region`, `visit:city`, `event:page`, `event:hostname`

### Usage Example

```python
from tinyhive.controllers import plausible_controller

# Get real-time visitor count
result = plausible_controller.execute("default", "get_realtime_visitors", {
    "site_id": "example.com"
})
print(f"Current visitors: {result['data']['visitors']}")

# Get aggregate stats for the last 30 days
result = plausible_controller.execute("default", "get_aggregate", {
    "site_id": "example.com",
    "period": "30d",
    "metrics": "visitors,pageviews,bounce_rate,visit_duration"
})

# Get traffic breakdown by source
result = plausible_controller.execute("default", "get_breakdown", {
    "site_id": "example.com",
    "period": "month",
    "property": "visit:source",
    "metrics": "visitors,visits",
    "limit": 10
})
for source in result["data"]["results"]:
    print(f"{source['source']}: {source['visitors']} visitors")

# Get timeseries data for visualization
result = plausible_controller.execute("default", "get_timeseries", {
    "site_id": "example.com",
    "period": "7d",
    "metrics": "visitors,pageviews",
    "interval": "date"
})
```

---

## PostHog Controller

### Overview

The PostHog Controller provides integration with PostHog, an open-source product analytics platform. It supports event tracking, user identification, feature flags, and analytics querying. Works with both PostHog Cloud and self-hosted instances.

**Use Cases:**
- Track user events and behaviors
- Identify and manage user profiles
- Evaluate feature flags for users
- Query analytics data programmatically
- Build custom analytics dashboards

### Authentication

PostHog uses API keys for authentication. Different API keys may be required for different operations (Project API key for capture, Personal API key for queries).

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `POSTHOG_API_KEY` | PostHog API key (Project or Personal) |

**How to Get Credentials:**
1. Log into your PostHog account
2. For event capture: Go to Project Settings > Project API Key
3. For queries: Go to Personal Settings > Personal API Keys

### Profile Configuration

```json
{
    "api_key_env": "POSTHOG_API_KEY",
    "host": "https://app.posthog.com",
    "project_id": "12345"
}
```

| Field | Description |
|-------|-------------|
| `api_key_env` | Environment variable containing the API key |
| `host` | PostHog instance URL (default: https://app.posthog.com) |
| `project_id` | PostHog project ID (required for query APIs) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `capture` | Capture a single event | `distinct_id`, `event` | `properties`, `timestamp` |
| `identify` | Identify a user and set properties | `distinct_id` | `properties` |
| `batch` | Send batch of events | `batch` (list of events) | None |
| `get_persons` | List persons (users) | None | `search`, `properties`, `limit`, `offset`, `project_id` |
| `get_events` | Query events | None | `event`, `date_from`, `date_to`, `person_id`, `distinct_id`, `limit`, `project_id` |
| `list_feature_flags` | List all feature flags | None | `active`, `limit`, `project_id` |
| `get_feature_flag` | Evaluate a feature flag for a user | `key`, `distinct_id` | `person_properties`, `group_properties`, `project_id` |
| `list_insights` | List saved insights | None | `saved`, `limit`, `project_id` |

### Usage Example

```python
from tinyhive.controllers import posthog_controller

# Track a page view event
result = posthog_controller.execute("default", "capture", {
    "distinct_id": "user_12345",
    "event": "pageview",
    "properties": {
        "$current_url": "https://example.com/pricing",
        "plan_viewed": "enterprise"
    }
})

# Identify a user with their properties
result = posthog_controller.execute("default", "identify", {
    "distinct_id": "user_12345",
    "properties": {
        "email": "user@example.com",
        "name": "John Doe",
        "plan": "enterprise",
        "company": "Acme Inc"
    }
})

# Send batch of events
result = posthog_controller.execute("default", "batch", {
    "batch": [
        {"event": "button_clicked", "distinct_id": "user_1", "properties": {"button": "signup"}},
        {"event": "button_clicked", "distinct_id": "user_2", "properties": {"button": "login"}},
        {"event": "form_submitted", "distinct_id": "user_1", "properties": {"form": "contact"}}
    ]
})

# Evaluate a feature flag for a user
result = posthog_controller.execute("default", "get_feature_flag", {
    "key": "new-checkout-flow",
    "distinct_id": "user_12345",
    "person_properties": {
        "plan": "enterprise"
    }
})
if result["data"]["enabled"]:
    print("Show new checkout flow")
```

---

## Prometheus Controller

### Overview

The Prometheus Controller provides integration with Prometheus HTTP API for querying metrics, time-series data, and monitoring information. Prometheus is an open-source monitoring and alerting toolkit widely used for cloud-native applications.

**Use Cases:**
- Execute PromQL queries programmatically
- Retrieve time-series data for dashboards
- Monitor scrape targets and their health
- Access alerting and recording rules
- Check active alerts

### Authentication

Prometheus can be configured with or without authentication. For secured instances, basic authentication is supported.

**Required Environment Variables (if auth enabled):**
| Variable | Description |
|----------|-------------|
| `PROMETHEUS_USER` | Basic auth username |
| `PROMETHEUS_PASSWORD` | Basic auth password |

### Profile Configuration

**Basic Profile (no auth):**
```json
{
    "prometheus_url": "http://localhost:9090"
}
```

**Profile with Basic Auth:**
```json
{
    "prometheus_url": "https://prometheus.example.com",
    "basic_auth_user_env": "PROMETHEUS_USER",
    "basic_auth_password_env": "PROMETHEUS_PASSWORD"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `query` | Execute an instant query | `query` (PromQL) | `time`, `timeout` |
| `query_range` | Execute a range query | `query`, `start`, `end`, `step` | `timeout` |
| `series` | Find series by label matchers | `match` (list) | `start`, `end` |
| `labels` | Get label names | None | `start`, `end`, `match` |
| `label_values` | Get values for a label | `label_name` | `start`, `end`, `match` |
| `targets` | Get current scrape targets | None | `state` (active/dropped/any) |
| `rules` | Get alerting and recording rules | None | `type`, `rule_name`, `rule_group`, `file` |
| `alerts` | Get active alerts | None | None |

### Usage Example

```python
from tinyhive.controllers import prometheus_controller

# Execute an instant query
result = prometheus_controller.execute("default", "query", {
    "query": "up{job='kubernetes-nodes'}"
})
for series in result["data"]["result"]:
    print(f"{series['metric']}: {series['value'][1]}")

# Execute a range query for CPU usage over time
result = prometheus_controller.execute("default", "query_range", {
    "query": "rate(node_cpu_seconds_total{mode='user'}[5m])",
    "start": "2024-01-01T00:00:00Z",
    "end": "2024-01-01T01:00:00Z",
    "step": "60s"
})

# Find all series matching a pattern
result = prometheus_controller.execute("default", "series", {
    "match": ["node_memory_.*", "node_cpu_.*"],
    "start": "-1h"
})

# Get all values for the 'job' label
result = prometheus_controller.execute("default", "label_values", {
    "label_name": "job"
})
print(f"Jobs: {result['data']}")

# Check scrape target health
result = prometheus_controller.execute("default", "targets", {
    "state": "active"
})
for target in result["data"]["activeTargets"]:
    print(f"{target['labels']['job']}: {target['health']}")

# Get active alerts
result = prometheus_controller.execute("default", "alerts", {})
for alert in result["data"]["alerts"]:
    print(f"Alert: {alert['labels']['alertname']} - {alert['state']}")
```

---

## QuickBooks Controller

### Overview

The QuickBooks Controller provides integration with QuickBooks Online API for accounting operations including invoices, customers, payments, and general queries. QuickBooks is a popular small business accounting software.

**Use Cases:**
- Create and manage invoices programmatically
- Sync customer data with external systems
- Record payments received
- Query accounting data
- Build custom financial reporting tools

### Authentication

QuickBooks Online uses OAuth2 for authentication. Access tokens expire after 1 hour and need to be refreshed using refresh tokens.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `QUICKBOOKS_ACCESS_TOKEN` | OAuth2 access token |

**How to Get Credentials:**
1. Create an app at [Intuit Developer Portal](https://developer.intuit.com)
2. Configure OAuth2 settings
3. Implement OAuth2 authorization flow to obtain tokens
4. Handle token refresh (tokens expire in 1 hour)

### Profile Configuration

```json
{
    "realm_id": "123456789",
    "token_env": "QUICKBOOKS_ACCESS_TOKEN",
    "environment": "production"
}
```

| Field | Description |
|-------|-------------|
| `realm_id` | Your QuickBooks company ID |
| `token_env` | Environment variable containing OAuth2 access token |
| `environment` | `production` or `sandbox` (default: production) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `create_invoice` | Create a new invoice | `customer_ref`, `line_items` | `due_date`, `doc_number`, `private_note`, `customer_memo` |
| `get_invoice` | Get an invoice by ID | `invoice_id` | None |
| `list_invoices` | List invoices | None | `max_results`, `start_position`, `customer_id`, `due_date_from`, `due_date_to` |
| `create_customer` | Create a new customer | `display_name` | `email`, `phone`, `company_name`, `given_name`, `family_name`, `billing_address`, `notes` |
| `list_customers` | List customers | None | `max_results`, `start_position`, `active`, `display_name` |
| `create_payment` | Record a payment | `customer_ref`, `amount` | `payment_method`, `payment_ref_num`, `deposit_to_account`, `invoice_refs`, `txn_date`, `private_note` |
| `get_company_info` | Get company information | None | None |
| `query` | Execute SQL-like query | `query` | None |

### Usage Example

```python
from tinyhive.controllers import quickbooks_controller

# Create a new customer
result = quickbooks_controller.execute("default", "create_customer", {
    "display_name": "Acme Corporation",
    "email": "billing@acme.com",
    "phone": "555-123-4567",
    "company_name": "Acme Corporation",
    "billing_address": {
        "line1": "123 Main Street",
        "city": "San Francisco",
        "country_sub_division_code": "CA",
        "postal_code": "94105",
        "country": "USA"
    }
})
customer_id = result["data"]["id"]

# Create an invoice
result = quickbooks_controller.execute("default", "create_invoice", {
    "customer_ref": customer_id,
    "line_items": [
        {
            "description": "Consulting Services - January 2024",
            "amount": 5000.00,
            "quantity": 1
        },
        {
            "description": "Software License",
            "amount": 1200.00,
            "quantity": 1
        }
    ],
    "due_date": "2024-02-15",
    "customer_memo": "Thank you for your business!"
})
invoice_id = result["data"]["id"]

# Record a payment for the invoice
result = quickbooks_controller.execute("default", "create_payment", {
    "customer_ref": customer_id,
    "amount": 6200.00,
    "payment_method": "Check",
    "payment_ref_num": "1234",
    "invoice_refs": [
        {"invoice_id": invoice_id, "amount": 6200.00}
    ]
})

# Execute a custom query
result = quickbooks_controller.execute("default", "query", {
    "query": "SELECT * FROM Invoice WHERE TotalAmt > '1000' MAXRESULTS 50"
})
```

---

## Reddit Controller

### Overview

The Reddit Controller provides integration with Reddit's API for reading and posting content, managing comments, voting, and searching. Reddit is a social news aggregation and discussion platform.

**Use Cases:**
- Monitor subreddits for mentions
- Automate content posting
- Build comment bots
- Search for specific content
- Analyze Reddit discussions

### Authentication

Reddit uses OAuth2 for API access. The controller supports both direct token usage and client credentials flow.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `REDDIT_ACCESS_TOKEN` | OAuth2 access token (direct token method) |
| `REDDIT_CLIENT_SECRET` | Client secret (client credentials method) |
| `REDDIT_PASSWORD` | Reddit password (client credentials method) |

**How to Get Credentials:**
1. Go to [Reddit App Preferences](https://www.reddit.com/prefs/apps)
2. Create a new "script" application
3. Note the client ID (under app name) and client secret

**Required API Scopes:**
- `identity` - For get_me
- `submit` - For submit_post
- `read` - For get_post, list_subreddit_posts, get_comments, search
- `vote` - For vote
- Comment posting requires appropriate scope

### Profile Configuration

**With Direct Token:**
```json
{
    "token_env": "REDDIT_ACCESS_TOKEN",
    "user_agent": "TinyHive/1.0 by your_username"
}
```

**With Client Credentials:**
```json
{
    "client_id": "your_client_id",
    "client_secret_env": "REDDIT_CLIENT_SECRET",
    "username": "your_username",
    "password_env": "REDDIT_PASSWORD",
    "user_agent": "TinyHive/1.0 by your_username"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `get_me` | Get authenticated user info | None | None |
| `submit_post` | Submit a new post | `subreddit`, `title` | `text`, `url`, `kind`, `flair_id`, `flair_text`, `nsfw`, `spoiler`, `send_replies` |
| `get_post` | Get details of a post | `post_id` | None |
| `list_subreddit_posts` | List posts from a subreddit | `subreddit` | `sort`, `limit`, `time`, `after`, `before` |
| `get_comments` | Get comments for a post | `post_id` | `subreddit`, `sort`, `limit`, `depth` |
| `post_comment` | Post a comment | `thing_id`, `text` | None |
| `vote` | Vote on post/comment | `thing_id`, `direction` | None |
| `search` | Search Reddit | `query` | `subreddit`, `sort`, `time`, `limit`, `after`, `type` |

### Usage Example

```python
from tinyhive.controllers import reddit_controller

# Get authenticated user info
result = reddit_controller.execute("default", "get_me", {})
print(f"Logged in as: {result['data']['name']}")

# Get hot posts from a subreddit
result = reddit_controller.execute("default", "list_subreddit_posts", {
    "subreddit": "programming",
    "sort": "hot",
    "limit": 10
})
for post in result["data"]["posts"]:
    print(f"{post['title']} - Score: {post['score']}")

# Submit a self post
result = reddit_controller.execute("default", "submit_post", {
    "subreddit": "test",
    "title": "Hello from TinyHive!",
    "text": "This is a test post created via the API.",
    "kind": "self"
})

# Search for posts
result = reddit_controller.execute("default", "search", {
    "query": "python machine learning",
    "subreddit": "programming",
    "sort": "relevance",
    "time": "month",
    "limit": 25
})

# Get comments on a post
result = reddit_controller.execute("default", "get_comments", {
    "post_id": "abc123",
    "sort": "top",
    "limit": 50
})

# Upvote a post
result = reddit_controller.execute("default", "vote", {
    "thing_id": "t3_abc123",
    "direction": 1  # 1=upvote, 0=remove, -1=downvote
})
```

---

## Redis Controller

### Overview

The Redis Controller provides direct access to Redis using raw socket connections with the RESP protocol. It requires no external dependencies beyond Python's standard library. Redis is an in-memory data structure store used as a database, cache, and message broker.

**Use Cases:**
- Caching and session management
- Real-time data storage
- Message queuing
- Rate limiting
- Leaderboards and counters

### Authentication

Redis authentication is handled via the connection URL which can include a password.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `REDIS_URL` | Redis connection URL |

**Redis URL Format:**
```
redis://[:password@]host:port/db
redis://:mypassword@localhost:6379/0
redis://localhost:6379/0
rediss://... (for SSL connections)
```

### Profile Configuration

```json
{
    "url_env": "REDIS_URL",
    "timeout": 30,
    "max_retries": 3
}
```

| Field | Description |
|-------|-------------|
| `url_env` | Environment variable containing Redis URL |
| `timeout` | Connection timeout in seconds (default: 30) |
| `max_retries` | Max connection retries (default: 3) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `get` | Get the value of a key | `key` | None |
| `set` | Set a key's value | `key`, `value` | `ex` (seconds), `px` (milliseconds), `nx`, `xx` |
| `delete` | Delete key(s) | `keys` (list) | None |
| `exists` | Check if a key exists | `key` | None |
| `keys` | Find keys matching pattern | `pattern` | None |
| `hget` | Get a hash field value | `key`, `field` | None |
| `hset` | Set a hash field | `key`, `field`, `value` | None |
| `lpush` | Push to list head | `key`, `values` | None |
| `lrange` | Get list range | `key` | `start`, `stop` |
| `expire` | Set key timeout | `key`, `seconds` | None |

### Usage Example

```python
from tinyhive.controllers import redis_controller

# Set a simple key-value pair
result = redis_controller.execute("default", "set", {
    "key": "user:1234:name",
    "value": "John Doe"
})

# Set with expiration (1 hour)
result = redis_controller.execute("default", "set", {
    "key": "session:abc123",
    "value": '{"user_id": 1234, "role": "admin"}',
    "ex": 3600
})

# Get a value
result = redis_controller.execute("default", "get", {
    "key": "user:1234:name"
})
print(f"Name: {result['data']}")

# Check if key exists
result = redis_controller.execute("default", "exists", {
    "key": "user:1234:name"
})
if result["data"]:
    print("Key exists")

# Work with hashes
result = redis_controller.execute("default", "hset", {
    "key": "user:1234",
    "field": "email",
    "value": "john@example.com"
})

result = redis_controller.execute("default", "hget", {
    "key": "user:1234",
    "field": "email"
})

# Work with lists
result = redis_controller.execute("default", "lpush", {
    "key": "notifications:1234",
    "values": ["New message received", "Your order shipped"]
})

result = redis_controller.execute("default", "lrange", {
    "key": "notifications:1234",
    "start": 0,
    "stop": -1  # Get all
})

# Find keys by pattern
result = redis_controller.execute("default", "keys", {
    "pattern": "user:*:name"
})
```

---

## Replicate Controller

### Overview

The Replicate Controller provides integration with Replicate's API for running machine learning models in the cloud. Replicate hosts thousands of open-source models for image generation, language processing, audio synthesis, and more.

**Use Cases:**
- Generate images using AI models (Stable Diffusion, DALL-E, etc.)
- Process and transform images
- Run language models
- Generate audio and music
- Build AI-powered applications

### Authentication

Replicate uses API tokens for authentication.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `REPLICATE_API_TOKEN` | API token from Replicate |

**How to Get Credentials:**
1. Create an account at [Replicate](https://replicate.com)
2. Go to [Account Settings > API Tokens](https://replicate.com/account/api-tokens)
3. Create a new API token

### Profile Configuration

```json
{
    "token_env": "REPLICATE_API_TOKEN",
    "default_timeout": 60,
    "webhook_url": null
}
```

| Field | Description |
|-------|-------------|
| `token_env` | Environment variable containing API token |
| `default_timeout` | Request timeout in seconds (default: 60) |
| `webhook_url` | Optional webhook URL for prediction completion |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `create_prediction` | Run a model (create prediction) | `version`, `input` | `webhook`, `webhook_events_filter` |
| `get_prediction` | Get prediction status/result | `prediction_id` | None |
| `cancel_prediction` | Cancel a running prediction | `prediction_id` | None |
| `list_predictions` | List recent predictions | None | `cursor` |
| `list_models` | List models for an owner | `owner` | `cursor` |
| `get_model` | Get model details | `owner`, `name` | None |
| `get_model_versions` | List model versions | `owner`, `name` | `cursor` |
| `list_collections` | List model collections | None | `cursor` |

### Usage Example

```python
from tinyhive.controllers import replicate_controller
import time

# Get details about a model
result = replicate_controller.execute("default", "get_model", {
    "owner": "stability-ai",
    "name": "sdxl"
})
latest_version = result["result"]["latest_version"]["id"]

# Create an image generation prediction
result = replicate_controller.execute("default", "create_prediction", {
    "version": latest_version,
    "input": {
        "prompt": "A serene mountain landscape at sunset, digital art",
        "negative_prompt": "blurry, low quality",
        "width": 1024,
        "height": 1024,
        "num_outputs": 1
    }
})
prediction_id = result["result"]["id"]

# Poll for completion
while True:
    result = replicate_controller.execute("default", "get_prediction", {
        "prediction_id": prediction_id
    })
    status = result["result"]["status"]

    if status == "succeeded":
        print(f"Image URL: {result['result']['output']}")
        break
    elif status == "failed":
        print(f"Error: {result['result']['error']}")
        break
    else:
        print(f"Status: {status}")
        time.sleep(2)

# List recent predictions
result = replicate_controller.execute("default", "list_predictions", {})
for pred in result["result"]["predictions"]:
    print(f"{pred['id']}: {pred['status']}")

# Cancel a running prediction
result = replicate_controller.execute("default", "cancel_prediction", {
    "prediction_id": prediction_id
})
```

---

## Retool Controller

### Overview

The Retool Controller provides integration with Retool's API for managing apps, users, groups, and workflows. Retool is a low-code platform for building internal tools. The controller supports both Retool Cloud and self-hosted instances.

**Use Cases:**
- Manage Retool users programmatically
- Automate user provisioning and group management
- Trigger Retool workflows from external systems
- List and manage Retool applications
- Build admin tools for Retool organizations

### Authentication

Retool uses API keys for authentication.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `RETOOL_API_KEY` | Retool API key |

**How to Get Credentials:**
1. Log into your Retool organization
2. Go to Settings > API
3. Create a new API key with appropriate permissions

### Profile Configuration

```json
{
    "host": "your-org.retool.com",
    "api_key_env": "RETOOL_API_KEY"
}
```

| Field | Description |
|-------|-------------|
| `host` | Your Retool host (e.g., "your-org.retool.com" for cloud, "retool.yourcompany.com" for self-hosted) |
| `api_key_env` | Environment variable containing the API key |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_apps` | List Retool apps | None | `folder_id` |
| `get_app` | Get app details | `app_id` | None |
| `list_users` | List all users | None | None |
| `get_user` | Get user details | `user_id` | None |
| `create_user` | Create a new user | `email`, `first_name`, `last_name` | None |
| `list_groups` | List permission groups | None | None |
| `add_user_to_group` | Add user to a group | `user_id`, `group_id` | None |
| `run_workflow` | Trigger a workflow | `workflow_id` | `data` |

### Usage Example

```python
from tinyhive.controllers import retool_controller

# List all apps
result = retool_controller.execute("default", "list_apps", {})
for app in result["data"]["apps"]:
    print(f"App: {app['name']} (ID: {app['id']})")

# Create a new user
result = retool_controller.execute("default", "create_user", {
    "email": "new.employee@company.com",
    "first_name": "John",
    "last_name": "Doe"
})
user_id = result["data"]["user"]["id"]

# List available groups
result = retool_controller.execute("default", "list_groups", {})
for group in result["data"]["groups"]:
    print(f"Group: {group['name']} (ID: {group['id']})")

# Add user to a group
result = retool_controller.execute("default", "add_user_to_group", {
    "user_id": user_id,
    "group_id": "developers_group_id"
})

# Trigger a workflow with data
result = retool_controller.execute("default", "run_workflow", {
    "workflow_id": "workflow_12345",
    "data": {
        "customer_id": "cust_abc123",
        "action": "send_welcome_email",
        "template": "onboarding_v2"
    }
})
print(f"Workflow result: {result['data']['result']}")

# Get detailed user information
result = retool_controller.execute("default", "get_user", {
    "user_id": user_id
})
user = result["data"]["user"]
print(f"User: {user['email']} - Groups: {user.get('groups', [])}")
```

---

## Common Patterns

### Error Handling

All controllers return responses in a consistent format:

```python
# Success
{"ok": True, "data": {...}}  # or "result" depending on controller

# Error
{"ok": False, "error": "Error message"}
```

Example error handling:

```python
result = controller.execute(profile, action, params)
if not result.get("ok"):
    print(f"Error: {result.get('error')}")
else:
    data = result.get("data") or result.get("result")
    # Process successful result
```

### Pagination

Many list actions support pagination:

```python
# Using cursor/bookmark based pagination
all_items = []
cursor = None

while True:
    params = {"limit": 100}
    if cursor:
        params["cursor"] = cursor  # or "bookmark", "after" depending on API

    result = controller.execute(profile, "list_items", params)
    items = result["data"]["items"]
    all_items.extend(items)

    cursor = result["data"].get("next") or result["data"].get("cursor")
    if not cursor:
        break
```

### Profile Management

Profiles are stored as JSON files in the `profiles/` directory. Create different profiles for different environments or accounts:

```
profiles/
  production.json
  staging.json
  development.json
```

Then use them by name:

```python
# Use production profile
result = controller.execute("production", "action", params)

# Use staging profile
result = controller.execute("staging", "action", params)
```
