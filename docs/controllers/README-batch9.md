# TinyHive Controllers Documentation - Batch 9

This document covers the following controllers: Typeform, VAPI, Vercel, Vonage, Webflow, Webhook, WooCommerce, WordPress, Xero, YouTube, Zendesk, and Zoom.

---

## Table of Contents

1. [Typeform Controller](#typeform-controller)
2. [VAPI Controller](#vapi-controller)
3. [Vercel Controller](#vercel-controller)
4. [Vonage Controller](#vonage-controller)
5. [Webflow Controller](#webflow-controller)
6. [Webhook Controller](#webhook-controller)
7. [WooCommerce Controller](#woocommerce-controller)
8. [WordPress Controller](#wordpress-controller)
9. [Xero Controller](#xero-controller)
10. [YouTube Controller](#youtube-controller)
11. [Zendesk Controller](#zendesk-controller)
12. [Zoom Controller](#zoom-controller)

---

## Typeform Controller

### Overview

The Typeform Controller provides integration with the Typeform API for managing forms, collecting responses, and accessing form analytics. Typeform is a platform for creating interactive forms, surveys, and quizzes with a conversational interface.

**Use Cases:**
- Create and manage survey forms
- Collect and analyze form responses
- Track form analytics and completion rates
- Build custom data collection workflows

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `TYPEFORM_TOKEN` | Personal access token for Typeform API |

**How to get credentials:**
1. Log in to your Typeform account
2. Navigate to https://admin.typeform.com/user/tokens
3. Create a new personal access token
4. Grant required scopes: `forms:read`, `forms:write`, `responses:read`, `insights:read`

### Profile Configuration

```json
{
  "token_env": "TYPEFORM_TOKEN",
  "workspace_id": "optional-workspace-id"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_forms` | List all forms in the workspace | - | `page`, `page_size`, `workspace_id`, `search` |
| `get_form` | Get details of a specific form | `form_id` | - |
| `create_form` | Create a new form | `title` | `fields`, `workspace_id`, `settings`, `welcome_screens`, `thankyou_screens` |
| `update_form` | Update an existing form | `form_id` | `title`, `fields`, `settings`, `welcome_screens`, `thankyou_screens` |
| `delete_form` | Delete a form | `form_id` | - |
| `list_responses` | List responses for a form | `form_id` | `page_size`, `since`, `until`, `after`, `before`, `completed`, `sort`, `query`, `fields` |
| `get_response` | Get a single response by ID | `form_id`, `response_id` | - |
| `get_form_insights` | Get analytics/insights for a form | `form_id` | - |

### Usage Example

```python
from tinyhive.controllers import typeform_controller

# List all forms
result = typeform_controller.execute("default", "list_forms", {
    "page": 1,
    "page_size": 10
})

# Create a new form with fields
result = typeform_controller.execute("default", "create_form", {
    "title": "Customer Feedback Survey",
    "fields": [
        {
            "type": "short_text",
            "title": "What is your name?",
            "ref": "name_field",
            "validations": {"required": True}
        },
        {
            "type": "rating",
            "title": "How would you rate our service?",
            "ref": "rating_field",
            "properties": {"steps": 5}
        }
    ]
})

# Get form responses
result = typeform_controller.execute("default", "list_responses", {
    "form_id": "abc123",
    "page_size": 50,
    "completed": True
})

# Get form analytics
result = typeform_controller.execute("default", "get_form_insights", {
    "form_id": "abc123"
})
```

---

## VAPI Controller

### Overview

The VAPI Controller integrates with VAPI.ai, a Voice AI platform for building voice agents. It supports creating assistants, managing calls, and uploading knowledge base files for AI-powered voice interactions.

**Use Cases:**
- Create voice AI assistants for customer support
- Initiate outbound voice calls
- Manage AI-powered phone conversations
- Upload knowledge base files for assistant training

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `VAPI_API_KEY` | API key for VAPI.ai |

**How to get credentials:**
1. Sign up at https://vapi.ai
2. Navigate to your dashboard settings
3. Generate an API key

### Profile Configuration

```json
{
  "api_key_env": "VAPI_API_KEY",
  "default_model": "gpt-4",
  "default_voice": "jennifer-playht"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `create_assistant` | Create a new voice AI assistant | `name` | `first_message`, `system_prompt`, `model`, `voice` |
| `list_assistants` | List all assistants | - | `limit` |
| `get_assistant` | Get assistant details | `assistant_id` | - |
| `update_assistant` | Update assistant configuration | `assistant_id`, `fields` | - |
| `create_call` | Initiate an outbound call | `assistant_id`, `phone_number_id`, `customer_number` | - |
| `list_calls` | List calls with optional filters | - | `assistant_id`, `limit` |
| `get_call` | Get call details including transcript | `call_id` | - |
| `upload_file` | Upload a file for knowledge base | `file_path` | - |

### Usage Example

```python
from tinyhive.controllers import vapi_controller

# Create a voice assistant
result = vapi_controller.execute("default", "create_assistant", {
    "name": "Support Agent",
    "first_message": "Hello! How can I help you today?",
    "system_prompt": "You are a helpful customer support agent...",
    "model": "gpt-4",
    "voice": "jennifer-playht"
})

# Initiate an outbound call
result = vapi_controller.execute("default", "create_call", {
    "assistant_id": "asst_123",
    "phone_number_id": "pn_456",
    "customer_number": "+15551234567"
})

# Get call details with transcript
result = vapi_controller.execute("default", "get_call", {
    "call_id": "call_789"
})

# Upload knowledge base file
result = vapi_controller.execute("default", "upload_file", {
    "file_path": "/path/to/knowledge.pdf"
})
```

---

## Vercel Controller

### Overview

The Vercel Controller provides integration with the Vercel REST API for managing projects, deployments, domains, and environment variables. Vercel is a cloud platform for frontend frameworks and static sites.

**Use Cases:**
- List and manage Vercel projects
- Create and monitor deployments
- Manage custom domains
- Handle environment variables

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `VERCEL_ACCESS_TOKEN` | Vercel API access token |

**How to get credentials:**
1. Log in to your Vercel account
2. Navigate to https://vercel.com/account/tokens
3. Create a new access token

### Profile Configuration

```json
{
  "team_id": "team_xxxxxxxxxxxx"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_projects` | List projects in the account/team | - | `limit` |
| `get_project` | Get details of a specific project | `project_id` | - |
| `list_deployments` | List deployments for a project | - | `project_id`, `limit`, `state` |
| `get_deployment` | Get details of a specific deployment | `deployment_id` | - |
| `create_deployment` | Create a new deployment | `name`, `git_source` | - |
| `cancel_deployment` | Cancel a deployment that is building | `deployment_id` | - |
| `list_domains` | List domains associated with a project | `project_id` | - |
| `get_env_vars` | Get environment variables for a project | `project_id` | - |

### Usage Example

```python
from tinyhive.controllers import vercel_controller

# List all projects
result = vercel_controller.execute("default", "list_projects", {
    "limit": 20
})

# Get project details
result = vercel_controller.execute("default", "get_project", {
    "project_id": "my-project"
})

# Create a deployment from GitHub
result = vercel_controller.execute("default", "create_deployment", {
    "name": "my-project",
    "git_source": {
        "type": "github",
        "repo": "owner/repo",
        "ref": "main"
    }
})

# List deployments filtered by state
result = vercel_controller.execute("default", "list_deployments", {
    "project_id": "my-project",
    "state": "READY"
})

# Get environment variables
result = vercel_controller.execute("default", "get_env_vars", {
    "project_id": "my-project"
})
```

---

## Vonage Controller

### Overview

The Vonage Controller integrates with Vonage Communications APIs supporting SMS, Voice, Verify (2FA), and Number Insight services. Vonage provides cloud communications APIs for messaging and voice.

**Use Cases:**
- Send SMS messages
- Make outbound voice calls
- Implement two-factor authentication (2FA)
- Look up phone number information

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `VONAGE_API_KEY` | Vonage API key |
| `VONAGE_API_SECRET` | Vonage API secret |

**How to get credentials:**
1. Sign up at https://dashboard.nexmo.com
2. Your API key and secret are displayed on the dashboard
3. For Voice API, create an application and download the private key

### Profile Configuration

```json
{
  "api_key_env": "VONAGE_API_KEY",
  "api_secret_env": "VONAGE_API_SECRET",
  "application_id": "optional-app-id-for-voice",
  "private_key_path": "/path/to/private.key",
  "default_from": "+15551234567",
  "webhook_base_url": "https://example.com/webhooks"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `send_sms` | Send an SMS message | `to`, `text` | `from`, `type`, `ttl`, `callback` |
| `get_message` | Get the status of a message | `message_id` | - |
| `list_messages` | List messages within a date range | `date_start`, `date_end` | `status`, `to`, `from`, `page_size`, `order` |
| `create_call` | Create an outbound voice call | `to` | `from`, `answer_url`, `ncco`, `event_url`, `machine_detection`, `length_timer`, `ringing_timer` |
| `get_call` | Get details of a voice call | `call_uuid` | - |
| `send_verification` | Start a verification (2FA) request | `number`, `brand` | `code_length`, `pin_expiry`, `next_event_wait`, `workflow_id`, `lg` |
| `check_verification` | Check a verification code | `request_id`, `code` | - |
| `lookup_number` | Look up information about a phone number | `number` | `type`, `country`, `cnam` |

### Usage Example

```python
from tinyhive.controllers import vonage_controller

# Send an SMS
result = vonage_controller.execute("default", "send_sms", {
    "from": "+15551234567",
    "to": "+15559876543",
    "text": "Hello from TinyHive!"
})

# Create a voice call with NCCO
result = vonage_controller.execute("default", "create_call", {
    "to": "+15559876543",
    "ncco": [
        {"action": "talk", "text": "Hello, this is a test call."}
    ]
})

# Start 2FA verification
result = vonage_controller.execute("default", "send_verification", {
    "number": "+15559876543",
    "brand": "MyApp",
    "code_length": 6
})

# Check verification code
result = vonage_controller.execute("default", "check_verification", {
    "request_id": "req_123",
    "code": "123456"
})

# Look up number information
result = vonage_controller.execute("default", "lookup_number", {
    "number": "+15559876543",
    "type": "advanced"
})
```

---

## Webflow Controller

### Overview

The Webflow Controller provides integration with the Webflow CMS API v2 for managing sites, collections, and CMS items. Webflow is a visual web design platform with a powerful CMS.

**Use Cases:**
- Manage Webflow sites and collections
- Create and update CMS items
- Publish content programmatically
- Build headless CMS workflows

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `WEBFLOW_ACCESS_TOKEN` | Bearer token for Webflow API |

**How to get credentials:**
1. Log in to your Webflow account
2. Navigate to Site Settings > Apps & Integrations
3. Generate an API token with required scopes

**Required Scopes:**
- `sites:read` - Read sites
- `cms:read` - Read collections and items
- `cms:write` - Create/update/publish items

### Profile Configuration

```json
{
  "site_id": "your-site-id"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_sites` | List all sites accessible with the token | - | - |
| `get_site` | Get details for a specific site | - | `site_id` |
| `list_collections` | List all CMS collections for a site | - | `site_id` |
| `get_collection` | Get details for a collection including fields | `collection_id` | - |
| `list_items` | List items in a collection | `collection_id` | `limit`, `offset` |
| `create_item` | Create a new item in a collection | `collection_id`, `fields` | `is_draft`, `is_archived` |
| `update_item` | Update an existing item | `collection_id`, `item_id`, `fields` | `is_draft`, `is_archived` |
| `publish_items` | Publish one or more items | `collection_id`, `item_ids` | - |

### Usage Example

```python
from tinyhive.controllers import webflow_controller

# List all sites
result = webflow_controller.execute("default", "list_sites", {})

# List collections for a site
result = webflow_controller.execute("default", "list_collections", {
    "site_id": "site_123"
})

# List items in a collection
result = webflow_controller.execute("default", "list_items", {
    "collection_id": "col_456",
    "limit": 50
})

# Create a new CMS item
result = webflow_controller.execute("default", "create_item", {
    "collection_id": "col_456",
    "fields": {
        "name": "New Blog Post",
        "slug": "new-blog-post",
        "content": "This is the post content..."
    },
    "is_draft": False
})

# Publish items
result = webflow_controller.execute("default", "publish_items", {
    "collection_id": "col_456",
    "item_ids": ["item_789", "item_790"]
})
```

---

## Webhook Controller

### Overview

The Webhook Controller provides comprehensive webhook functionality including sending HTTP POST webhooks, verifying signatures (GitHub, Stripe, Slack, custom HMAC), running a lightweight HTTP server to receive webhooks, and storing webhook events in SQLite.

**Use Cases:**
- Send webhooks to external services
- Receive and verify incoming webhooks
- Store webhook events for processing
- Build webhook-based integrations

### Authentication

No external authentication required. The controller manages its own signature verification.

### Profile Configuration

```json
{}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `send_webhook` | Send an HTTP POST webhook | `url`, `payload` | `headers`, `timeout` |
| `verify_signature` | Verify a webhook signature | `provider`, `payload`, `signature`, `secret` | `timestamp`, `algorithm`, `prefix` |
| `register_handler` | Register a webhook handler endpoint | `path`, `secret`, `provider` | `description` |
| `unregister_handler` | Remove a registered handler | - | `path`, `handler_id` |
| `list_handlers` | List all registered handlers | - | `active_only` |
| `get_recent_events` | Get recent webhook events | - | `limit`, `handler_id`, `since` |
| `start_server` | Start the HTTP server | - | `host`, `port` |
| `stop_server` | Stop the webhook server | - | - |

### Usage Example

```python
from tinyhive.controllers import webhook_controller

# Send a webhook
result = webhook_controller.execute("default", "send_webhook", {
    "url": "https://api.example.com/webhook",
    "payload": {
        "event": "order.created",
        "order_id": "12345"
    },
    "headers": {"X-Custom-Header": "value"}
})

# Register a webhook handler
result = webhook_controller.execute("default", "register_handler", {
    "path": "/webhooks/github",
    "secret": "my-webhook-secret",
    "provider": "github",
    "description": "GitHub repository webhooks"
})

# Start the webhook server
result = webhook_controller.execute("default", "start_server", {
    "host": "0.0.0.0",
    "port": 8080
})

# Verify a GitHub signature
result = webhook_controller.execute("default", "verify_signature", {
    "provider": "github",
    "payload": '{"action":"push"}',
    "signature": "sha256=abc123...",
    "secret": "my-webhook-secret"
})

# Get recent events
result = webhook_controller.execute("default", "get_recent_events", {
    "limit": 50,
    "handler_id": "handler_123"
})
```

---

## WooCommerce Controller

### Overview

The WooCommerce Controller provides integration with the WooCommerce REST API using OAuth 1.0a authentication. WooCommerce is an open-source e-commerce plugin for WordPress.

**Use Cases:**
- Manage orders and order statuses
- Update product inventory
- Retrieve customer information
- Build e-commerce automation workflows

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `WC_CONSUMER_KEY` | WooCommerce REST API consumer key |
| `WC_CONSUMER_SECRET` | WooCommerce REST API consumer secret |

**How to get credentials:**
1. In WordPress admin, go to WooCommerce > Settings > Advanced > REST API
2. Click "Add Key"
3. Set permissions (Read/Write) and generate API keys

### Profile Configuration

```json
{
  "store_url": "https://mystore.com",
  "api_version": "wc/v3",
  "consumer_key_env": "WC_CONSUMER_KEY",
  "consumer_secret_env": "WC_CONSUMER_SECRET"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_orders` | List orders from WooCommerce | - | `status`, `per_page`, `page`, `after`, `before`, `customer` |
| `get_order` | Get a single order by ID | `order_id` | - |
| `update_order` | Update an existing order | `order_id` | `status`, `meta_data`, `billing`, `shipping`, `customer_note` |
| `create_order` | Create a new order | `line_items` | `customer_id`, `billing`, `shipping`, `payment_method`, `payment_method_title`, `set_paid`, `status`, `shipping_lines`, `coupon_lines`, `meta_data` |
| `list_products` | List products | - | `category`, `status`, `per_page`, `page`, `search`, `sku`, `tag`, `on_sale`, `stock_status` |
| `get_product` | Get a single product by ID | `product_id` | - |
| `update_product` | Update an existing product | `product_id` | `stock_quantity`, `price`, `sale_price`, `status`, `name`, `description`, `short_description`, `sku`, `manage_stock`, `stock_status`, `categories`, `tags`, `meta_data` |
| `list_customers` | List customers | - | `per_page`, `page`, `email`, `search`, `role`, `orderby`, `order` |

### Usage Example

```python
from tinyhive.controllers import woocommerce_controller

# List recent orders
result = woocommerce_controller.execute("mystore", "list_orders", {
    "status": "processing",
    "per_page": 25
})

# Get order details
result = woocommerce_controller.execute("mystore", "get_order", {
    "order_id": 12345
})

# Update order status
result = woocommerce_controller.execute("mystore", "update_order", {
    "order_id": 12345,
    "status": "completed"
})

# Create a new order
result = woocommerce_controller.execute("mystore", "create_order", {
    "line_items": [
        {"product_id": 93, "quantity": 2}
    ],
    "billing": {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@example.com"
    },
    "set_paid": True
})

# Update product stock
result = woocommerce_controller.execute("mystore", "update_product", {
    "product_id": 93,
    "stock_quantity": 50,
    "manage_stock": True
})
```

---

## WordPress Controller

### Overview

The WordPress Controller provides integration with the WordPress REST API using application passwords. It supports managing posts, pages, categories, and media.

**Use Cases:**
- Create and publish blog posts
- Manage page content
- Upload media files
- Automate content workflows

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `WP_USERNAME` | WordPress username |
| `WP_APP_PASSWORD` | WordPress application password |

**How to get credentials:**
1. In WordPress admin, go to Users > Profile
2. Scroll to "Application Passwords"
3. Enter a name and click "Add New Application Password"
4. Copy the generated password (shown only once)

### Profile Configuration

```json
{
  "site_url": "https://example.com",
  "username_env": "WP_USERNAME",
  "app_password_env": "WP_APP_PASSWORD"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_posts` | List WordPress posts | - | `per_page`, `page`, `status`, `categories`, `search` |
| `get_post` | Get a single post by ID | `post_id` | - |
| `create_post` | Create a new post | `title`, `content` | `status`, `categories`, `tags` |
| `update_post` | Update an existing post | `post_id`, `fields` | - |
| `delete_post` | Delete a post | `post_id` | `force` |
| `list_pages` | List WordPress pages | - | `per_page`, `page`, `status` |
| `list_categories` | List categories | - | `per_page`, `page`, `hide_empty` |
| `upload_media` | Upload a media file | `file_path` | `title`, `alt_text` |

### Usage Example

```python
from tinyhive.controllers import wordpress_controller

# List published posts
result = wordpress_controller.execute("myblog", "list_posts", {
    "status": "publish",
    "per_page": 10
})

# Create a new post
result = wordpress_controller.execute("myblog", "create_post", {
    "title": "My New Blog Post",
    "content": "<p>This is the post content with <strong>HTML</strong>.</p>",
    "status": "draft",
    "categories": [5, 12]
})

# Update a post
result = wordpress_controller.execute("myblog", "update_post", {
    "post_id": 123,
    "fields": {
        "status": "publish",
        "title": "Updated Title"
    }
})

# Upload media
result = wordpress_controller.execute("myblog", "upload_media", {
    "file_path": "/path/to/image.jpg",
    "title": "Featured Image",
    "alt_text": "A descriptive alt text"
})

# List categories
result = wordpress_controller.execute("myblog", "list_categories", {
    "hide_empty": False
})
```

---

## Xero Controller

### Overview

The Xero Controller provides integration with the Xero Accounting API for managing invoices, contacts, accounts, payments, and organisation details. Xero is a cloud-based accounting software platform.

**Use Cases:**
- Create and manage invoices
- Manage customer/supplier contacts
- Record payments
- Access chart of accounts
- Retrieve organisation details

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `XERO_ACCESS_TOKEN` | OAuth 2.0 access token |

**How to get credentials:**
1. Create a Xero app at https://developer.xero.com
2. Implement OAuth 2.0 flow to obtain access token
3. Get tenant ID from the /connections endpoint after auth

**Required Scopes:**
- `accounting.transactions` - Invoices, payments
- `accounting.contacts` - Contacts
- `accounting.settings` - Accounts, organisation

### Profile Configuration

```json
{
  "tenant_id": "your-xero-tenant-id",
  "token_env": "XERO_ACCESS_TOKEN"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_invoices` | List invoices | - | `where`, `order`, `page` |
| `create_invoice` | Create an invoice | `type`, `contact`, `line_items` | `due_date`, `date`, `reference`, `status`, `currency_code` |
| `get_invoice` | Get a single invoice by ID | `invoice_id` | - |
| `list_contacts` | List contacts | - | `where`, `order`, `page` |
| `create_contact` | Create a contact | `name` | `email`, `first_name`, `last_name`, `phones`, `addresses`, `is_supplier`, `is_customer` |
| `list_accounts` | List chart of accounts | - | `where`, `order` |
| `create_payment` | Create a payment against an invoice | `invoice`, `account`, `amount`, `date` | `reference` |
| `get_organisation` | Get organisation details | - | - |

### Usage Example

```python
from tinyhive.controllers import xero_controller

# List invoices
result = xero_controller.execute("default", "list_invoices", {
    "where": 'Status=="DRAFT"',
    "order": "Date DESC"
})

# Create an invoice
result = xero_controller.execute("default", "create_invoice", {
    "type": "ACCREC",
    "contact": {"Name": "ABC Company"},
    "line_items": [
        {
            "description": "Consulting Services",
            "quantity": 10,
            "unit_amount": 150.00,
            "account_code": "200"
        }
    ],
    "due_date": "2024-02-15",
    "status": "DRAFT"
})

# Create a contact
result = xero_controller.execute("default", "create_contact", {
    "name": "New Customer Ltd",
    "email": "contact@newcustomer.com",
    "is_customer": True,
    "phones": [
        {"type": "DEFAULT", "number": "+1234567890"}
    ]
})

# Create a payment
result = xero_controller.execute("default", "create_payment", {
    "invoice": {"InvoiceID": "inv-123"},
    "account": {"Code": "090"},
    "amount": 1500.00,
    "date": "2024-01-20"
})

# Get organisation details
result = xero_controller.execute("default", "get_organisation", {})
```

---

## YouTube Controller

### Overview

The YouTube Controller provides read-only access to the YouTube Data API v3 for searching videos, retrieving video/channel details, managing playlists, and accessing comments and captions.

**Use Cases:**
- Search for videos and channels
- Retrieve video metadata and statistics
- Access channel information
- List playlist contents
- Read video comments

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `YOUTUBE_API_KEY` | YouTube Data API v3 key |

**How to get credentials:**
1. Go to Google Cloud Console
2. Create a project or select an existing one
3. Enable YouTube Data API v3
4. Create an API key under Credentials

### Profile Configuration

```json
{
  "api_key_env": "YOUTUBE_API_KEY",
  "default_max_results": 25,
  "default_parts": ["snippet", "contentDetails", "statistics"]
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `search` | Search for videos, channels, or playlists | `q` | `type`, `max_results`, `order`, `channel_id`, `page_token` |
| `get_video` | Get details for a single video | `video_id` | `parts` |
| `list_videos` | Get details for multiple videos | `video_ids` | `parts` |
| `get_channel` | Get channel information | `channel_id` | `parts` |
| `list_playlists` | List playlists for a channel | `channel_id` | `max_results`, `page_token` |
| `get_playlist_items` | Get videos in a playlist | `playlist_id` | `max_results`, `page_token` |
| `list_comments` | List top-level comments on a video | `video_id` | `max_results`, `order`, `page_token` |
| `get_captions` | List available captions for a video | `video_id` | - |

### Usage Example

```python
from tinyhive.controllers import youtube_controller

# Search for videos
result = youtube_controller.execute("default", "search", {
    "q": "python programming tutorial",
    "type": "video",
    "max_results": 10,
    "order": "viewCount"
})

# Get video details
result = youtube_controller.execute("default", "get_video", {
    "video_id": "dQw4w9WgXcQ",
    "parts": ["snippet", "statistics", "contentDetails"]
})

# Get channel information
result = youtube_controller.execute("default", "get_channel", {
    "channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw"
})

# List playlist items
result = youtube_controller.execute("default", "get_playlist_items", {
    "playlist_id": "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
    "max_results": 50
})

# List video comments
result = youtube_controller.execute("default", "list_comments", {
    "video_id": "dQw4w9WgXcQ",
    "max_results": 25,
    "order": "relevance"
})
```

---

## Zendesk Controller

### Overview

The Zendesk Controller provides integration with Zendesk Support API for ticket management and user operations. Zendesk is a customer service and support ticketing system.

**Use Cases:**
- Create and manage support tickets
- Update ticket status and assignments
- Add comments to tickets
- Search tickets with filters
- Manage users

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `ZENDESK_EMAIL` | Zendesk agent email address |
| `ZENDESK_API_TOKEN` | Zendesk API token |

**How to get credentials:**
1. Log in to Zendesk Admin Center
2. Go to Apps and integrations > APIs > Zendesk API
3. Enable Token access and create a new API token

### Profile Configuration

```json
{
  "subdomain": "yourcompany",
  "email_env": "ZENDESK_EMAIL",
  "token_env": "ZENDESK_API_TOKEN"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `create_ticket` | Create a new ticket | `subject`, `description` | `requester_id`, `priority`, `type` |
| `update_ticket` | Update an existing ticket | `ticket_id` | `status`, `priority`, `assignee_id`, `comment` |
| `get_ticket` | Get details of a ticket | `ticket_id` | - |
| `list_tickets` | List tickets | - | `status`, `assignee_id`, `per_page` |
| `add_comment` | Add a comment to a ticket | `ticket_id`, `body` | `public` |
| `search_tickets` | Search for tickets | `query` | - |
| `list_users` | List users | - | `role`, `per_page` |
| `create_user` | Create a new user | `name`, `email` | `role` |

### Usage Example

```python
from tinyhive.controllers import zendesk_controller

# Create a ticket
result = zendesk_controller.execute("support", "create_ticket", {
    "subject": "Need help with billing",
    "description": "I have a question about my invoice...",
    "priority": "high",
    "type": "question"
})

# Update ticket status
result = zendesk_controller.execute("support", "update_ticket", {
    "ticket_id": 12345,
    "status": "pending",
    "comment": "Waiting for customer response"
})

# Add a comment
result = zendesk_controller.execute("support", "add_comment", {
    "ticket_id": 12345,
    "body": "Thank you for contacting us. We're looking into this.",
    "public": True
})

# Search tickets
result = zendesk_controller.execute("support", "search_tickets", {
    "query": "status:open priority:high assignee:me"
})

# List users by role
result = zendesk_controller.execute("support", "list_users", {
    "role": "agent",
    "per_page": 50
})

# Create a user
result = zendesk_controller.execute("support", "create_user", {
    "name": "John Doe",
    "email": "john.doe@example.com",
    "role": "end-user"
})
```

---

## Zoom Controller

### Overview

The Zoom Controller provides integration with the Zoom REST API for meeting management, recordings, and user administration. Zoom is a video communications platform for meetings and webinars.

**Use Cases:**
- Create and manage meetings
- List and retrieve meeting details
- Access cloud recordings
- Manage Zoom users
- Get meeting participant information

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `ZOOM_ACCESS_TOKEN` | Zoom OAuth access token |

**How to get credentials:**
1. Create a Zoom app at https://marketplace.zoom.us
2. Choose OAuth app type
3. Implement OAuth flow to obtain access token
4. Grant required scopes for each action

**Required OAuth Scopes:**
- `meeting:read:list_meetings` - List meetings
- `meeting:write:meeting` - Create meetings
- `meeting:read:meeting` - Get meeting details
- `meeting:update:meeting` - Update meetings
- `meeting:delete:meeting` - Delete meetings
- `cloud_recording:read:list_user_recordings` - List recordings
- `meeting:read:participant` - Get participants
- `user:read:list_users` - List users

### Profile Configuration

```json
{
  "token_env": "ZOOM_ACCESS_TOKEN",
  "default_user_id": "me"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_meetings` | List meetings for a user | - | `user_id`, `type`, `page_size`, `next_page_token` |
| `create_meeting` | Create a new meeting | `topic` | `user_id`, `type`, `start_time`, `duration`, `timezone`, `agenda`, `password`, `settings` |
| `get_meeting` | Get meeting details | `meeting_id` | `occurrence_id`, `show_previous_occurrences` |
| `update_meeting` | Update a meeting | `meeting_id` | `occurrence_id`, `topic`, `type`, `start_time`, `duration`, `timezone`, `agenda`, `password`, `settings` |
| `delete_meeting` | Delete a meeting | `meeting_id` | `occurrence_id`, `schedule_for_reminder`, `cancel_meeting_reminder` |
| `list_recordings` | List cloud recordings for a user | `from`, `to` | `user_id`, `page_size`, `next_page_token`, `trash`, `trash_type` |
| `get_meeting_participants` | Get meeting participants (past meetings) | `meeting_id` | `page_size`, `next_page_token`, `include_fields` |
| `list_users` | List users in the account | - | `status`, `page_size`, `role_id`, `next_page_token`, `include_fields`, `license` |

### Usage Example

```python
from tinyhive.controllers import zoom_controller

# List upcoming meetings
result = zoom_controller.execute("default", "list_meetings", {
    "type": "upcoming",
    "page_size": 30
})

# Create a scheduled meeting
result = zoom_controller.execute("default", "create_meeting", {
    "topic": "Team Weekly Sync",
    "type": 2,
    "start_time": "2024-01-20T10:00:00Z",
    "duration": 60,
    "timezone": "America/New_York",
    "agenda": "Weekly team sync meeting",
    "settings": {
        "host_video": True,
        "participant_video": True,
        "waiting_room": True,
        "auto_recording": "cloud"
    }
})

# Get meeting details
result = zoom_controller.execute("default", "get_meeting", {
    "meeting_id": 123456789
})

# Update a meeting
result = zoom_controller.execute("default", "update_meeting", {
    "meeting_id": 123456789,
    "topic": "Updated Meeting Title",
    "duration": 90
})

# List cloud recordings
result = zoom_controller.execute("default", "list_recordings", {
    "from": "2024-01-01",
    "to": "2024-01-31"
})

# Get past meeting participants
result = zoom_controller.execute("default", "get_meeting_participants", {
    "meeting_id": 123456789
})

# List users
result = zoom_controller.execute("default", "list_users", {
    "status": "active",
    "page_size": 100
})
```

---

## Common Patterns

### Error Handling

All controllers return a consistent response format:

```python
# Success
{
    "ok": True,
    "result": {...}  # or "data": {...}
}

# Error
{
    "ok": False,
    "error": "Error message description"
}
```

### Profile Loading

Controllers load profiles from the `profiles/` directory:

```python
# Profile file: profiles/production.json
result = controller.execute("production", "action_name", params)
```

### Environment Variables

Sensitive credentials should always be stored in environment variables:

```bash
export TYPEFORM_TOKEN="your-token"
export ZOOM_ACCESS_TOKEN="your-oauth-token"
```
