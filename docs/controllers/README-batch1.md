# TinyHive Controllers Documentation - Batch 1

This document covers the following controllers: Airtable, Amplitude, Anthropic, Asana, Auth0, AWS, BigCommerce, Bitbucket, Box, and Calendly.

---

## Table of Contents

1. [Airtable Controller](#airtable-controller)
2. [Amplitude Controller](#amplitude-controller)
3. [Anthropic Controller](#anthropic-controller)
4. [Asana Controller](#asana-controller)
5. [Auth0 Controller](#auth0-controller)
6. [AWS Controller](#aws-controller)
7. [BigCommerce Controller](#bigcommerce-controller)
8. [Bitbucket Controller](#bitbucket-controller)
9. [Box Controller](#box-controller)
10. [Calendly Controller](#calendly-controller)

---

## Airtable Controller

### Overview

Airtable is a cloud-based platform that combines the flexibility of a spreadsheet with the power of a database. The Airtable controller enables you to:

- Manage records in Airtable tables (CRUD operations)
- Batch create multiple records
- List accessible bases and retrieve table schemas
- Filter and sort records using Airtable formulas

**Use Cases:** CRM data management, content calendars, inventory tracking, project management, custom databases.

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `AIRTABLE_API_KEY` | Airtable Personal Access Token |

**How to get credentials:**
1. Go to [Airtable Account](https://airtable.com/account)
2. Navigate to "Developer hub" > "Personal access tokens"
3. Create a new token with required scopes

**Required Scopes:**
- `data.records:read` - For list_records, get_record
- `data.records:write` - For create_record, create_records, update_record, delete_record
- `schema.bases:read` - For list_bases, get_schema

### Profile Configuration

```json
{
    "api_key_env": "AIRTABLE_API_KEY"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_records` | List records from a table | `base_id`, `table_name` | `fields`, `filter_formula`, `max_records`, `sort`, `page_size`, `offset`, `view` |
| `get_record` | Get a single record | `base_id`, `table_name`, `record_id` | - |
| `create_record` | Create a single record | `base_id`, `table_name`, `fields` | `typecast` |
| `create_records` | Batch create records (max 10) | `base_id`, `table_name`, `records` | `typecast` |
| `update_record` | Update a record | `base_id`, `table_name`, `record_id`, `fields` | `typecast` |
| `delete_record` | Delete a record | `base_id`, `table_name`, `record_id` | - |
| `list_bases` | List accessible bases | - | `offset` |
| `get_schema` | Get table schema for a base | `base_id` | - |

### Usage Example

```python
from tinyhive.controller import execute

# List all bases
result = execute("airtable", "myprofile", "list_bases", {})
print(result["data"]["bases"])

# List records with filtering
result = execute("airtable", "myprofile", "list_records", {
    "base_id": "appXXXXXXXXXXXXXX",
    "table_name": "Tasks",
    "filter_formula": "AND({Status}='Active', {Priority}='High')",
    "sort": [{"field": "Due Date", "direction": "asc"}],
    "max_records": 50
})

# Create a new record
result = execute("airtable", "myprofile", "create_record", {
    "base_id": "appXXXXXXXXXXXXXX",
    "table_name": "Tasks",
    "fields": {
        "Name": "New Task",
        "Status": "Todo",
        "Priority": "High"
    }
})

# Batch create records
result = execute("airtable", "myprofile", "create_records", {
    "base_id": "appXXXXXXXXXXXXXX",
    "table_name": "Contacts",
    "records": [
        {"fields": {"Name": "Alice", "Email": "alice@example.com"}},
        {"fields": {"Name": "Bob", "Email": "bob@example.com"}}
    ]
})
```

---

## Amplitude Controller

### Overview

Amplitude is a product analytics platform that helps teams understand user behavior. The Amplitude controller enables you to:

- Track events and user actions
- Identify and update user properties
- Batch upload events at high volume
- Export raw event data
- Query event segmentation and retention metrics
- Analyze funnels

**Use Cases:** Product analytics, user behavior tracking, A/B testing analysis, conversion funnel analysis, retention reporting.

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `AMPLITUDE_API_KEY` | Amplitude API Key |
| `AMPLITUDE_SECRET_KEY` | Amplitude Secret Key (for Export/Dashboard APIs) |

**How to get credentials:**
1. Log in to [Amplitude](https://amplitude.com)
2. Go to Settings > Projects > [Your Project]
3. Copy the API Key and Secret Key

**Required Permissions:**
- Track/Identify/Batch: API Key only (HTTP API)
- Export/User Activity/Queries: API Key + Secret Key (Basic Auth)

### Profile Configuration

```json
{
    "api_key_env": "AMPLITUDE_API_KEY",
    "secret_key_env": "AMPLITUDE_SECRET_KEY",
    "timeout": 60
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `track` | Track events | `events` (array with `user_id`/`device_id`, `event_type`) | Event properties, user properties, platform info |
| `identify` | Update user properties | `user_id` or `device_id`, `user_properties` | - |
| `batch` | Batch upload events (high volume) | `events` | `options` |
| `export` | Export raw event data | `start` (YYYYMMDDTHH), `end` (YYYYMMDDTHH) | - |
| `get_user_activity` | Get user's event history | `user_id` | `offset`, `limit` |
| `query_events` | Query event segmentation | `event_type`, `start` (YYYYMMDD), `end` (YYYYMMDD) | `interval`, `group_by` |
| `get_retention` | Get retention analysis | `start` (YYYYMMDD), `end` (YYYYMMDD) | `retention_type`, `se`, `re`, `rm`, `rb` |
| `get_funnel` | Get funnel analysis | `funnel_id`, `start` (YYYYMMDD), `end` (YYYYMMDD) | `mode`, `n`, `cs`, `group_by` |

### Usage Example

```python
from tinyhive.controller import execute

# Track a single event
result = execute("amplitude", "myprofile", "track", {
    "events": [{
        "user_id": "user_12345",
        "event_type": "Purchase Completed",
        "event_properties": {
            "product_id": "SKU-001",
            "price": 29.99,
            "currency": "USD"
        },
        "user_properties": {
            "$set": {"lifetime_value": 150.00}
        }
    }]
})

# Identify user properties
result = execute("amplitude", "myprofile", "identify", {
    "user_id": "user_12345",
    "user_properties": {
        "$set": {"plan": "premium", "company": "Acme Inc"},
        "$add": {"login_count": 1}
    }
})

# Export events for a time range
result = execute("amplitude", "myprofile", "export", {
    "start": "20240101T00",
    "end": "20240102T00"
})

# Query event counts
result = execute("amplitude", "myprofile", "query_events", {
    "event_type": "Page View",
    "start": "20240101",
    "end": "20240131",
    "interval": 1,
    "group_by": ["platform"]
})
```

---

## Anthropic Controller

### Overview

Anthropic provides Claude, a family of AI assistants. The Anthropic controller enables you to:

- Create chat completions with Claude models
- Stream responses for real-time output
- Count tokens before sending requests
- Use tools/function calling
- Process images (vision capabilities)
- List available models

**Use Cases:** AI-powered chat applications, content generation, code assistance, document analysis, image understanding.

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API Key |

**How to get credentials:**
1. Sign up at [Anthropic Console](https://console.anthropic.com)
2. Navigate to API Keys
3. Create a new API key

### Profile Configuration

```json
{
    "api_key_env": "ANTHROPIC_API_KEY",
    "default_model": "claude-sonnet-4-20250514",
    "default_max_tokens": 1024
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `create_message` | Create a chat completion | `messages` | `model`, `max_tokens`, `temperature`, `system`, `stop_sequences`, `tools`, `tool_choice`, `top_p`, `top_k`, `metadata` |
| `create_message_stream` | Create streaming completion | `messages` | Same as create_message |
| `count_tokens` | Count tokens in messages | `messages` | `model`, `system`, `tools` |
| `list_models` | List available models | - | `limit`, `before_id`, `after_id` |

### Usage Example

```python
from tinyhive.controller import execute

# Simple message
result = execute("anthropic", "myprofile", "create_message", {
    "messages": [
        {"role": "user", "content": "Explain quantum computing in simple terms."}
    ],
    "max_tokens": 500
})
print(result["data"]["content"][0]["text"])

# With system prompt and temperature
result = execute("anthropic", "myprofile", "create_message", {
    "system": "You are a helpful coding assistant. Be concise.",
    "messages": [
        {"role": "user", "content": "Write a Python function to calculate fibonacci numbers."}
    ],
    "temperature": 0.7,
    "max_tokens": 1000
})

# Using tools/function calling
result = execute("anthropic", "myprofile", "create_message", {
    "messages": [
        {"role": "user", "content": "What's the weather in San Francisco?"}
    ],
    "tools": [{
        "name": "get_weather",
        "description": "Get current weather for a location",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"}
            },
            "required": ["location"]
        }
    }],
    "tool_choice": {"type": "auto"}
})

# Count tokens before sending
result = execute("anthropic", "myprofile", "count_tokens", {
    "messages": [
        {"role": "user", "content": "A very long message..."}
    ]
})
print(f"Input tokens: {result['data']['input_tokens']}")
```

---

## Asana Controller

### Overview

Asana is a work management platform for teams to organize and track work. The Asana controller enables you to:

- Manage workspaces and projects
- Create, update, and complete tasks
- Add comments to tasks
- List and filter tasks by project

**Use Cases:** Project management, task tracking, team collaboration, workflow automation.

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `ASANA_TOKEN` | Asana Personal Access Token |

**How to get credentials:**
1. Go to [Asana Developer Console](https://app.asana.com/0/developer-console)
2. Create a new Personal Access Token
3. Copy the token immediately (shown only once)

### Profile Configuration

```json
{
    "token_env": "ASANA_TOKEN"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_workspaces` | List all workspaces | - | `limit`, `offset` |
| `list_projects` | List projects in workspace | `workspace_gid` | `archived`, `limit`, `offset` |
| `get_project` | Get project details | `project_gid` | `opt_fields` |
| `list_tasks` | List tasks in project | `project_gid` | `completed_since`, `limit`, `offset`, `opt_fields` |
| `create_task` | Create a new task | `name`, (`workspace_gid` or `projects`) | `notes`, `due_on`, `assignee`, `projects`, `tags`, `parent` |
| `update_task` | Update task fields | `task_gid`, `fields` | - |
| `add_comment` | Add comment to task | `task_gid`, `text` | - |
| `complete_task` | Mark task complete | `task_gid` | - |

### Usage Example

```python
from tinyhive.controller import execute

# List workspaces
result = execute("asana", "myprofile", "list_workspaces", {})
workspace_gid = result["result"]["workspaces"][0]["gid"]

# List projects in workspace
result = execute("asana", "myprofile", "list_projects", {
    "workspace_gid": workspace_gid
})

# Create a new task
result = execute("asana", "myprofile", "create_task", {
    "workspace_gid": workspace_gid,
    "name": "Review Q4 Report",
    "notes": "Complete review and provide feedback",
    "due_on": "2024-12-15",
    "projects": ["1234567890123456"]
})
task_gid = result["result"]["gid"]

# Add a comment
result = execute("asana", "myprofile", "add_comment", {
    "task_gid": task_gid,
    "text": "Started working on this. Will complete by EOD."
})

# Complete the task
result = execute("asana", "myprofile", "complete_task", {
    "task_gid": task_gid
})
```

---

## Auth0 Controller

### Overview

Auth0 is an identity management platform providing authentication and authorization services. The Auth0 controller enables you to:

- Manage users (CRUD operations)
- Assign roles to users
- List and manage roles
- Query user authentication logs

**Use Cases:** User management, identity verification, access control, security auditing.

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `AUTH0_CLIENT_ID` | Auth0 M2M Application Client ID |
| `AUTH0_CLIENT_SECRET` | Auth0 M2M Application Client Secret |

**How to get credentials:**
1. Log in to [Auth0 Dashboard](https://manage.auth0.com)
2. Go to Applications > Create Application
3. Select "Machine to Machine Applications"
4. Authorize the Management API with required scopes

**Required Scopes:**
- `read:users`, `create:users`, `update:users`, `delete:users`
- `read:roles`, `create:role_members`
- `read:logs`

### Profile Configuration

```json
{
    "domain": "your-tenant.auth0.com",
    "client_id_env": "AUTH0_CLIENT_ID",
    "client_secret_env": "AUTH0_CLIENT_SECRET",
    "audience": "https://your-tenant.auth0.com/api/v2/",
    "default_connection": "Username-Password-Authentication"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_users` | List users in tenant | - | `per_page`, `page`, `search_engine`, `q` (Lucene query) |
| `get_user` | Get user by ID | `user_id` | - |
| `create_user` | Create a new user | `email` | `password`, `connection`, `name`, `nickname`, `email_verified`, `user_metadata`, `app_metadata` |
| `update_user` | Update user attributes | `user_id`, `fields` | - |
| `delete_user` | Delete a user | `user_id` | - |
| `assign_roles` | Assign roles to user | `user_id`, `role_ids` | - |
| `list_roles` | List all roles | - | `per_page`, `page`, `name_filter` |
| `get_user_logs` | Get user's auth logs | `user_id` | `per_page`, `page` |

### Usage Example

```python
from tinyhive.controller import execute

# List users
result = execute("auth0", "myprofile", "list_users", {
    "per_page": 50,
    "q": 'email:"*@example.com"'
})

# Create a new user
result = execute("auth0", "myprofile", "create_user", {
    "email": "newuser@example.com",
    "password": "SecureP@ssw0rd!",
    "name": "John Doe",
    "user_metadata": {"preferences": {"theme": "dark"}},
    "app_metadata": {"plan": "premium"}
})
user_id = result["data"]["user_id"]

# Assign roles
result = execute("auth0", "myprofile", "assign_roles", {
    "user_id": user_id,
    "role_ids": ["rol_XXXXXXXXXXXX", "rol_YYYYYYYYYYYY"]
})

# Get user's authentication logs
result = execute("auth0", "myprofile", "get_user_logs", {
    "user_id": user_id,
    "per_page": 20
})
```

---

## AWS Controller

### Overview

Amazon Web Services (AWS) provides cloud computing services. The AWS controller enables you to:

- Manage S3 buckets and objects
- List and describe EC2 instances
- Invoke Lambda functions
- Send SQS messages
- Publish to SNS topics

**Use Cases:** Cloud storage, serverless computing, message queuing, notification systems, infrastructure management.

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `AWS_ACCESS_KEY_ID` | AWS Access Key ID |
| `AWS_SECRET_ACCESS_KEY` | AWS Secret Access Key |
| `AWS_SESSION_TOKEN` | Session token (optional, for temporary credentials) |

**How to get credentials:**
1. Log in to [AWS Console](https://console.aws.amazon.com)
2. Go to IAM > Users > [Your User] > Security credentials
3. Create access keys

**Required IAM Permissions per Action:**
- `list_buckets`: `s3:ListAllMyBuckets`
- `upload_object`: `s3:PutObject`
- `download_object`: `s3:GetObject`
- `list_instances`: `ec2:DescribeInstances`
- `invoke_lambda`: `lambda:InvokeFunction`
- `send_sqs_message`: `sqs:SendMessage`
- `publish_sns`: `sns:Publish`

### Profile Configuration

```json
{
    "region": "us-east-1",
    "access_key_env": "AWS_ACCESS_KEY_ID",
    "secret_key_env": "AWS_SECRET_ACCESS_KEY",
    "session_token_env": "AWS_SESSION_TOKEN"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_buckets` | List all S3 buckets | - | - |
| `upload_object` | Upload to S3 | `bucket`, `key`, (`data` or `data_base64` or `local_path`) | `content_type` |
| `download_object` | Download from S3 | `bucket`, `key` | `local_path` |
| `list_instances` | List EC2 instances | - | `filters`, `instance_ids`, `max_results` |
| `invoke_lambda` | Invoke Lambda function | `function_name` | `payload`, `invocation_type`, `log_type`, `qualifier` |
| `send_sqs_message` | Send SQS message | `queue_url`, `message_body` | `delay_seconds`, `message_attributes`, `message_group_id`, `message_deduplication_id` |
| `publish_sns` | Publish to SNS | `message`, (`topic_arn` or `target_arn` or `phone_number`) | `subject`, `message_structure`, `message_attributes` |

### Usage Example

```python
from tinyhive.controller import execute

# List S3 buckets
result = execute("aws", "myprofile", "list_buckets", {})
print(result["result"]["buckets"])

# Upload a file to S3
result = execute("aws", "myprofile", "upload_object", {
    "bucket": "my-bucket",
    "key": "data/report.json",
    "data": '{"status": "complete"}',
    "content_type": "application/json"
})

# List running EC2 instances
result = execute("aws", "myprofile", "list_instances", {
    "filters": {
        "instance-state-name": "running",
        "tag:Environment": "production"
    }
})

# Invoke a Lambda function
result = execute("aws", "myprofile", "invoke_lambda", {
    "function_name": "my-function",
    "payload": {"action": "process", "id": 123},
    "invocation_type": "RequestResponse"
})

# Send an SQS message
result = execute("aws", "myprofile", "send_sqs_message", {
    "queue_url": "https://sqs.us-east-1.amazonaws.com/123456789/my-queue",
    "message_body": '{"task": "process_order", "order_id": "12345"}'
})

# Publish to SNS
result = execute("aws", "myprofile", "publish_sns", {
    "topic_arn": "arn:aws:sns:us-east-1:123456789:my-topic",
    "message": "Alert: Server CPU usage exceeded 90%",
    "subject": "CPU Alert"
})
```

---

## BigCommerce Controller

### Overview

BigCommerce is an e-commerce platform for online stores. The BigCommerce controller enables you to:

- Manage products (list, create, update)
- Manage orders (list, view, update status)
- List and search customers

**Use Cases:** E-commerce automation, inventory management, order processing, customer management.

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `BIGCOMMERCE_ACCESS_TOKEN` | BigCommerce Store API Access Token |

**How to get credentials:**
1. Log in to your BigCommerce store admin
2. Go to Settings > API > API Accounts
3. Create an API Account with required scopes
4. Copy the Access Token and Store Hash

**Required Scopes:**
- Products: read/write
- Orders: read/write
- Customers: read/write

### Profile Configuration

```json
{
    "store_hash": "your-store-hash",
    "access_token_env": "BIGCOMMERCE_ACCESS_TOKEN"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_products` | List catalog products | - | `limit`, `page`, `name`, `sku` |
| `get_product` | Get product details | `product_id` | - |
| `create_product` | Create a product | `name`, `type`, `price` | `weight`, `sku`, `description`, `categories` |
| `update_product` | Update product fields | `product_id`, `fields` | - |
| `list_orders` | List orders | - | `status_id`, `min_date_created`, `limit`, `page` |
| `get_order` | Get order details | `order_id` | - |
| `update_order_status` | Update order status | `order_id`, `status_id` | - |
| `list_customers` | List customers | - | `email`, `name`, `limit`, `page` |

**Order Status IDs:**
- 0: Incomplete, 1: Pending, 2: Shipped, 3: Partially Shipped
- 4: Refunded, 5: Cancelled, 6: Declined, 7: Awaiting Payment
- 8: Awaiting Pickup, 9: Awaiting Shipment, 10: Completed
- 11: Awaiting Fulfillment, 12: Manual Verification Required
- 13: Disputed, 14: Partially Refunded

### Usage Example

```python
from tinyhive.controller import execute

# List products
result = execute("bigcommerce", "myprofile", "list_products", {
    "limit": 50,
    "name": "T-Shirt"
})

# Create a new product
result = execute("bigcommerce", "myprofile", "create_product", {
    "name": "Premium Cotton T-Shirt",
    "type": "physical",
    "weight": 0.5,
    "price": 29.99,
    "sku": "TSHIRT-001",
    "description": "<p>High-quality cotton t-shirt</p>",
    "categories": [23, 45]
})

# List recent orders
result = execute("bigcommerce", "myprofile", "list_orders", {
    "status_id": 11,  # Awaiting Fulfillment
    "limit": 20
})

# Update order status to Shipped
result = execute("bigcommerce", "myprofile", "update_order_status", {
    "order_id": 12345,
    "status_id": 2  # Shipped
})

# Search customers by email
result = execute("bigcommerce", "myprofile", "list_customers", {
    "email": "customer@example.com"
})
```

---

## Bitbucket Controller

### Overview

Bitbucket is a Git repository hosting service by Atlassian. The Bitbucket controller enables you to:

- Manage repositories
- Create and manage pull requests
- List commits and view file contents
- Monitor pipeline builds

**Use Cases:** Code repository management, code review automation, CI/CD monitoring, source code access.

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `BITBUCKET_APP_PASSWORD` | Bitbucket App Password |
| `BITBUCKET_ACCESS_TOKEN` | OAuth2 Access Token (alternative) |

**How to get credentials:**
1. Go to Bitbucket > Personal settings > App passwords
2. Create a new App Password with required permissions
3. Store the password securely (shown only once)

**Required Permissions:**
- Repositories: Read
- Pull requests: Read, Write
- Pipelines: Read

### Profile Configuration

```json
{
    "username": "your-bitbucket-username",
    "token_env": "BITBUCKET_APP_PASSWORD",
    "default_workspace": "your-workspace"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_repos` | List repositories | - | `workspace`, `role`, `sort`, `page`, `pagelen` |
| `get_repo` | Get repository details | `repo_slug` | `workspace` |
| `list_pull_requests` | List PRs | `repo_slug` | `workspace`, `state`, `page`, `pagelen` |
| `create_pull_request` | Create a PR | `repo_slug`, `title`, `source_branch`, `dest_branch` | `workspace`, `description`, `close_source_branch`, `reviewers` |
| `get_pull_request` | Get PR details | `repo_slug`, `pr_id` | `workspace` |
| `list_commits` | List commits | `repo_slug` | `workspace`, `branch`, `path`, `page`, `pagelen` |
| `get_file` | Get file content | `repo_slug`, `path` | `workspace`, `commit` |
| `list_pipelines` | List pipelines | `repo_slug` | `workspace`, `page`, `pagelen`, `sort` |

### Usage Example

```python
from tinyhive.controller import execute

# List repositories
result = execute("bitbucket", "myprofile", "list_repos", {
    "role": "member",
    "sort": "-updated_on"
})

# List open pull requests
result = execute("bitbucket", "myprofile", "list_pull_requests", {
    "repo_slug": "my-project",
    "state": "OPEN"
})

# Create a pull request
result = execute("bitbucket", "myprofile", "create_pull_request", {
    "repo_slug": "my-project",
    "title": "Add new feature",
    "source_branch": "feature/new-feature",
    "dest_branch": "main",
    "description": "This PR adds the new feature as discussed."
})

# Get file content
result = execute("bitbucket", "myprofile", "get_file", {
    "repo_slug": "my-project",
    "path": "src/config.json",
    "commit": "main"
})

# List recent pipelines
result = execute("bitbucket", "myprofile", "list_pipelines", {
    "repo_slug": "my-project",
    "sort": "-created_on",
    "pagelen": 10
})
```

---

## Box Controller

### Overview

Box is a cloud content management and file sharing service. The Box controller enables you to:

- Browse and manage folders
- Upload and download files
- Search for files and folders
- Create shared links

**Use Cases:** Cloud file storage, document management, file sharing, content collaboration.

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `BOX_ACCESS_TOKEN` | Box OAuth2 Access Token |

**How to get credentials:**
1. Go to [Box Developer Console](https://app.box.com/developers/console)
2. Create a new Box App
3. Generate a Developer Token or configure OAuth2

**Required Scopes:**
- `base_explorer` or `root_readonly` - For read operations
- `base_upload` or `root_readwrite` - For write operations
- `item_share` - For creating shared links

### Profile Configuration

```json
{
    "token_env": "BOX_ACCESS_TOKEN",
    "default_folder_id": "0"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_folder` | List folder contents | - | `folder_id`, `limit`, `offset` |
| `get_file_info` | Get file details | `file_id` | - |
| `upload_file` | Upload a file | `file_content`, `file_name` | `folder_id`, `content_encoding` |
| `download_file` | Download a file | `file_id` | - |
| `delete_file` | Delete a file | `file_id` | - |
| `create_folder` | Create a folder | `name` | `parent_id` |
| `search` | Search files/folders | `query` | `type`, `limit` |
| `create_shared_link` | Create shared link | `file_id` | `access`, `permissions` |

### Usage Example

```python
from tinyhive.controller import execute

# List root folder contents
result = execute("box", "myprofile", "list_folder", {
    "folder_id": "0",
    "limit": 100
})

# Upload a file
result = execute("box", "myprofile", "upload_file", {
    "folder_id": "123456789",
    "file_name": "report.txt",
    "file_content": "This is the report content.",
    "content_encoding": "utf-8"
})
file_id = result["result"]["id"]

# Download a file
result = execute("box", "myprofile", "download_file", {
    "file_id": file_id
})
content = result["data"]

# Search for files
result = execute("box", "myprofile", "search", {
    "query": "quarterly report",
    "type": "file",
    "limit": 20
})

# Create a shared link
result = execute("box", "myprofile", "create_shared_link", {
    "file_id": file_id,
    "access": "open",
    "permissions": {"can_download": True}
})
print(result["result"]["url"])
```

---

## Calendly Controller

### Overview

Calendly is a scheduling automation platform. The Calendly controller enables you to:

- Get current user information
- List and manage event types
- View and cancel scheduled events
- Manage invitees
- List webhook subscriptions

**Use Cases:** Meeting scheduling, appointment booking, calendar integration, scheduling automation.

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `CALENDLY_TOKEN` | Calendly Personal Access Token |

**How to get credentials:**
1. Log in to [Calendly](https://calendly.com)
2. Go to Integrations > API & Webhooks
3. Generate a Personal Access Token

### Profile Configuration

```json
{
    "token_env": "CALENDLY_TOKEN"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `get_current_user` | Get authenticated user info | - | - |
| `list_event_types` | List event types | `user_uri` | `active`, `count`, `page_token`, `sort` |
| `list_events` | List scheduled events | `user_uri` | `min_start_time`, `max_start_time`, `status`, `count`, `page_token`, `sort`, `invitee_email` |
| `get_event` | Get event details | `event_uuid` | - |
| `cancel_event` | Cancel an event | `event_uuid` | `reason` |
| `list_invitees` | List event invitees | `event_uuid` | `count`, `page_token`, `sort`, `status`, `email` |
| `get_invitee` | Get invitee details | `invitee_uuid` | - |
| `list_webhooks` | List webhook subscriptions | `organization_uri`, `scope` | `user_uri`, `count`, `page_token`, `sort` |

### Usage Example

```python
from tinyhive.controller import execute

# Get current user
result = execute("calendly", "myprofile", "get_current_user", {})
user_uri = result["result"]["resource"]["uri"]

# List event types
result = execute("calendly", "myprofile", "list_event_types", {
    "user_uri": user_uri,
    "active": True
})

# List upcoming events
result = execute("calendly", "myprofile", "list_events", {
    "user_uri": user_uri,
    "min_start_time": "2024-01-01T00:00:00Z",
    "status": "active",
    "sort": "start_time:asc"
})

# Get event details
event_uuid = "abc123-def456"
result = execute("calendly", "myprofile", "get_event", {
    "event_uuid": event_uuid
})

# List invitees for an event
result = execute("calendly", "myprofile", "list_invitees", {
    "event_uuid": event_uuid
})

# Cancel an event
result = execute("calendly", "myprofile", "cancel_event", {
    "event_uuid": event_uuid,
    "reason": "Scheduling conflict"
})
```

---

## Common Patterns

### Error Handling

All controllers return a consistent response format:

```python
# Success
{"ok": True, "result": {...}}  # or "data" key

# Failure
{"ok": False, "error": "Error message"}
```

Always check the `ok` field before processing results:

```python
result = execute("controller", "profile", "action", params)
if result.get("ok"):
    # Process result["result"] or result["data"]
    pass
else:
    # Handle error
    print(f"Error: {result.get('error')}")
```

### Profile Management

Profiles are stored in `profiles/{name}.json`. Create separate profiles for different environments:

```
profiles/
  dev.json
  staging.json
  production.json
```

### Method IDs

Controllers use the format: `controller.{service}.{profile}.{action}`

Examples:
- `controller.airtable.production.list_records`
- `controller.aws.dev.upload_object`
- `controller.anthropic.main.create_message`
