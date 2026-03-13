# TinyHive Controllers Documentation - Batch 5

This document covers the following controllers:
- [Mixpanel](#mixpanel-controller)
- [Monday.com](#mondaycom-controller)
- [MongoDB Atlas](#mongodb-atlas-controller)
- [Netlify](#netlify-controller)
- [Notion](#notion-controller)
- [Okta](#okta-controller)
- [OpenAI](#openai-controller)
- [Oracle Cloud Infrastructure](#oracle-cloud-infrastructure-controller)
- [PagerDuty](#pagerduty-controller)
- [PayPal](#paypal-controller)

---

## Mixpanel Controller

### Overview

Mixpanel is a product analytics platform that enables tracking user interactions, building funnels, analyzing user behavior, and measuring engagement. The Mixpanel controller provides integration for event tracking, user profile management, and data querying through Mixpanel's REST APIs.

**Common Use Cases:**
- Track user events and behavior across applications
- Manage user profiles and properties
- Query event data and analyze funnels
- Export raw event data for analysis
- Manage and analyze cohorts

### Authentication

Mixpanel uses two authentication methods:
- **Project Token**: For ingestion operations (tracking events and profile updates)
- **Service Account**: For query operations (requires Basic Auth with username/secret)

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `MIXPANEL_SERVICE_ACCOUNT_USERNAME` | Service account username for query operations |
| `MIXPANEL_SERVICE_ACCOUNT_SECRET` | Service account secret for query operations |

**How to Get Credentials:**
1. Log in to your Mixpanel account
2. Go to Project Settings > Access Security
3. For **Project Token**: Copy from Project Settings > Project Details
4. For **Service Account**: Go to Organization Settings > Service Accounts and create a new service account

### Profile Configuration

```json
{
  "project_id": "12345678",
  "project_token": "your_project_token",
  "service_account_username_env": "MIXPANEL_SERVICE_ACCOUNT_USERNAME",
  "service_account_secret_env": "MIXPANEL_SERVICE_ACCOUNT_SECRET"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `project_id` | Yes | Mixpanel project ID (required for queries) |
| `project_token` | Yes | Token for ingestion API (track/profile operations) |
| `service_account_username_env` | No | Environment variable for service account username |
| `service_account_secret_env` | No | Environment variable for service account secret |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `track` | Track a single event | `event`, `distinct_id` | `properties`, `time` |
| `track_batch` | Track multiple events in batch | `events` | - |
| `set_profile` | Set user profile properties (overwrites) | `distinct_id`, `properties` | - |
| `update_profile` | Update user profile with specific operation | `distinct_id`, `operation` | `properties` |
| `query_events` | Query event data using Insights API | `from_date`, `to_date` | `event`, `project_id` |
| `query_funnels` | Query funnel data | `funnel_id`, `from_date`, `to_date` | `project_id`, `unit` |
| `export_events` | Export raw event data (JSONL) | `from_date`, `to_date` | `event`, `project_id`, `limit` |
| `list_cohorts` | List all cohorts in the project | - | `project_id` |

### Usage Example

```python
from tinyhive import ControllerDispatch

dispatch = ControllerDispatch()

# Track a single event
result = dispatch.execute(
    "controller.mixpanel.production.track",
    {
        "event": "Purchase Completed",
        "distinct_id": "user_123",
        "properties": {
            "product_id": "sku_456",
            "price": 29.99,
            "currency": "USD"
        }
    }
)

# Track multiple events in batch
result = dispatch.execute(
    "controller.mixpanel.production.track_batch",
    {
        "events": [
            {"event": "Page View", "distinct_id": "user_123", "properties": {"page": "/home"}},
            {"event": "Button Click", "distinct_id": "user_123", "properties": {"button": "signup"}}
        ]
    }
)

# Set user profile properties
result = dispatch.execute(
    "controller.mixpanel.production.set_profile",
    {
        "distinct_id": "user_123",
        "properties": {
            "$name": "John Doe",
            "$email": "john@example.com",
            "plan": "premium"
        }
    }
)

# Query event data
result = dispatch.execute(
    "controller.mixpanel.production.query_events",
    {
        "from_date": "2024-01-01",
        "to_date": "2024-01-31",
        "event": "Purchase Completed"
    }
)

# Export raw events
result = dispatch.execute(
    "controller.mixpanel.production.export_events",
    {
        "from_date": "2024-01-01",
        "to_date": "2024-01-07",
        "limit": 1000
    }
)
```

---

## Monday.com Controller

### Overview

Monday.com is a work operating system that enables teams to build workflow apps for project management, CRM, software development, and more. The Monday controller provides integration for managing boards, items, groups, and updates through Monday.com's GraphQL API.

**Common Use Cases:**
- Create and manage project boards
- Add, update, and track work items
- Organize items into groups
- Add comments and updates to items
- Build automated workflows

### Authentication

Monday.com uses API key authentication.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `MONDAY_API_KEY` | Monday.com API key |

**How to Get Credentials:**
1. Log in to Monday.com
2. Click your profile picture > Developers
3. Go to My Access Tokens
4. Click "Show" next to your API token (or create a new one)

### Profile Configuration

```json
{
  "api_key_env": "MONDAY_API_KEY"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `api_key_env` | No | Environment variable containing API key (default: `MONDAY_API_KEY`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_boards` | List accessible boards | - | `limit`, `page` |
| `get_board` | Get detailed board information | `board_id` | - |
| `list_items` | List items in a board | `board_id` | `limit` |
| `create_item` | Create a new item in a board | `board_id`, `item_name` | `group_id`, `column_values` |
| `update_item` | Update item column values | `board_id`, `item_id`, `column_values` | - |
| `delete_item` | Delete an item | `item_id` | - |
| `add_update` | Add a comment/update to an item | `item_id`, `body` | - |
| `create_group` | Create a new group in a board | `board_id`, `group_name` | - |

### Usage Example

```python
from tinyhive import ControllerDispatch

dispatch = ControllerDispatch()

# List all boards
result = dispatch.execute(
    "controller.monday.workspace.list_boards",
    {"limit": 25}
)

# Get board details with items
result = dispatch.execute(
    "controller.monday.workspace.get_board",
    {"board_id": "1234567890"}
)

# Create a new item
result = dispatch.execute(
    "controller.monday.workspace.create_item",
    {
        "board_id": "1234567890",
        "item_name": "New Feature Request",
        "group_id": "topics",
        "column_values": {
            "status": {"label": "Working on it"},
            "date": {"date": "2024-03-15"},
            "person": {"personsAndTeams": [{"id": 12345, "kind": "person"}]}
        }
    }
)

# Update an item's columns
result = dispatch.execute(
    "controller.monday.workspace.update_item",
    {
        "board_id": "1234567890",
        "item_id": "9876543210",
        "column_values": {
            "status": {"label": "Done"},
            "text": "Completed the implementation"
        }
    }
)

# Add a comment to an item
result = dispatch.execute(
    "controller.monday.workspace.add_update",
    {
        "item_id": "9876543210",
        "body": "Just finished the review. Looks good!"
    }
)

# Create a new group
result = dispatch.execute(
    "controller.monday.workspace.create_group",
    {
        "board_id": "1234567890",
        "group_name": "Q2 Tasks"
    }
)
```

---

## MongoDB Atlas Controller

### Overview

MongoDB Atlas is a fully managed cloud database service for MongoDB. The MongoDB Atlas controller provides integration with the Atlas Data API, enabling CRUD operations and aggregation pipelines through HTTP requests.

**Common Use Cases:**
- Perform CRUD operations on MongoDB collections
- Run aggregation pipelines for data analysis
- Query documents with filters and projections
- Batch insert and update operations
- Build serverless data-driven applications

### Authentication

MongoDB Atlas Data API uses API key authentication.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `MONGODB_API_KEY` | MongoDB Atlas Data API key |

**How to Get Credentials:**
1. Log in to MongoDB Atlas
2. Go to Data API in the left sidebar
3. Enable the Data API for your cluster
4. Create an API key with appropriate permissions
5. Copy the API key and store it securely

### Profile Configuration

```json
{
  "app_id": "data-xxxxx",
  "api_key_env": "MONGODB_API_KEY",
  "default_data_source": "Cluster0",
  "default_database": "mydb"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `app_id` | Yes | Your MongoDB Atlas Data API App ID |
| `api_key_env` | No | Environment variable for API key (default: `MONGODB_API_KEY`) |
| `default_data_source` | No | Default cluster name |
| `default_database` | No | Default database name |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `find_one` | Find a single document | `collection` | `dataSource`, `database`, `filter`, `projection` |
| `find` | Find multiple documents | `collection` | `dataSource`, `database`, `filter`, `projection`, `sort`, `limit`, `skip` |
| `insert_one` | Insert a single document | `collection`, `document` | `dataSource`, `database` |
| `insert_many` | Insert multiple documents | `collection`, `documents` | `dataSource`, `database` |
| `update_one` | Update a single document | `collection`, `filter`, `update` | `dataSource`, `database`, `upsert` |
| `update_many` | Update multiple documents | `collection`, `filter`, `update` | `dataSource`, `database` |
| `delete_one` | Delete a single document | `collection`, `filter` | `dataSource`, `database` |
| `delete_many` | Delete multiple documents | `collection`, `filter` | `dataSource`, `database` |
| `aggregate` | Run an aggregation pipeline | `collection`, `pipeline` | `dataSource`, `database` |

### Usage Example

```python
from tinyhive import ControllerDispatch

dispatch = ControllerDispatch()

# Find a single document
result = dispatch.execute(
    "controller.mongodb.production.find_one",
    {
        "collection": "users",
        "filter": {"email": "john@example.com"},
        "projection": {"_id": 1, "name": 1, "email": 1}
    }
)

# Find multiple documents with sorting and limit
result = dispatch.execute(
    "controller.mongodb.production.find",
    {
        "collection": "orders",
        "filter": {"status": "pending"},
        "sort": {"createdAt": -1},
        "limit": 10
    }
)

# Insert a document
result = dispatch.execute(
    "controller.mongodb.production.insert_one",
    {
        "collection": "products",
        "document": {
            "name": "Widget Pro",
            "price": 29.99,
            "category": "electronics",
            "inStock": True
        }
    }
)

# Update a document
result = dispatch.execute(
    "controller.mongodb.production.update_one",
    {
        "collection": "users",
        "filter": {"email": "john@example.com"},
        "update": {
            "$set": {"lastLogin": "2024-03-12T10:30:00Z"},
            "$inc": {"loginCount": 1}
        }
    }
)

# Run an aggregation pipeline
result = dispatch.execute(
    "controller.mongodb.production.aggregate",
    {
        "collection": "orders",
        "pipeline": [
            {"$match": {"status": "completed"}},
            {"$group": {
                "_id": "$customerId",
                "totalSpent": {"$sum": "$amount"},
                "orderCount": {"$sum": 1}
            }},
            {"$sort": {"totalSpent": -1}},
            {"$limit": 10}
        ]
    }
)
```

---

## Netlify Controller

### Overview

Netlify is a cloud platform for web developers that provides hosting, continuous deployment, serverless functions, and form handling. The Netlify controller enables management of sites, deploys, and forms through the Netlify API.

**Common Use Cases:**
- Manage website deployments
- List and monitor site status
- Trigger new deploys
- Access form submissions
- Monitor deployment history

### Authentication

Netlify uses personal access token authentication.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `NETLIFY_ACCESS_TOKEN` | Netlify personal access token |

**How to Get Credentials:**
1. Log in to Netlify
2. Go to User Settings > Applications
3. Under Personal Access Tokens, click "New access token"
4. Give it a description and click "Generate token"
5. Copy and save the token securely

### Profile Configuration

```json
{
  "site_id": "optional-default-site-id",
  "team_slug": "optional-team-slug"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `site_id` | No | Default site ID for operations |
| `team_slug` | No | Team slug for team-specific operations |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_sites` | List all sites | - | `filter`, `page`, `per_page` |
| `get_site` | Get site details | `site_id` (or profile default) | - |
| `list_deploys` | List deploys for a site | `site_id` (or profile default) | `page`, `per_page` |
| `get_deploy` | Get deploy details | `deploy_id` | - |
| `create_deploy` | Create a new deploy with file digests | `site_id`, `files` | `draft`, `branch`, `title` |
| `lock_deploy` | Lock a deploy to prevent auto-publishing | `deploy_id` | - |
| `list_forms` | List forms for a site | `site_id` (or profile default) | - |
| `list_submissions` | List form submissions | `form_id` | `page`, `per_page` |

### Usage Example

```python
from tinyhive import ControllerDispatch

dispatch = ControllerDispatch()

# List all sites
result = dispatch.execute(
    "controller.netlify.team.list_sites",
    {"filter": "owner", "per_page": 50}
)

# Get site details
result = dispatch.execute(
    "controller.netlify.team.get_site",
    {"site_id": "your-site-id"}
)

# List recent deploys
result = dispatch.execute(
    "controller.netlify.team.list_deploys",
    {
        "site_id": "your-site-id",
        "per_page": 10
    }
)

# Get deploy details
result = dispatch.execute(
    "controller.netlify.team.get_deploy",
    {"deploy_id": "deploy-id-here"}
)

# List forms and their submissions
result = dispatch.execute(
    "controller.netlify.team.list_forms",
    {"site_id": "your-site-id"}
)

# Get form submissions
result = dispatch.execute(
    "controller.netlify.team.list_submissions",
    {
        "form_id": "form-id-here",
        "per_page": 100
    }
)
```

---

## Notion Controller

### Overview

Notion is an all-in-one workspace for notes, documents, wikis, and databases. The Notion controller provides integration for managing pages, databases, blocks, and search through Notion's API.

**Common Use Cases:**
- Query and manage databases
- Create and update pages
- Append content blocks to pages
- Search across workspace
- Build automated documentation workflows

### Authentication

Notion uses internal integration tokens for authentication.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `NOTION_TOKEN` | Notion integration token |

**How to Get Credentials:**
1. Go to [Notion Integrations](https://www.notion.so/my-integrations)
2. Click "New integration"
3. Give it a name and select the workspace
4. Copy the "Internal Integration Token"
5. Share the pages/databases with your integration

### Profile Configuration

```json
{
  "token_env": "NOTION_TOKEN"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `token_env` | No | Environment variable for integration token (default: `NOTION_TOKEN`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `query_database` | Query a Notion database | `database_id` | `filter`, `sorts`, `page_size`, `start_cursor` |
| `list_databases` | List all accessible databases | - | `page_size`, `start_cursor` |
| `get_database` | Get database schema/metadata | `database_id` | - |
| `create_page` | Create a new page in a database | `database_id`, `properties` | `children`, `icon`, `cover` |
| `update_page` | Update page properties | `page_id` | `properties`, `archived`, `icon`, `cover` |
| `get_page` | Get a page by ID | `page_id` | - |
| `append_blocks` | Append blocks to a page | `page_id`, `children` | `after` |
| `search` | Search pages and databases | - | `query`, `filter`, `sort`, `page_size`, `start_cursor` |

### Usage Example

```python
from tinyhive import ControllerDispatch

dispatch = ControllerDispatch()

# Query a database with filters
result = dispatch.execute(
    "controller.notion.workspace.query_database",
    {
        "database_id": "your-database-id",
        "filter": {
            "property": "Status",
            "select": {"equals": "In Progress"}
        },
        "sorts": [
            {"property": "Due Date", "direction": "ascending"}
        ],
        "page_size": 50
    }
)

# Create a new page
result = dispatch.execute(
    "controller.notion.workspace.create_page",
    {
        "database_id": "your-database-id",
        "properties": {
            "Name": {
                "title": [{"text": {"content": "New Task"}}]
            },
            "Status": {
                "select": {"name": "To Do"}
            },
            "Priority": {
                "select": {"name": "High"}
            }
        },
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "Task description here."}}]
                }
            }
        ]
    }
)

# Update a page
result = dispatch.execute(
    "controller.notion.workspace.update_page",
    {
        "page_id": "page-id-here",
        "properties": {
            "Status": {"select": {"name": "Done"}}
        }
    }
)

# Append blocks to a page
result = dispatch.execute(
    "controller.notion.workspace.append_blocks",
    {
        "page_id": "page-id-here",
        "children": [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "New Section"}}]
                }
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"text": {"content": "First item"}}]
                }
            }
        ]
    }
)

