# TinyHive Controllers - Batch 3

Documentation for Dropbox, Elasticsearch, Figma, Firebase, Freshdesk, GCP, GitHub, GitLab, Google, and Grafana controllers.

---

## Table of Contents

1. [Dropbox Controller](#dropbox-controller)
2. [Elasticsearch Controller](#elasticsearch-controller)
3. [Figma Controller](#figma-controller)
4. [Firebase Controller](#firebase-controller)
5. [Freshdesk Controller](#freshdesk-controller)
6. [GCP Controller](#gcp-controller)
7. [GitHub Controller](#github-controller)
8. [GitLab Controller](#gitlab-controller)
9. [Google Controller](#google-controller)
10. [Grafana Controller](#grafana-controller)

---

## Dropbox Controller

### Overview

The Dropbox controller provides integration with Dropbox API v2 for cloud file storage operations. Use cases include:

- Automated file backup and synchronization
- Document management workflows
- Sharing files programmatically
- Building file-based integrations

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `DROPBOX_ACCESS_TOKEN` | Dropbox OAuth2 access token |

**How to get credentials:**
1. Go to [Dropbox App Console](https://www.dropbox.com/developers/apps)
2. Create a new app or select an existing one
3. Generate an access token under the OAuth 2 section

**Required Permissions:**
- `files.metadata.read`
- `files.metadata.write`
- `files.content.read`
- `files.content.write`
- `sharing.write`

### Profile Configuration

```json
{
    "token_env": "DROPBOX_ACCESS_TOKEN",
    "timeout": 60
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_folder` | List contents of a folder | `path` (str, use "" for root) | `recursive` (bool), `limit` (int, max 2000) |
| `get_metadata` | Get metadata for a file or folder | `path` (str) | - |
| `upload_file` | Upload a file to Dropbox | `path` (str), `content` (str) | `mode` (str: add/overwrite/update), `content_encoding` (str: utf-8/base64), `autorename` (bool) |
| `download_file` | Download a file from Dropbox | `path` (str) | - |
| `delete` | Delete a file or folder | `path` (str) | - |
| `create_folder` | Create a new folder | `path` (str) | `autorename` (bool) |
| `move` | Move a file or folder | `from_path` (str), `to_path` (str) | `autorename` (bool), `allow_ownership_transfer` (bool) |
| `create_shared_link` | Create a shared link for a file or folder | `path` (str) | - |

### Usage Example

```python
from tinyhive.controllers import dropbox_controller

# List files in root folder
result = dropbox_controller.execute("default", "list_folder", {
    "path": "",
    "recursive": False,
    "limit": 100
})

# Upload a file
result = dropbox_controller.execute("default", "upload_file", {
    "path": "/documents/report.txt",
    "content": "Monthly report content...",
    "mode": "overwrite"
})

# Download a file
result = dropbox_controller.execute("default", "download_file", {
    "path": "/documents/report.txt"
})

# Create a shared link
result = dropbox_controller.execute("default", "create_shared_link", {
    "path": "/documents/report.txt"
})
```

---

## Elasticsearch Controller

### Overview

The Elasticsearch controller provides REST API operations for search and analytics. Supports both Elastic Cloud (API key auth) and self-hosted clusters (Basic auth). Use cases include:

- Full-text search implementation
- Log and event data analysis
- Real-time data indexing
- Aggregations and analytics

### Authentication

**Option 1: Elastic Cloud (API Key)**

| Environment Variable | Description |
|---------------------|-------------|
| `ELASTICSEARCH_API_KEY` | API key (Base64 encoded id:api_key) |

**Option 2: Self-hosted (Basic Auth)**

| Environment Variable | Description |
|---------------------|-------------|
| `ELASTICSEARCH_USERNAME` | Cluster username |
| `ELASTICSEARCH_PASSWORD` | Cluster password |

**How to get credentials:**
1. **Elastic Cloud:** Go to Elastic Cloud console > Deployment > Security > Create API Key
2. **Self-hosted:** Use your cluster admin credentials or create a dedicated user

### Profile Configuration

**Elastic Cloud:**
```json
{
    "host": "https://my-cluster.es.us-east-1.aws.elastic.cloud:9243",
    "api_key_env": "ELASTICSEARCH_API_KEY"
}
```

**Self-hosted with Basic Auth:**
```json
{
    "host": "https://localhost:9200",
    "username_env": "ELASTICSEARCH_USERNAME",
    "password_env": "ELASTICSEARCH_PASSWORD",
    "verify_ssl": false
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `search` | Search documents in an index | `index` (str) | `query` (dict), `size` (int), `from` (int), `sort` (list), `_source` (list), `aggs` (dict) |
| `index_doc` | Index (create/replace) a document | `index` (str), `document` (dict) | `doc_id` (str), `refresh` (str: true/false/wait_for) |
| `get_doc` | Get a document by ID | `index` (str), `doc_id` (str) | `_source` (list) |
| `update_doc` | Partial update a document | `index` (str), `doc_id` (str), `doc` (dict) | `refresh` (str), `retry_on_conflict` (int) |
| `delete_doc` | Delete a document by ID | `index` (str), `doc_id` (str) | `refresh` (str) |
| `bulk` | Perform bulk operations | `operations` (list) | `refresh` (str) |
| `create_index` | Create an index | `index` (str) | `mappings` (dict), `settings` (dict) |
| `delete_index` | Delete an index | `index` (str) | - |

### Usage Example

```python
from tinyhive.controllers import elasticsearch_controller

# Create an index with mappings
result = elasticsearch_controller.execute("cloud", "create_index", {
    "index": "products",
    "mappings": {
        "properties": {
            "name": {"type": "text"},
            "price": {"type": "float"},
            "category": {"type": "keyword"}
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 1
    }
})

# Index a document
result = elasticsearch_controller.execute("cloud", "index_doc", {
    "index": "products",
    "doc_id": "1",
    "document": {
        "name": "Widget Pro",
        "price": 29.99,
        "category": "electronics"
    },
    "refresh": "wait_for"
})

# Search documents
result = elasticsearch_controller.execute("cloud", "search", {
    "index": "products",
    "query": {
        "bool": {
            "must": [{"match": {"category": "electronics"}}],
            "filter": [{"range": {"price": {"lte": 50}}}]
        }
    },
    "size": 20,
    "sort": [{"price": "asc"}]
})

# Bulk operations
result = elasticsearch_controller.execute("cloud", "bulk", {
    "operations": [
        {"action": "index", "index": "products", "doc_id": "2", "document": {"name": "Gadget X", "price": 19.99}},
        {"action": "update", "index": "products", "doc_id": "1", "document": {"price": 24.99}},
        {"action": "delete", "index": "products", "doc_id": "3"}
    ],
    "refresh": "true"
})
```

---

## Figma Controller

### Overview

The Figma controller integrates with the Figma REST API for design collaboration. Use cases include:

- Extracting design assets and images
- Reading design file structure
- Automating design reviews with comments
- Syncing design components with code

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `FIGMA_ACCESS_TOKEN` | Figma personal access token |

**How to get credentials:**
1. Go to Figma > Account Settings > Personal Access Tokens
2. Generate a new token with required scopes

**Required Scopes:**
- `files:read` - For get_file, get_file_nodes, get_images
- `file_comments:read` - For get_comments
- `file_comments:write` - For post_comment
- `projects:read` - For list_projects, list_project_files
- `library_read` - For get_team_components

### Profile Configuration

```json
{
    "token_env": "FIGMA_ACCESS_TOKEN"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `get_file` | Get a Figma file's data | `file_key` (str) | `node_ids` (str), `depth` (int), `geometry` (str), `plugin_data` (str), `branch_data` (bool) |
| `get_file_nodes` | Get specific nodes from a file | `file_key` (str), `node_ids` (str) | `depth` (int), `geometry` (str), `plugin_data` (str) |
| `get_images` | Export images from a file | `file_key` (str), `node_ids` (str) | `format` (str: jpg/png/svg/pdf), `scale` (float: 0.01-4), `svg_include_id` (bool), `svg_simplify_stroke` (bool), `use_absolute_bounds` (bool), `version` (str) |
| `get_comments` | Get comments on a file | `file_key` (str) | `as_md` (bool) |
| `post_comment` | Post a comment on a file | `file_key` (str), `message` (str) | `client_meta` (dict), `comment_id` (str) |
| `list_projects` | List projects for a team | `team_id` (str) | - |
| `list_project_files` | List files in a project | `project_id` (str) | `branch_data` (bool) |
| `get_team_components` | Get published components for a team | `team_id` (str) | `page_size` (int, max 100), `cursor` (str) |

### Usage Example

```python
from tinyhive.controllers import figma_controller

# Get file data (file_key from Figma URL: figma.com/file/{file_key}/...)
result = figma_controller.execute("default", "get_file", {
    "file_key": "abc123XYZ",
    "depth": 2
})

# Export images from specific nodes
result = figma_controller.execute("default", "get_images", {
    "file_key": "abc123XYZ",
    "node_ids": "1:2,3:4,5:6",
    "format": "png",
    "scale": 2
})

# Post a comment on a design
result = figma_controller.execute("default", "post_comment", {
    "file_key": "abc123XYZ",
    "message": "This looks great! Ready for development.",
    "client_meta": {"x": 100, "y": 200}
})

# List team projects
result = figma_controller.execute("default", "list_projects", {
    "team_id": "1234567890"
})
```

---

## Firebase Controller

### Overview

The Firebase controller provides integration with Firebase services including Firestore, Realtime Database, Cloud Messaging (FCM), and Authentication. Use cases include:

- Serverless database operations (Firestore/RTDB)
- Push notification delivery
- User authentication management
- Real-time data synchronization

### Authentication

**Option 1: Service Account JSON (recommended for server-side)**

| File | Description |
|------|-------------|
| Service account JSON file | Download from Firebase Console > Project Settings > Service Accounts |

**Option 2: ID Token from environment**

| Environment Variable | Description |
|---------------------|-------------|
| `FIREBASE_ID_TOKEN` | Firebase ID token for client-side or testing |

**Required IAM Roles:**
- Firestore: `roles/datastore.user` or Firebase Firestore rules
- Realtime Database: Firebase RTDB rules
- FCM: `roles/cloudmessaging.messages.create`
- Auth: `roles/firebaseauth.admin`

**Dependencies:** `pip install cryptography` (for service account JWT signing)

### Profile Configuration

**Service Account:**
```json
{
    "project_id": "my-firebase-project",
    "service_account_path": "/path/to/service-account.json"
}
```

**ID Token:**
```json
{
    "project_id": "my-firebase-project",
    "token_env": "FIREBASE_ID_TOKEN"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `get_document` | Get a Firestore document by ID | `collection` (str), `document_id` (str) | - |
| `set_document` | Set/create a Firestore document | `collection` (str), `document_id` (str), `data` (dict) | `merge` (bool) |
| `query_collection` | Query a Firestore collection | `collection` (str) | `where` (list of [field, op, value]), `order_by` (list), `limit` (int) |
| `delete_document` | Delete a Firestore document | `collection` (str), `document_id` (str) | - |
| `get_rtdb` | Get data from Realtime Database | `path` (str) | `shallow` (bool), `order_by` (str), `limit_to_first` (int), `limit_to_last` (int) |
| `set_rtdb` | Set data in Realtime Database | `path` (str), `data` (any) | `method` (str: PUT/PATCH) |
| `send_fcm` | Send a push notification | `token` (str), `title` (str), `body` (str) | `data` (dict), `image` (str), `android` (dict), `apns` (dict), `webpush` (dict) |
| `list_users` | List Firebase Auth users | - | `max_results` (int, max 1000), `page_token` (str) |

### Usage Example

```python
from tinyhive.controllers import firebase_controller

# Set a Firestore document
result = firebase_controller.execute("default", "set_document", {
    "collection": "users",
    "document_id": "user123",
    "data": {
        "name": "John Doe",
        "email": "john@example.com",
        "created_at": "2024-01-15T10:30:00Z"
    },
    "merge": True
})

# Query a Firestore collection
result = firebase_controller.execute("default", "query_collection", {
    "collection": "orders",
    "where": [
        ["status", "EQUAL", "pending"],
        ["total", "GREATER_THAN", 100]
    ],
    "order_by": [["created_at", "DESCENDING"]],
    "limit": 50
})

# Send a push notification
result = firebase_controller.execute("default", "send_fcm", {
    "token": "device-fcm-token-here",
    "title": "Order Update",
    "body": "Your order has been shipped!",
    "data": {"order_id": "12345", "tracking_url": "https://..."}
})

# Get data from Realtime Database
result = firebase_controller.execute("default", "get_rtdb", {
    "path": "users/user123/settings",
    "shallow": False
})
```

---

## Freshdesk Controller

### Overview

The Freshdesk controller integrates with the Freshdesk helpdesk API for customer support operations. Use cases include:

- Ticket management automation
- Customer support workflows
- Contact and agent management
- Helpdesk reporting and analytics

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `FRESHDESK_API_KEY` | Freshdesk API key |

**How to get credentials:**
1. Log into Freshdesk as an admin
2. Go to Profile Settings > API Key
3. Copy your API key

**Required Permissions:**
- Tickets: Read/Write access
- Contacts: Read/Write access
- Agents: Read access

### Profile Configuration

```json
{
    "domain": "yourcompany.freshdesk.com",
    "api_key_env": "FRESHDESK_API_KEY"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_tickets` | List tickets with filtering | - | `filter` (str), `per_page` (int, max 100), `page` (int) |
| `get_ticket` | Get a single ticket by ID | `ticket_id` (int) | - |
| `create_ticket` | Create a new ticket | `subject` (str), `description` (str), `email` (str) | `priority` (int: 1-4), `status` (int: 2-5), `type` (str), `tags` (list), `cc_emails` (list), `custom_fields` (dict) |
| `update_ticket` | Update an existing ticket | `ticket_id` (int), `fields` (dict) | - |
| `add_reply` | Add a reply to a ticket | `ticket_id` (int), `body` (str) | `cc_emails` (list), `bcc_emails` (list) |
| `list_contacts` | List contacts | - | `email` (str), `phone` (str), `per_page` (int), `page` (int) |
| `create_contact` | Create a new contact | `name` (str), `email` (str) | `phone` (str), `mobile` (str), `twitter_id` (str), `company_id` (int), `description` (str), `job_title` (str), `custom_fields` (dict) |
| `list_agents` | List all agents | - | `email` (str), `per_page` (int), `page` (int) |

**Priority Values:** 1=Low, 2=Medium, 3=High, 4=Urgent

**Status Values:** 2=Open, 3=Pending, 4=Resolved, 5=Closed

### Usage Example

```python
from tinyhive.controllers import freshdesk_controller

# Create a new support ticket
result = freshdesk_controller.execute("default", "create_ticket", {
    "subject": "Cannot access my account",
    "description": "<p>I'm having trouble logging in since yesterday...</p>",
    "email": "customer@example.com",
    "priority": 2,
    "status": 2,
    "tags": ["login", "urgent"]
})

# List open tickets
result = freshdesk_controller.execute("default", "list_tickets", {
    "filter": "new_and_my_open",
    "per_page": 50
})

# Add a reply to a ticket
result = freshdesk_controller.execute("default", "add_reply", {
    "ticket_id": 12345,
    "body": "<p>Thank you for contacting us. We've reset your password...</p>",
    "cc_emails": ["manager@company.com"]
})

# Update ticket status to resolved
result = freshdesk_controller.execute("default", "update_ticket", {
    "ticket_id": 12345,
    "fields": {
        "status": 4,
        "priority": 1
    }
})
```

---

## GCP Controller

### Overview

The GCP controller provides integration with Google Cloud Platform services including Cloud Storage, Compute Engine, Cloud Functions, and Pub/Sub. Use cases include:

- Cloud storage operations (upload, download, list)
- Compute instance management
- Serverless function invocation
- Message queue publishing

### Authentication

**Option 1: Service Account JSON**

| File | Description |
|------|-------------|
| Service account JSON file | Download from GCP Console > IAM & Admin > Service Accounts |

**Option 2: Application Default Credentials (ADC)**

| Environment Variable | Description |
|---------------------|-------------|
| `GOOGLE_ACCESS_TOKEN` | Access token from `gcloud auth print-access-token` |

**Required IAM Roles:**
- `list_gcs_buckets`: `roles/storage.viewer`
- `upload_to_gcs`: `roles/storage.objectCreator`
- `download_from_gcs`: `roles/storage.objectViewer`
- `list_compute_instances`: `roles/compute.viewer`
- `invoke_cloud_function`: `roles/cloudfunctions.invoker`
- `publish_pubsub`: `roles/pubsub.publisher`

**Dependencies:** `pip install cryptography` (for service account JWT signing)

### Profile Configuration

**Service Account:**
```json
{
    "project_id": "my-gcp-project",
    "service_account_path": "/path/to/service-account.json",
    "default_region": "us-central1",
    "default_zone": "us-central1-a"
}
```

**Application Default Credentials:**
```json
{
    "project_id": "my-gcp-project",
    "use_adc": true,
    "token_env": "GOOGLE_ACCESS_TOKEN",
    "default_region": "us-central1",
    "default_zone": "us-central1-a"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_gcs_buckets` | List Cloud Storage buckets | - | `project_id` (str), `prefix` (str), `max_results` (int) |
| `upload_to_gcs` | Upload to Cloud Storage | `bucket` (str), `object_name` (str), and (`local_path` or `data`) | `content_type` (str) |
| `download_from_gcs` | Download from Cloud Storage | `bucket` (str), `object_name` (str) | `local_path` (str) |
| `list_compute_instances` | List Compute Engine instances | - | `project_id` (str), `zone` (str), `filter` (str), `max_results` (int) |
| `invoke_cloud_function` | Invoke a Cloud Function | `function_url` (str) | `method` (str), `payload` (dict/str), `headers` (dict), `timeout` (int) |
| `publish_pubsub` | Publish to Pub/Sub topic | `topic` (str), `message` (str) | `project_id` (str), `attributes` (dict), `ordering_key` (str) |

### Usage Example

```python
from tinyhive.controllers import gcp_controller

# List GCS buckets
result = gcp_controller.execute("default", "list_gcs_buckets", {
    "prefix": "prod-"
})

# Upload a file to Cloud Storage
result = gcp_controller.execute("default", "upload_to_gcs", {
    "bucket": "my-bucket",
    "object_name": "data/report.json",
    "data": '{"status": "complete", "count": 42}',
    "content_type": "application/json"
})

# Download from Cloud Storage
result = gcp_controller.execute("default", "download_from_gcs", {
    "bucket": "my-bucket",
    "object_name": "data/report.json",
    "local_path": "/tmp/report.json"
})

# List Compute instances in a zone
result = gcp_controller.execute("default", "list_compute_instances", {
    "zone": "us-central1-a",
    "filter": "status=RUNNING"
})

# Invoke a Cloud Function
result = gcp_controller.execute("default", "invoke_cloud_function", {
    "function_url": "https://us-central1-my-project.cloudfunctions.net/my-function",
    "method": "POST",
    "payload": {"action": "process", "id": "12345"}
})

# Publish to Pub/Sub
result = gcp_controller.execute("default", "publish_pubsub", {
    "topic": "my-topic",
    "message": "Event triggered at 2024-01-15T10:30:00Z",
    "attributes": {"type": "notification", "priority": "high"}
})
```

---

## GitHub Controller

### Overview

The GitHub controller integrates with the GitHub REST API for repository and issue management. Use cases include:

- Repository management
- Issue and PR automation
- CI/CD workflow triggers
- Release management
- Code retrieval

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `GITHUB_TOKEN` | GitHub Personal Access Token or Fine-grained token |

**How to get credentials:**
1. Go to GitHub Settings > Developer Settings > Personal Access Tokens
2. Create a new token with required scopes

**Required Token Scopes:**
- `repo` - Full repository access (or `public_repo` for public only)
- `workflow` - For trigger_workflow action

### Profile Configuration

```json
{
    "token_env": "GITHUB_TOKEN",
    "default_owner": "my-org",
    "api_base_url": "https://api.github.com"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_repos` | List repositories for user/org | - | `owner` (str), `type` (str), `sort` (str), `direction` (str), `per_page` (int), `page` (int) |
| `get_repo` | Get repository details | `repo` (str) | `owner` (str) |
| `create_issue` | Create a new issue | `repo` (str), `title` (str) | `owner` (str), `body` (str), `labels` (list), `assignees` (list), `milestone` (int) |
| `list_issues` | List issues in a repository | `repo` (str) | `owner` (str), `state` (str), `labels` (str), `sort` (str), `direction` (str), `per_page` (int), `page` (int) |
| `create_pr` | Create a pull request | `repo` (str), `title` (str), `head` (str), `base` (str) | `owner` (str), `body` (str), `draft` (bool), `maintainer_can_modify` (bool) |
| `add_comment` | Add comment to issue/PR | `repo` (str), `issue_number` (int), `body` (str) | `owner` (str) |
| `trigger_workflow` | Trigger a workflow dispatch | `repo` (str), `workflow_id` (str), `ref` (str) | `owner` (str), `inputs` (dict) |
| `create_release` | Create a new release | `repo` (str), `tag_name` (str) | `owner` (str), `name` (str), `body` (str), `target_commitish` (str), `draft` (bool), `prerelease` (bool), `generate_release_notes` (bool) |
| `get_file` | Get file contents from repository | `repo` (str), `path` (str) | `owner` (str), `ref` (str) |

### Usage Example

```python
from tinyhive.controllers import github_controller

# List repositories
result = github_controller.execute("default", "list_repos", {
    "owner": "my-org",
    "type": "all",
    "sort": "updated",
    "per_page": 30
})

# Create an issue
result = github_controller.execute("default", "create_issue", {
    "owner": "my-org",
    "repo": "my-repo",
    "title": "Bug: Login page not loading",
    "body": "## Description\nThe login page shows a blank screen...",
    "labels": ["bug", "priority-high"],
    "assignees": ["developer1"]
})

# Create a pull request
result = github_controller.execute("default", "create_pr", {
    "owner": "my-org",
    "repo": "my-repo",
    "title": "feat: Add user dashboard",
    "head": "feature/user-dashboard",
    "base": "main",
    "body": "## Changes\n- Added dashboard component\n- Updated routing",
    "draft": False
})

# Trigger a deployment workflow
result = github_controller.execute("default", "trigger_workflow", {
    "owner": "my-org",
    "repo": "my-repo",
    "workflow_id": "deploy.yml",
    "ref": "main",
    "inputs": {"environment": "production"}
})

# Create a release
result = github_controller.execute("default", "create_release", {
    "owner": "my-org",
    "repo": "my-repo",
    "tag_name": "v1.2.0",
    "name": "Release 1.2.0",
    "body": "## What's New\n- Feature A\n- Bug fix B",
    "generate_release_notes": True
})
```

---

## GitLab Controller

### Overview

The GitLab controller integrates with GitLab API v4 for project and issue management. Use cases include:

- Project management
- Issue tracking and automation
- Merge request workflows
- Code review automation

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `GITLAB_PAT` | GitLab Personal Access Token |

**How to get credentials:**
1. Go to GitLab > User Settings > Access Tokens
2. Create a token with required scopes (api, read_api, read_repository, write_repository)

### Profile Configuration

```json
{
    "token_env": "GITLAB_PAT",
    "base_url": "https://gitlab.com/api/v4"
}
```

For self-hosted GitLab, change `base_url` to your instance URL.

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_projects` | List GitLab projects | - | `owned` (bool), `membership` (bool), `search` (str), `visibility` (str), `per_page` (int), `page` (int) |
| `get_project` | Get a single project | `project_id` (int/str) | - |
| `list_issues` | List issues for a project | `project_id` (int/str) | `state` (str), `labels` (str), `milestone` (str), `assignee_id` (int), `author_id` (int), `search` (str), `per_page` (int), `page` (int) |
| `create_issue` | Create a new issue | `project_id` (int/str), `title` (str) | `description` (str), `labels` (str), `assignee_ids` (list), `milestone_id` (int), `confidential` (bool) |
| `list_mrs` | List merge requests | `project_id` (int/str) | `state` (str), `labels` (str), `milestone` (str), `author_id` (int), `assignee_id` (int), `source_branch` (str), `target_branch` (str), `search` (str), `per_page` (int), `page` (int) |
| `create_mr` | Create a merge request | `project_id` (int/str), `source_branch` (str), `target_branch` (str), `title` (str) | `description` (str), `assignee_ids` (list), `labels` (str), `milestone_id` (int), `remove_source_branch` (bool), `squash` (bool), `draft` (bool) |
| `add_comment` | Add comment to issue/MR | `project_id` (int/str), `item_type` (str: issue/mr), `item_iid` (int), `body` (str) | - |

### Usage Example

```python
from tinyhive.controllers import gitlab_controller

# List owned projects
result = gitlab_controller.execute("default", "list_projects", {
    "owned": True,
    "per_page": 20
})

# Get a specific project (by path or ID)
result = gitlab_controller.execute("default", "get_project", {
    "project_id": "my-group/my-project"
})

# Create an issue
result = gitlab_controller.execute("default", "create_issue", {
    "project_id": "my-group/my-project",
    "title": "Implement user authentication",
    "description": "We need to add OAuth2 support...",
    "labels": "feature,priority::high",
    "assignee_ids": [123]
})

# Create a merge request
result = gitlab_controller.execute("default", "create_mr", {
    "project_id": 12345,
    "source_branch": "feature/auth",
    "target_branch": "main",
    "title": "Add OAuth2 authentication",
    "description": "## Changes\n- Added OAuth2 provider\n- Updated login flow",
    "remove_source_branch": True,
    "squash": True
})

# Add a comment to a merge request
result = gitlab_controller.execute("default", "add_comment", {
    "project_id": "my-group/my-project",
    "item_type": "mr",
    "item_iid": 42,
    "body": "LGTM! Ready to merge."
})
```

---

## Google Controller

### Overview

The Google controller provides integration with Google Workspace APIs including Gmail and Calendar. Use cases include:

- Email automation and management
- Calendar event scheduling
- Productivity workflows
- Communication automation

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `GOOGLE_ACCESS_TOKEN` | OAuth2 access token |

**How to get credentials:**
1. Set up OAuth2 in Google Cloud Console
2. Create OAuth credentials (Desktop or Web app)
3. Complete OAuth flow to obtain access token
4. For server-side: use service account with domain-wide delegation

**Required Scopes:**
- Gmail: `https://www.googleapis.com/auth/gmail.readonly`, `https://www.googleapis.com/auth/gmail.send`
- Calendar: `https://www.googleapis.com/auth/calendar`, `https://www.googleapis.com/auth/calendar.events`

### Profile Configuration

```json
{
    "token_env": "GOOGLE_ACCESS_TOKEN"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_messages` | List Gmail messages | - | `query` (str, Gmail search syntax), `max_results` (int) |
| `send_email` | Send an email | `to` (str), `subject` (str), `body` (str) | - |
| `list_events` | List calendar events | - | `calendar_id` (str, default: "primary"), `max_results` (int) |
| `create_event` | Create a calendar event | `summary` (str), `start` (str, ISO format), `end` (str, ISO format) | `calendar_id` (str) |

### Usage Example

```python
from tinyhive.controllers import google_controller

# List unread emails
result = google_controller.execute("default", "list_messages", {
    "query": "is:unread",
    "max_results": 20
})

# List emails from specific sender
result = google_controller.execute("default", "list_messages", {
    "query": "from:important@company.com after:2024/01/01",
    "max_results": 50
})

# Send an email
result = google_controller.execute("default", "send_email", {
    "to": "recipient@example.com",
    "subject": "Meeting Follow-up",
    "body": "Thank you for meeting with us today..."
})

# List upcoming calendar events
result = google_controller.execute("default", "list_events", {
    "calendar_id": "primary",
    "max_results": 10
})

# Create a calendar event
result = google_controller.execute("default", "create_event", {
    "summary": "Team Standup",
    "start": "2024-01-20T09:00:00-05:00",
    "end": "2024-01-20T09:30:00-05:00",
    "calendar_id": "primary"
})
```

---

## Grafana Controller

### Overview

The Grafana controller integrates with the Grafana API for monitoring and observability. Use cases include:

- Dashboard management
- Data source configuration
- Alert monitoring
- Annotation creation for event marking

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `GRAFANA_API_KEY` | Grafana API key or Service Account token |

**How to get credentials:**
1. Go to Grafana > Configuration > API Keys (or Service Accounts)
2. Create a new key with appropriate role (Viewer, Editor, or Admin)

**Required Permissions:**
- `list_dashboards`, `get_dashboard`: Viewer
- `create_dashboard`, `delete_dashboard`, `create_annotation`: Editor
- `list_datasources`, `get_datasource`: Viewer (Admin for full details)
- `list_alerts`: Viewer

### Profile Configuration

```json
{
    "grafana_url": "https://grafana.example.com",
    "api_key_env": "GRAFANA_API_KEY"
}
```

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_dashboards` | Search dashboards | - | `query` (str), `tag` (str/list), `type` (str), `folderIds` (list), `starred` (bool), `limit` (int) |
| `get_dashboard` | Get a dashboard by UID | `uid` (str) | - |
| `create_dashboard` | Create or update a dashboard | `dashboard` (dict with `title`) | `folderId` (int), `folderUid` (str), `overwrite` (bool), `message` (str) |
| `delete_dashboard` | Delete a dashboard by UID | `uid` (str) | - |
| `list_datasources` | List all data sources | - | - |
| `get_datasource` | Get a data source | One of: `id` (int), `name` (str), `uid` (str) | - |
| `list_alerts` | List alert rules | - | `dashboard_id` (int), `panel_id` (int), `query` (str), `state` (str), `limit` (int), `folder_id` (list), `dashboard_query` (str), `dashboard_tag` (str/list) |
| `create_annotation` | Create an annotation | `time` (int, epoch ms), `text` (str) | `dashboardId` (int), `dashboardUID` (str), `panelId` (int), `timeEnd` (int), `tags` (list) |

### Usage Example

```python
from tinyhive.controllers import grafana_controller
import time

# Search for dashboards
result = grafana_controller.execute("default", "list_dashboards", {
    "query": "production",
    "tag": ["kubernetes", "monitoring"],
    "limit": 50
})

# Get a specific dashboard
result = grafana_controller.execute("default", "get_dashboard", {
    "uid": "abc123xyz"
})

# Create a simple dashboard
result = grafana_controller.execute("default", "create_dashboard", {
    "dashboard": {
        "id": None,
        "title": "My New Dashboard",
        "tags": ["automated"],
        "timezone": "browser",
        "panels": [],
        "schemaVersion": 30
    },
    "folderId": 0,
    "overwrite": False,
    "message": "Initial creation via API"
})

# List all data sources
result = grafana_controller.execute("default", "list_datasources", {})

# List alerting rules
result = grafana_controller.execute("default", "list_alerts", {
    "state": "alerting",
    "limit": 20
})

# Create an annotation to mark a deployment
result = grafana_controller.execute("default", "create_annotation", {
    "dashboardUID": "abc123xyz",
    "time": int(time.time() * 1000),
    "text": "Deployed version 2.1.0 to production",
    "tags": ["deployment", "production", "v2.1.0"]
})
```

---

## Common Response Format

All controllers return responses in a consistent format:

**Success Response:**
```python
{
    "ok": True,
    "result": { ... }  # or "data": { ... }
}
```

**Error Response:**
```python
{
    "ok": False,
    "error": "Error message description"
}
```

## Dependencies

| Controller | Dependencies |
|------------|--------------|
| Dropbox | None (standard library) |
| Elasticsearch | None (standard library) |
| Figma | None (standard library) |
| Firebase | `cryptography` (for service account auth) |
| Freshdesk | None (standard library) |
| GCP | `cryptography` (for service account auth) |
| GitHub | None (standard library) |
| GitLab | None (standard library) |
| Google | None (standard library) |
| Grafana | None (standard library) |

Install optional dependencies:
```bash
pip install cryptography
```