# Search the workspace
result = dispatch.execute(
    "controller.notion.workspace.search",
    {
        "query": "project planning",
        "filter": {"value": "page", "property": "object"},
        "page_size": 20
    }
)
```

---

## Okta Controller

### Overview

Okta is an identity and access management platform providing SSO, MFA, and user lifecycle management. The Okta controller enables management of users, groups, and applications through the Okta API.

**Common Use Cases:**
- User provisioning and deprovisioning
- Group membership management
- Application assignment
- User profile updates
- Identity lifecycle automation

### Authentication

Okta uses API token authentication with the SSWS scheme.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `OKTA_API_TOKEN` | Okta API token |

**How to Get Credentials:**
1. Log in to your Okta Admin Console
2. Go to Security > API
3. Click "Create Token"
4. Give the token a name and click "Create Token"
5. Copy the token value (shown only once)

### Profile Configuration

```json
{
  "domain": "your-org.okta.com",
  "token_env": "OKTA_API_TOKEN"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `domain` | Yes | Your Okta domain (e.g., `your-org.okta.com`) |
| `token_env` | No | Environment variable for API token (default: `OKTA_API_TOKEN`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_users` | List users in Okta | - | `filter`, `search`, `limit` |
| `get_user` | Get user by ID | `user_id` | - |
| `create_user` | Create a new user | `profile` | `credentials`, `groupIds`, `activate` |
| `update_user` | Update user profile | `user_id`, `profile` | - |
| `deactivate_user` | Deactivate a user | `user_id` | `send_email` |
| `list_groups` | List groups | - | `filter`, `q`, `limit` |
| `add_user_to_group` | Add user to a group | `group_id`, `user_id` | - |
| `list_applications` | List applications | - | `filter`, `q`, `limit` |

### Usage Example

```python
from tinyhive import ControllerDispatch

dispatch = ControllerDispatch()

# List active users
result = dispatch.execute(
    "controller.okta.company.list_users",
    {
        "filter": 'status eq "ACTIVE"',
        "limit": 100
    }
)

# Search for users
result = dispatch.execute(
    "controller.okta.company.list_users",
    {
        "search": 'profile.department eq "Engineering"'
    }
)

# Create a new user
result = dispatch.execute(
    "controller.okta.company.create_user",
    {
        "profile": {
            "login": "jane.doe@example.com",
            "email": "jane.doe@example.com",
            "firstName": "Jane",
            "lastName": "Doe",
            "department": "Engineering"
        },
        "credentials": {
            "password": {"value": "TempPassword123!"}
        },
        "activate": True
    }
)

# Update user profile
result = dispatch.execute(
    "controller.okta.company.update_user",
    {
        "user_id": "00u1abcd1234",
        "profile": {
            "department": "Product",
            "title": "Senior Engineer"
        }
    }
)

# Add user to group
result = dispatch.execute(
    "controller.okta.company.add_user_to_group",
    {
        "group_id": "00g1abcd1234",
        "user_id": "00u1abcd1234"
    }
)

# Deactivate a user
result = dispatch.execute(
    "controller.okta.company.deactivate_user",
    {
        "user_id": "00u1abcd1234",
        "send_email": False
    }
)
```

---

## OpenAI Controller

### Overview

OpenAI provides AI models for text generation, embeddings, image generation, audio transcription, text-to-speech, and content moderation. The OpenAI controller integrates with OpenAI's API for these capabilities.

**Common Use Cases:**
- Generate text completions and chat responses
- Create text embeddings for search/similarity
- Generate images with DALL-E
- Transcribe audio with Whisper
- Generate speech from text
- Moderate content for policy violations

### Authentication

OpenAI uses Bearer token authentication.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |

**How to Get Credentials:**
1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Sign in and go to API Keys
3. Click "Create new secret key"
4. Copy and store the key securely

### Profile Configuration

```json
{
  "api_key_env": "OPENAI_API_KEY",
  "default_model": "gpt-4o",
  "default_embedding_model": "text-embedding-3-small",
  "default_image_model": "dall-e-3",
  "default_whisper_model": "whisper-1",
  "default_tts_model": "tts-1"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `api_key_env` | No | Environment variable for API key (default: `OPENAI_API_KEY`) |
| `default_model` | No | Default chat model (default: `gpt-4o`) |
| `default_embedding_model` | No | Default embedding model |
| `default_image_model` | No | Default image model |
| `default_whisper_model` | No | Default transcription model |
| `default_tts_model` | No | Default text-to-speech model |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `chat_completion` | Generate chat completion | `messages` | `model`, `temperature`, `max_tokens`, `top_p`, `frequency_penalty`, `presence_penalty`, `stop`, `user` |
| `create_embedding` | Generate text embeddings | `input` | `model`, `encoding_format`, `dimensions`, `user` |
| `create_image` | Generate images with DALL-E | `prompt` | `model`, `size`, `n`, `quality`, `style`, `response_format`, `user` |
| `transcribe_audio` | Transcribe audio with Whisper | `file_path` | `model`, `language`, `prompt`, `response_format`, `temperature` |
| `text_to_speech` | Generate speech from text | `input`, `voice` | `model`, `response_format`, `speed`, `output_path` |
| `list_models` | List available models | - | `filter_prefix` |
| `moderate` | Check content for policy violations | `input` | `model` |

### Usage Example

```python
from tinyhive import ControllerDispatch

dispatch = ControllerDispatch()

# Chat completion
result = dispatch.execute(
    "controller.openai.default.chat_completion",
    {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Explain quantum computing in simple terms."}
        ],
        "model": "gpt-4o",
        "temperature": 0.7,
        "max_tokens": 500
    }
)

# Generate embeddings
result = dispatch.execute(
    "controller.openai.default.create_embedding",
    {
        "input": "The quick brown fox jumps over the lazy dog.",
        "model": "text-embedding-3-small"
    }
)

# Generate an image
result = dispatch.execute(
    "controller.openai.default.create_image",
    {
        "prompt": "A futuristic city at sunset with flying cars",
        "model": "dall-e-3",
        "size": "1024x1024",
        "quality": "hd"
    }
)

# Transcribe audio
result = dispatch.execute(
    "controller.openai.default.transcribe_audio",
    {
        "file_path": "/path/to/audio.mp3",
        "language": "en"
    }
)

# Text to speech
result = dispatch.execute(
    "controller.openai.default.text_to_speech",
    {
        "input": "Welcome to our application!",
        "voice": "nova",
        "output_path": "/path/to/output.mp3"
    }
)

# Content moderation
result = dispatch.execute(
    "controller.openai.default.moderate",
    {
        "input": "Text to check for policy violations"
    }
)
```

---

## Oracle Cloud Infrastructure Controller

### Overview

Oracle Cloud Infrastructure (OCI) is a cloud computing platform offering compute, storage, database, and other cloud services. The OCI controller provides integration for managing compute instances, object storage, databases, and compartments.

**Common Use Cases:**
- Manage compute instances (list, start, stop)
- Access object storage buckets and objects
- Query autonomous databases
- Manage compartment hierarchy
- Automate infrastructure operations

### Authentication

OCI uses RSA-SHA256 request signing with API keys.

**Required Configuration:**
- OCI API key pair (PEM format)
- User and tenancy OCIDs
- Key fingerprint

**How to Get Credentials:**
1. Log in to OCI Console
2. Go to User Settings > API Keys
3. Click "Add API Key"
4. Choose to generate or upload a key pair
5. Download the private key file
6. Note the fingerprint, tenancy OCID, and user OCID

**Dependencies:**
- `cryptography` library: `pip install cryptography`

### Profile Configuration

```json
{
  "tenancy_ocid": "ocid1.tenancy.oc1...",
  "user_ocid": "ocid1.user.oc1...",
  "fingerprint": "aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99",
  "private_key_path": "/path/to/oci_api_key.pem",
  "region": "us-ashburn-1",
  "compartment_ocid": "ocid1.compartment.oc1..."
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `tenancy_ocid` | Yes | Your tenancy OCID |
| `user_ocid` | Yes | Your user OCID |
| `fingerprint` | Yes | API key fingerprint |
| `private_key_path` | Yes | Path to PEM private key file |
| `region` | Yes | OCI region identifier |
| `compartment_ocid` | No | Default compartment OCID |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_instances` | List compute instances | - | `compartment_id`, `availability_domain`, `display_name`, `lifecycle_state`, `limit` |
| `get_instance` | Get instance details | `instance_id` | - |
| `start_instance` | Start a stopped instance | `instance_id` | - |
| `stop_instance` | Stop a running instance | `instance_id` | `force` |
| `list_buckets` | List object storage buckets | `namespace` | `compartment_id`, `limit` |
| `list_objects` | List objects in a bucket | `namespace`, `bucket_name` | `prefix`, `delimiter`, `start`, `limit`, `fields` |
| `list_databases` | List autonomous databases | - | `compartment_id`, `display_name`, `db_workload`, `lifecycle_state`, `limit` |
| `list_compartments` | List compartments | - | `compartment_id`, `access_level`, `compartment_id_in_subtree`, `lifecycle_state`, `limit` |

### Usage Example

```python
from tinyhive import ControllerDispatch

dispatch = ControllerDispatch()

# List running instances
result = dispatch.execute(
    "controller.oracle.production.list_instances",
    {
        "lifecycle_state": "RUNNING",
        "limit": 50
    }
)

# Get instance details
result = dispatch.execute(
    "controller.oracle.production.get_instance",
    {"instance_id": "ocid1.instance.oc1.iad..."}
)

# Start an instance
result = dispatch.execute(
    "controller.oracle.production.start_instance",
    {"instance_id": "ocid1.instance.oc1.iad..."}
)

# Stop an instance
result = dispatch.execute(
    "controller.oracle.production.stop_instance",
    {
        "instance_id": "ocid1.instance.oc1.iad...",
        "force": False
    }
)

# List buckets
result = dispatch.execute(
    "controller.oracle.production.list_buckets",
    {"namespace": "my-namespace"}
)

# List objects in a bucket
result = dispatch.execute(
    "controller.oracle.production.list_objects",
    {
        "namespace": "my-namespace",
        "bucket_name": "my-bucket",
        "prefix": "logs/",
        "limit": 100
    }
)

# List autonomous databases
result = dispatch.execute(
    "controller.oracle.production.list_databases",
    {"lifecycle_state": "AVAILABLE"}
)
```

---

## PagerDuty Controller

### Overview

PagerDuty is an incident management platform for alerting, on-call scheduling, and incident response. The PagerDuty controller enables incident management, service monitoring, and event triggering through the PagerDuty APIs.

**Common Use Cases:**
- Create and manage incidents
- Query on-call schedules
- Send alert events
- List and manage services
- Automate incident response workflows

### Authentication

PagerDuty uses API token authentication.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `PAGERDUTY_TOKEN` | PagerDuty REST API token |

**How to Get Credentials:**
1. Log in to PagerDuty
2. Go to Integrations > API Access Keys
3. Click "Create New API Key"
4. Choose "General Access API Key" for full access
5. Copy and store the key securely

### Profile Configuration

```json
{
  "token_env": "PAGERDUTY_TOKEN",
  "default_from_email": "user@example.com",
  "default_service_id": "PXXXXXX"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `token_env` | No | Environment variable for API token (default: `PAGERDUTY_TOKEN`) |
| `default_from_email` | No | Default email for incident operations |
| `default_service_id` | No | Default service ID |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `create_incident` | Create a new incident | `title`, `service_id`, `from_email` | `urgency`, `body`, `escalation_policy_id`, `incident_key`, `priority_id` |
| `list_incidents` | List incidents | - | `statuses`, `urgencies`, `since`, `until`, `service_ids`, `user_ids`, `time_zone`, `sort_by`, `limit`, `offset` |
| `get_incident` | Get incident details | `incident_id` | - |
| `update_incident` | Update incident (ack/resolve) | `incident_id`, `status`, `from_email` | `resolution` |
| `list_services` | List services | - | `query`, `team_ids`, `time_zone`, `sort_by`, `limit`, `offset`, `include` |
| `list_oncalls` | List on-call users | - | `schedule_ids`, `user_ids`, `escalation_policy_ids`, `since`, `until`, `time_zone`, `earliest`, `limit`, `offset`, `include` |
| `create_event` | Send Events API v2 event | `routing_key`, `event_action` | `summary`, `severity`, `source`, `dedup_key`, `timestamp`, `component`, `group`, `class_type`, `custom_details`, `images`, `links` |
| `list_users` | List users | - | `query`, `team_ids`, `include`, `limit`, `offset` |

### Usage Example

```python
from tinyhive import ControllerDispatch

dispatch = ControllerDispatch()

# Create an incident
result = dispatch.execute(
    "controller.pagerduty.ops.create_incident",
    {
        "title": "High CPU Usage on Production Server",
        "service_id": "PABCDEF",
        "from_email": "ops@example.com",
        "urgency": "high",
        "body": "CPU usage has exceeded 95% for more than 10 minutes."
    }
)

# List active incidents
result = dispatch.execute(
    "controller.pagerduty.ops.list_incidents",
    {
        "statuses": ["triggered", "acknowledged"],
        "urgencies": ["high"],
        "limit": 25
    }
)

# Acknowledge an incident
result = dispatch.execute(
    "controller.pagerduty.ops.update_incident",
    {
        "incident_id": "P1234567",
        "status": "acknowledged",
        "from_email": "ops@example.com"
    }
)

# Resolve an incident
result = dispatch.execute(
    "controller.pagerduty.ops.update_incident",
    {
        "incident_id": "P1234567",
        "status": "resolved",
        "from_email": "ops@example.com",
        "resolution": "Scaled up the server and load balanced."
    }
)

# List who's on call
result = dispatch.execute(
    "controller.pagerduty.ops.list_oncalls",
    {
        "escalation_policy_ids": ["PXYZ123"],
        "earliest": True
    }
)

# Send an Events API alert
result = dispatch.execute(
    "controller.pagerduty.ops.create_event",
    {
        "routing_key": "your-integration-routing-key",
        "event_action": "trigger",
        "summary": "Disk space critically low on db-01",
        "severity": "critical",
        "source": "monitoring-system",
        "component": "database",
        "custom_details": {
            "disk_used": "98%",
            "mount_point": "/data"
        }
    }
)
```

---

## PayPal Controller

### Overview

PayPal is a global payment platform enabling online payments, money transfers, and invoicing. The PayPal controller provides integration for payment processing, payouts, invoicing, and transaction management through PayPal's REST APIs.

**Common Use Cases:**
- Create and capture payment orders
- Send payouts to individuals
- Create and send invoices
- List and analyze transactions
- Process refunds

### Authentication

PayPal uses OAuth 2.0 client credentials authentication.

**Required Environment Variables:**
| Variable | Description |
|----------|-------------|
| `PAYPAL_CLIENT_ID` | PayPal REST API client ID |
| `PAYPAL_CLIENT_SECRET` | PayPal REST API client secret |

**How to Get Credentials:**
1. Go to [PayPal Developer Dashboard](https://developer.paypal.com/)
2. Navigate to Apps & Credentials
3. Create a new app or select an existing one
4. Copy the Client ID and Secret for your environment (Sandbox or Live)

### Profile Configuration

```json
{
  "environment": "sandbox",
  "client_id_env": "PAYPAL_CLIENT_ID",
  "client_secret_env": "PAYPAL_CLIENT_SECRET",
  "default_currency": "USD"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `environment` | No | `sandbox` or `production`/`live` (default: `sandbox`) |
| `client_id_env` | No | Environment variable for client ID (default: `PAYPAL_CLIENT_ID`) |
| `client_secret_env` | No | Environment variable for client secret (default: `PAYPAL_CLIENT_SECRET`) |
| `default_currency` | No | Default currency code (default: `USD`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `create_order` | Create a payment order | `purchase_units` | `intent`, `return_url`, `cancel_url` |
| `capture_order` | Capture an approved order | `order_id` | - |
| `get_order` | Get order details | `order_id` | - |
| `create_payout` | Send money (payout) | `receiver`, `amount` | `recipient_type`, `currency`, `note`, `sender_batch_id`, `email_subject`, `email_message` |
| `list_transactions` | List transactions | `start_date`, `end_date` | `transaction_type`, `transaction_status`, `page_size`, `page` |
| `create_invoice` | Create an invoice | `items`, `recipient_email` | `invoice_number`, `note`, `terms`, `due_date`, `currency` |
| `send_invoice` | Send an invoice | `invoice_id` | `subject`, `note`, `send_to_recipient`, `send_to_invoicer` |
| `refund_capture` | Refund a captured payment | `capture_id` | `amount`, `currency`, `note`, `invoice_id` |

### Usage Example

```python
from tinyhive import ControllerDispatch

dispatch = ControllerDispatch()

# Create a payment order
result = dispatch.execute(
    "controller.paypal.production.create_order",
    {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {"currency_code": "USD", "value": "99.99"},
                "description": "Premium Subscription"
            }
        ],
        "return_url": "https://example.com/success",
        "cancel_url": "https://example.com/cancel"
    }
)
# Returns order_id and approval_url

# Capture the order after customer approval
result = dispatch.execute(
    "controller.paypal.production.capture_order",
    {"order_id": "ORDER-ID-FROM-ABOVE"}
)

# Create a payout
result = dispatch.execute(
    "controller.paypal.production.create_payout",
    {
        "recipient_type": "EMAIL",
        "receiver": "recipient@example.com",
        "amount": "50.00",
        "currency": "USD",
        "note": "Payment for services rendered"
    }
)

# List transactions
result = dispatch.execute(
    "controller.paypal.production.list_transactions",
    {
        "start_date": "2024-01-01T00:00:00Z",
        "end_date": "2024-01-31T23:59:59Z",
        "page_size": 100
    }
)

# Create an invoice
result = dispatch.execute(
    "controller.paypal.production.create_invoice",
    {
        "recipient_email": "customer@example.com",
        "items": [
            {
                "name": "Consulting Services",
                "quantity": 10,
                "unit_amount": {"currency_code": "USD", "value": "150.00"},
                "description": "Technical consulting - 10 hours"
            }
        ],
        "note": "Thank you for your business!",
        "due_date": "2024-04-15"
    }
)

# Send the invoice
result = dispatch.execute(
    "controller.paypal.production.send_invoice",
    {
        "invoice_id": "INV2-XXXX-YYYY-ZZZZ",
        "subject": "Invoice from Acme Corp",
        "note": "Payment due within 30 days"
    }
)

# Process a refund
result = dispatch.execute(
    "controller.paypal.production.refund_capture",
    {
        "capture_id": "CAPTURE-ID-HERE",
        "amount": "25.00",
        "currency": "USD",
        "note": "Partial refund for returned item"
    }
)
```

---

## Summary

This batch covers 10 controllers for popular services:

| Controller | Service Type | Key Features |
|------------|--------------|--------------|
| Mixpanel | Product Analytics | Event tracking, user profiles, funnels, cohorts |
| Monday.com | Work Management | Boards, items, groups, updates |
| MongoDB Atlas | Database | CRUD operations, aggregation pipelines |
| Netlify | Web Hosting | Sites, deploys, forms, submissions |
| Notion | Workspace | Pages, databases, blocks, search |
| Okta | Identity Management | Users, groups, applications |
| OpenAI | AI/ML | Chat, embeddings, images, audio, moderation |
| Oracle Cloud | Cloud Infrastructure | Compute, storage, databases, compartments |
| PagerDuty | Incident Management | Incidents, on-call, services, events |
| PayPal | Payments | Orders, payouts, invoices, refunds |

For profile setup and environment configuration, refer to each controller's specific documentation section above.
