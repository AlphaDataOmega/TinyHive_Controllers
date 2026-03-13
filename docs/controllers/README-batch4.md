# TinyHive Controllers - Batch 4

This document covers the following controllers: HubSpot, Intercom, Jenkins, Jira, Kubernetes, Linear, Mailchimp, Make, Marketo, and Mistral.

---

## Table of Contents

1. [HubSpot Controller](#hubspot-controller)
2. [Intercom Controller](#intercom-controller)
3. [Jenkins Controller](#jenkins-controller)
4. [Jira Controller](#jira-controller)
5. [Kubernetes Controller](#kubernetes-controller)
6. [Linear Controller](#linear-controller)
7. [Mailchimp Controller](#mailchimp-controller)
8. [Make Controller](#make-controller)
9. [Marketo Controller](#marketo-controller)
10. [Mistral Controller](#mistral-controller)

---

## HubSpot Controller

### Overview

HubSpot is a comprehensive CRM platform for marketing, sales, and customer service. The HubSpot controller enables integration with HubSpot's CRM API for managing contacts, deals, companies, pipelines, and engagements.

**Use Cases:**
- Syncing customer contact information
- Creating and tracking sales deals
- Managing company records
- Automating engagement logging (notes, emails, tasks, meetings, calls)
- Building sales pipeline dashboards

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `HUBSPOT_API_KEY` | HubSpot private app access token |

**How to get credentials:**
1. Go to HubSpot > Settings > Integrations > Private Apps
2. Create a new private app
3. Select required scopes (see below)
4. Copy the generated access token

**Required Scopes:**
- `crm.objects.contacts.read` / `crm.objects.contacts.write`
- `crm.objects.deals.read` / `crm.objects.deals.write`
- `crm.objects.companies.read` / `crm.objects.companies.write`
- `crm.schemas.deals.read` (for pipelines)
- `sales-email-read` (for engagements)

### Profile Configuration

```json
{
    "api_key_env": "HUBSPOT_API_KEY",
    "portal_id": "12345678"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `api_key_env` | No | Environment variable name for API key (default: `HUBSPOT_API_KEY`) |
| `portal_id` | No | HubSpot portal ID (required for some engagement types) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `create_contact` | Create a new contact | `email` | `firstname`, `lastname`, `phone`, `properties` |
| `update_contact` | Update existing contact | `contact_id`, `properties` | - |
| `get_contact` | Get contact by ID | `contact_id` | `properties` (list of fields) |
| `search_contacts` | Search contacts with filters | - | `filters`, `sorts`, `limit`, `after`, `properties` |
| `create_deal` | Create a new deal | `dealname`, `dealstage` | `amount`, `pipeline`, `properties`, `associations` |
| `create_company` | Create a new company | `name` | `domain`, `properties`, `associations` |
| `list_pipelines` | List deal pipelines | - | `archived` |
| `create_engagement` | Create engagement/activity | `type`, `metadata` | `associations`, `timestamp`, `ownerId` |

### Usage Example

```python
from tinyhive.controllers import hubspot_controller

# Create a contact
result = hubspot_controller.execute("default", "create_contact", {
    "email": "john.doe@example.com",
    "firstname": "John",
    "lastname": "Doe",
    "phone": "+1-555-0100",
    "properties": {
        "company": "Acme Corp",
        "jobtitle": "Software Engineer"
    }
})

# Create a deal
result = hubspot_controller.execute("default", "create_deal", {
    "dealname": "Enterprise License",
    "dealstage": "appointmentscheduled",
    "amount": 50000,
    "pipeline": "default"
})

# Search contacts by company
result = hubspot_controller.execute("default", "search_contacts", {
    "filters": [
        {"propertyName": "company", "operator": "CONTAINS_TOKEN", "value": "Acme"}
    ],
    "limit": 25,
    "properties": ["email", "firstname", "lastname", "company"]
})

# Create a note engagement
result = hubspot_controller.execute("default", "create_engagement", {
    "type": "NOTE",
    "metadata": {"body": "Follow-up call scheduled for next week"},
    "associations": {"contactIds": [12345]}
})
```

---

## Intercom Controller

### Overview

Intercom is a customer messaging platform for sales, marketing, and support. The controller provides access to contacts, conversations, messages, and tags.

**Use Cases:**
- Managing customer and lead contacts
- Sending in-app or email messages
- Creating and replying to conversations
- Tagging users for segmentation
- Customer support automation

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `INTERCOM_ACCESS_TOKEN` | Intercom access token |

**How to get credentials:**
1. Go to Intercom > Settings > Developers > Developer Hub
2. Create a new app or select existing one
3. Generate an access token with required permissions

**Required Scopes:**
- Read and write contacts
- Read and write conversations
- Read and write messages
- Read and write tags

### Profile Configuration

```json
{
    "token_env": "INTERCOM_ACCESS_TOKEN"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `token_env` | No | Environment variable name for access token (default: `INTERCOM_ACCESS_TOKEN`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `create_contact` | Create new contact | - | `email`, `name`, `role`, `custom_attributes`, `phone`, `external_id` |
| `update_contact` | Update existing contact | `contact_id`, `fields` | - |
| `search_contacts` | Search contacts | `query` | `per_page`, `starting_after` |
| `send_message` | Send a message | `message_type`, `body`, `from`, `to` | `subject`, `template` |
| `create_conversation` | Create conversation | `user_id`, `body` | - |
| `reply_conversation` | Reply to conversation | `conversation_id`, `body`, `type` | `admin_id`, `user_id`, `message_type`, `attachment_urls` |
| `list_conversations` | List conversations | - | `state`, `per_page`, `starting_after` |
| `add_tag` | Add tag to contact | `contact_id`, `tag_name` | - |

### Usage Example

```python
from tinyhive.controllers import intercom_controller

# Create a lead contact
result = intercom_controller.execute("default", "create_contact", {
    "email": "lead@example.com",
    "name": "Jane Smith",
    "role": "lead",
    "custom_attributes": {
        "plan": "enterprise",
        "signup_source": "webinar"
    }
})

# Search for contacts
result = intercom_controller.execute("default", "search_contacts", {
    "query": {
        "field": "email",
        "operator": "~",
        "value": "example.com"
    },
    "per_page": 50
})

# Send an in-app message
result = intercom_controller.execute("default", "send_message", {
    "message_type": "in_app",
    "body": "Welcome to our platform! How can we help?",
    "from": {"type": "admin", "id": "12345"},
    "to": {"type": "user", "email": "user@example.com"}
})

# Reply to a conversation
result = intercom_controller.execute("default", "reply_conversation", {
    "conversation_id": "conv_123",
    "body": "Thanks for reaching out! Let me help you with that.",
    "type": "admin",
    "admin_id": "12345"
})
```

---

## Jenkins Controller

### Overview

Jenkins is an open-source automation server for CI/CD pipelines. The controller enables job management, build triggering, and monitoring through Jenkins REST API.

**Use Cases:**
- Listing and monitoring jobs
- Triggering builds with parameters
- Retrieving build status and logs
- Managing the build queue
- Stopping running builds

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `JENKINS_USERNAME` | Jenkins username |
| `JENKINS_API_TOKEN` | Jenkins API token |

**How to get credentials:**
1. Log in to Jenkins
2. Click your username > Configure
3. Under API Token, click "Add new Token"
4. Copy the generated token

**Required Permissions:**
- `list_jobs`: Overall/Read, Job/Read
- `get_job`: Job/Read
- `build_job`: Job/Build
- `get_build`: Job/Read
- `get_build_log`: Job/Read
- `stop_build`: Job/Cancel
- `get_queue`: Overall/Read
- `list_views`: Overall/Read

### Profile Configuration

```json
{
    "jenkins_url": "https://jenkins.example.com",
    "username_env": "JENKINS_USERNAME",
    "api_token_env": "JENKINS_API_TOKEN"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `jenkins_url` | Yes | Jenkins server URL |
| `username_env` | No | Environment variable for username (default: `JENKINS_USERNAME`) |
| `api_token_env` | No | Environment variable for API token (default: `JENKINS_API_TOKEN`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_jobs` | List all jobs | - | `folder`, `tree` |
| `get_job` | Get job details | `job_name` | `folder` |
| `build_job` | Trigger a build | `job_name` | `folder`, `parameters` |
| `get_build` | Get build info | `job_name`, `build_number` | `folder` |
| `get_build_log` | Get build console output | `job_name`, `build_number` | `folder`, `start` |
| `stop_build` | Stop a running build | `job_name`, `build_number` | `folder` |
| `get_queue` | Get build queue | - | - |
| `list_views` | List all views | - | - |

### Usage Example

```python
from tinyhive.controllers import jenkins_controller

# List all jobs
result = jenkins_controller.execute("default", "list_jobs", {})

# Trigger a build with parameters
result = jenkins_controller.execute("default", "build_job", {
    "job_name": "my-application",
    "parameters": {
        "BRANCH": "main",
        "ENVIRONMENT": "staging"
    }
})

# Get last build status
result = jenkins_controller.execute("default", "get_build", {
    "job_name": "my-application",
    "build_number": "lastBuild"
})

# Get build log
result = jenkins_controller.execute("default", "get_build_log", {
    "job_name": "my-application",
    "build_number": 42
})

# Check the build queue
result = jenkins_controller.execute("default", "get_queue", {})
```

---

## Jira Controller

### Overview

Jira is Atlassian's project management and issue tracking software. The controller supports issue creation, updates, searches via JQL, and project management.

**Use Cases:**
- Creating and updating issues
- Searching issues with JQL
- Adding comments to issues
- Transitioning issue states
- Assigning issues to users
- Listing projects

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `JIRA_EMAIL` | Atlassian account email |
| `JIRA_API_TOKEN` | Jira API token |

**How to get credentials:**
1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Copy the generated token

**Required Permissions:**
- `create_issue`: Browse projects, Create issues
- `update_issue`: Edit issues
- `get_issue`: Browse projects
- `search_issues`: Browse projects
- `add_comment`: Add comments
- `transition_issue`: Transition issues
- `assign_issue`: Assign issues
- `list_projects`: Browse projects

### Profile Configuration

```json
{
    "base_url": "https://yoursite.atlassian.net",
    "email_env": "JIRA_EMAIL",
    "token_env": "JIRA_API_TOKEN"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `base_url` | Yes | Jira Cloud instance URL |
| `email_env` | No | Environment variable for email (default: `JIRA_EMAIL`) |
| `token_env` | No | Environment variable for API token (default: `JIRA_API_TOKEN`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `create_issue` | Create a new issue | `project_key`, `summary` | `description`, `issue_type`, `priority`, `assignee`, `labels` |
| `update_issue` | Update an issue | `issue_key`, `fields` | - |
| `get_issue` | Get issue details | `issue_key` | `fields`, `expand` |
| `search_issues` | Search with JQL | `jql` | `fields`, `max_results`, `start_at` |
| `add_comment` | Add comment to issue | `issue_key`, `body` | - |
| `transition_issue` | Change issue status | `issue_key`, `transition_id` | - |
| `assign_issue` | Assign issue to user | `issue_key`, `account_id` | - |
| `list_projects` | List projects | - | `max_results`, `start_at`, `expand` |

### Usage Example

```python
from tinyhive.controllers import jira_controller

# Create a bug
result = jira_controller.execute("default", "create_issue", {
    "project_key": "PROJ",
    "summary": "Login button not working on mobile",
    "description": "Users report the login button is unresponsive on iOS Safari",
    "issue_type": "Bug",
    "priority": "High",
    "labels": ["mobile", "critical"]
})

# Search for open bugs assigned to me
result = jira_controller.execute("default", "search_issues", {
    "jql": "project = PROJ AND issuetype = Bug AND assignee = currentUser() AND status != Done",
    "max_results": 50
})

# Add a comment
result = jira_controller.execute("default", "add_comment", {
    "issue_key": "PROJ-123",
    "body": "Reproduced on iOS 17.2. Working on a fix."
})

# Transition to "In Progress"
result = jira_controller.execute("default", "transition_issue", {
    "issue_key": "PROJ-123",
    "transition_id": "21"  # Get from issue's available transitions
})
```

---

## Kubernetes Controller

### Overview

Kubernetes is a container orchestration platform. The controller provides access to pods, deployments, services, namespaces, and logs via the Kubernetes API.

**Use Cases:**
- Listing and inspecting pods
- Scaling deployments
- Viewing pod logs
- Managing services
- Applying manifests
- Namespace management

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `K8S_TOKEN` | Kubernetes bearer token |

**Authentication Methods:**
1. **Bearer Token**: Service account token with cluster access
2. **Kubeconfig**: Local kubeconfig file with context

### Profile Configuration

**Bearer Token Authentication:**
```json
{
    "api_server": "https://kubernetes.example.com:6443",
    "token_env": "K8S_TOKEN",
    "ca_cert_path": "/path/to/ca.crt",
    "verify_ssl": true,
    "default_namespace": "default"
}
```

**Kubeconfig Authentication:**
```json
{
    "kubeconfig_path": "~/.kube/config",
    "context": "my-cluster",
    "default_namespace": "default"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `api_server` | Yes* | Kubernetes API server URL |
| `token_env` | No | Environment variable for bearer token |
| `kubeconfig_path` | Yes* | Path to kubeconfig file |
| `context` | No | Kubeconfig context to use |
| `ca_cert_path` | No | Path to CA certificate |
| `verify_ssl` | No | Verify SSL certificates (default: true) |
| `default_namespace` | No | Default namespace (default: "default") |

*Either `api_server` or `kubeconfig_path` is required.

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_pods` | List pods | - | `namespace`, `label_selector`, `field_selector`, `limit` |
| `get_pod` | Get pod details | `name` | `namespace` |
| `list_deployments` | List deployments | - | `namespace`, `label_selector`, `limit` |
| `scale_deployment` | Scale deployment | `name`, `replicas` | `namespace` |
| `list_services` | List services | - | `namespace`, `label_selector`, `limit` |
| `list_namespaces` | List namespaces | - | `label_selector`, `limit` |
| `get_logs` | Get pod logs | `name` | `namespace`, `container`, `tail_lines`, `since_seconds`, `previous`, `timestamps` |
| `apply_manifest` | Apply K8s manifest | `manifest` | `namespace` |

### Usage Example

```python
from tinyhive.controllers import kubernetes_controller

# List all pods in production namespace
result = kubernetes_controller.execute("default", "list_pods", {
    "namespace": "production",
    "label_selector": "app=my-app"
})

# Scale a deployment
result = kubernetes_controller.execute("default", "scale_deployment", {
    "name": "web-frontend",
    "namespace": "production",
    "replicas": 5
})

# Get logs from a pod
result = kubernetes_controller.execute("default", "get_logs", {
    "name": "web-frontend-abc123",
    "namespace": "production",
    "container": "nginx",
    "tail_lines": 100
})

# Apply a ConfigMap manifest
result = kubernetes_controller.execute("default", "apply_manifest", {
    "manifest": {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "app-config"},
        "data": {"DATABASE_URL": "postgres://..."}
    },
    "namespace": "production"
})
```

---

## Linear Controller

### Overview

Linear is a modern issue tracking and project management tool. The controller uses Linear's GraphQL API for issues, teams, projects, and cycles (sprints).

**Use Cases:**
- Creating and managing issues
- Tracking project progress
- Managing sprint cycles
- Team organization
- Issue comments and updates

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `LINEAR_API_KEY` | Linear personal API key |

**How to get credentials:**
1. Go to Linear > Settings > API
2. Create a personal API key
3. Copy the key (starts with `lin_api_`)

### Profile Configuration

```json
{
    "api_key_env": "LINEAR_API_KEY"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `api_key_env` | No | Environment variable for API key (default: `LINEAR_API_KEY`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_issues` | List issues | - | `team_id`, `state`, `assignee_id`, `limit` |
| `get_issue` | Get issue details | `issue_id` | - |
| `create_issue` | Create new issue | `team_id`, `title` | `description`, `priority`, `assignee_id`, `labels`, `project_id`, `cycle_id`, `state_id`, `estimate`, `due_date`, `parent_id` |
| `update_issue` | Update an issue | `issue_id` | `title`, `description`, `state_id`, `priority`, `assignee_id`, `project_id`, `cycle_id`, `estimate`, `due_date`, `labels` |
| `add_comment` | Add comment | `issue_id`, `body` | - |
| `list_teams` | List teams | - | `limit` |
| `list_projects` | List projects | - | `team_id`, `limit` |
| `list_cycles` | List cycles/sprints | `team_id` | `limit` |

### Usage Example

```python
from tinyhive.controllers import linear_controller

# List teams to get team_id
result = linear_controller.execute("default", "list_teams", {"limit": 10})

# Create an issue
result = linear_controller.execute("default", "create_issue", {
    "team_id": "team-uuid-here",
    "title": "Implement user authentication",
    "description": "Add OAuth 2.0 authentication flow",
    "priority": 2,  # 0=none, 1=urgent, 2=high, 3=medium, 4=low
    "estimate": 5
})

# List issues in progress
result = linear_controller.execute("default", "list_issues", {
    "team_id": "team-uuid-here",
    "state": "In Progress",
    "limit": 50
})

# Add a comment
result = linear_controller.execute("default", "add_comment", {
    "issue_id": "issue-uuid-here",
    "body": "Started working on this. ETA: 2 days."
})

# List current sprint
result = linear_controller.execute("default", "list_cycles", {
    "team_id": "team-uuid-here"
})
```

---

## Mailchimp Controller

### Overview

Mailchimp is an email marketing platform. The controller supports audience management, subscriber operations, campaigns, and reporting.

**Use Cases:**
- Managing email lists/audiences
- Adding and updating subscribers
- Creating email campaigns
- Sending campaigns
- Viewing campaign analytics

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `MAILCHIMP_API_KEY` | Mailchimp API key |

**How to get credentials:**
1. Go to Mailchimp > Account > Extras > API keys
2. Create a new API key
3. Copy the key (format: `xxxxxxxx-us1`)

**Note:** The data center (e.g., `us1`, `us2`) is extracted from the API key suffix.

### Profile Configuration

```json
{
    "api_key_env": "MAILCHIMP_API_KEY"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `api_key_env` | No | Environment variable for API key (default: `MAILCHIMP_API_KEY`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_audiences` | List all audiences | - | `count`, `offset` |
| `add_subscriber` | Add subscriber to list | `list_id`, `email` | `merge_fields`, `tags`, `status` |
| `update_subscriber` | Update subscriber | `list_id`, `email` | `merge_fields`, `status` |
| `get_subscriber` | Get subscriber info | `list_id`, `email` | - |
| `list_campaigns` | List campaigns | - | `status`, `type`, `count` |
| `create_campaign` | Create a campaign | `type`, `recipients`, `settings` | - |
| `send_campaign` | Send a campaign | `campaign_id` | - |
| `get_campaign_report` | Get campaign stats | `campaign_id` | - |

### Usage Example

```python
from tinyhive.controllers import mailchimp_controller

# List audiences
result = mailchimp_controller.execute("default", "list_audiences", {
    "count": 10
})

# Add a subscriber
result = mailchimp_controller.execute("default", "add_subscriber", {
    "list_id": "abc123def",
    "email": "new.subscriber@example.com",
    "merge_fields": {
        "FNAME": "John",
        "LNAME": "Doe"
    },
    "tags": ["newsletter", "premium"],
    "status": "subscribed"
})

# Create a campaign
result = mailchimp_controller.execute("default", "create_campaign", {
    "type": "regular",
    "recipients": {
        "list_id": "abc123def"
    },
    "settings": {
        "subject_line": "March Newsletter",
        "preview_text": "Check out our latest updates",
        "title": "March 2024 Newsletter",
        "from_name": "Acme Corp",
        "reply_to": "hello@acme.com"
    }
})

# Get campaign report
result = mailchimp_controller.execute("default", "get_campaign_report", {
    "campaign_id": "campaign123"
})
```

---

## Make Controller

### Overview

Make (formerly Integromat) is a visual automation platform. The controller enables scenario management, execution triggering, and monitoring.

**Use Cases:**
- Listing and managing scenarios
- Triggering scenario executions
- Monitoring execution status
- Managing connections
- Webhook management

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `MAKE_API_TOKEN` | Make API token |

**How to get credentials:**
1. Go to Make > Profile Settings > API
2. Generate a new API token
3. Copy the token

### Profile Configuration

```json
{
    "team_id": 123456,
    "region": "eu1",
    "token_env": "MAKE_API_TOKEN"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `team_id` | Yes | Make team/organization ID |
| `region` | No | API region: `eu1`, `us1`, `eu2`, etc. (default: `eu1`) |
| `token_env` | No | Environment variable for API token (default: `MAKE_API_TOKEN`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_scenarios` | List all scenarios | - | `team_id`, `folder_id`, `pg[limit]`, `pg[offset]` |
| `get_scenario` | Get scenario details | `scenario_id` | - |
| `run_scenario` | Trigger scenario | `scenario_id` | `data`, `responsive` |
| `list_executions` | List executions | `scenario_id` | `pg[limit]`, `pg[offset]`, `status` |
| `get_execution` | Get execution details | `execution_id` | - |
| `toggle_scenario` | Enable/disable scenario | `scenario_id`, `enabled` | - |
| `list_connections` | List connections | - | `team_id`, `pg[limit]`, `pg[offset]` |
| `list_hooks` | List webhooks | - | `team_id`, `pg[limit]`, `pg[offset]` |

### Usage Example

```python
from tinyhive.controllers import make_controller

# List all scenarios
result = make_controller.execute("default", "list_scenarios", {})

# Run a scenario with input data
result = make_controller.execute("default", "run_scenario", {
    "scenario_id": 12345,
    "data": {
        "customer_id": "cust_123",
        "action": "sync"
    },
    "responsive": True  # Wait for completion
})

# Check execution history
result = make_controller.execute("default", "list_executions", {
    "scenario_id": 12345,
    "pg[limit]": 10
})

# Enable a scenario
result = make_controller.execute("default", "toggle_scenario", {
    "scenario_id": 12345,
    "enabled": True
})

# List all webhooks
result = make_controller.execute("default", "list_hooks", {})
```

---

## Marketo Controller

### Overview

Marketo is Adobe's marketing automation platform. The controller uses OAuth 2.0 client credentials for lead management, campaigns, programs, and custom activities.

**Use Cases:**
- Lead creation and management
- Syncing leads in bulk
- Adding leads to static lists
- Triggering smart campaigns
- Creating custom activities
- Program management

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `MARKETO_CLIENT_ID` | Marketo REST API client ID |
| `MARKETO_CLIENT_SECRET` | Marketo REST API client secret |

**How to get credentials:**
1. Go to Marketo Admin > Integration > LaunchPoint
2. Create a new service (API Only)
3. Note the Client ID and Client Secret
4. Find your Munchkin ID in Admin > Integration > Munchkin

### Profile Configuration

```json
{
    "munchkin_id": "123-ABC-456",
    "client_id_env": "MARKETO_CLIENT_ID",
    "client_secret_env": "MARKETO_CLIENT_SECRET"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `munchkin_id` | Yes | Marketo Munchkin ID (e.g., `123-ABC-456`) |
| `client_id_env` | No | Environment variable for client ID (default: `MARKETO_CLIENT_ID`) |
| `client_secret_env` | No | Environment variable for client secret (default: `MARKETO_CLIENT_SECRET`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `get_leads` | Get leads by filter | `filter_type`, `filter_values` | `fields`, `batch_size`, `next_page_token` |
| `create_lead` | Create/update single lead | `email` | `fields`, `lookup_field` |
| `sync_leads` | Sync multiple leads | `leads` | `action`, `lookup_field`, `async_processing`, `partition_name` |
| `add_to_list` | Add leads to static list | `list_id`, `lead_ids` | - |
| `list_programs` | List programs | - | `filter_type`, `filter_values`, `max_return`, `offset`, `earliest_updated_at`, `latest_updated_at` |
| `get_campaigns` | Get smart campaigns | - | `id`, `name`, `program_name`, `workspace_name`, `batch_size`, `next_page_token`, `is_triggerable` |
| `request_campaign` | Trigger smart campaign | `campaign_id`, `lead_ids` | `tokens` |
| `create_activity` | Create custom activity | `lead_id`, `activity_type_id`, `primary_attribute_value` | `attributes`, `activity_date` |

### Usage Example

```python
from tinyhive.controllers import marketo_controller

# Get leads by email
result = marketo_controller.execute("default", "get_leads", {
    "filter_type": "email",
    "filter_values": ["john@example.com", "jane@example.com"],
    "fields": ["email", "firstName", "lastName", "company"]
})

# Create a lead
result = marketo_controller.execute("default", "create_lead", {
    "email": "newlead@example.com",
    "fields": {
        "firstName": "New",
        "lastName": "Lead",
        "company": "Acme Corp"
    }
})

# Sync multiple leads
result = marketo_controller.execute("default", "sync_leads", {
    "leads": [
        {"email": "lead1@example.com", "firstName": "Lead", "lastName": "One"},
        {"email": "lead2@example.com", "firstName": "Lead", "lastName": "Two"}
    ],
    "action": "createOrUpdate"
})

# Add leads to a list
result = marketo_controller.execute("default", "add_to_list", {
    "list_id": 1234,
    "lead_ids": [100, 101, 102]
})

# Trigger a smart campaign
result = marketo_controller.execute("default", "request_campaign", {
    "campaign_id": 5678,
    "lead_ids": [100, 101],
    "tokens": [
        {"name": "{{my.campaignSource}}", "value": "API"}
    ]
})
```

---

## Mistral Controller

### Overview

Mistral AI provides powerful language models. The controller supports chat completions, embeddings, moderation, fill-in-the-middle completions, and fine-tuning.

**Use Cases:**
- Chat/conversation AI
- Text embeddings for semantic search
- Content moderation
- Code completion (FIM)
- Model fine-tuning

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `MISTRAL_API_KEY` | Mistral AI API key |

**How to get credentials:**
1. Go to https://console.mistral.ai/
2. Navigate to API Keys
3. Create a new API key

### Profile Configuration

```json
{
    "api_key_env": "MISTRAL_API_KEY",
    "default_model": "mistral-large-latest",
    "default_embedding_model": "mistral-embed",
    "timeout": 120
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `api_key_env` | No | Environment variable for API key (default: `MISTRAL_API_KEY`) |
| `default_model` | No | Default chat model (default: `mistral-large-latest`) |
| `default_embedding_model` | No | Default embedding model (default: `mistral-embed`) |
| `timeout` | No | Request timeout in seconds (default: 120) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `chat_complete` | Create chat completion | `messages` | `model`, `temperature`, `max_tokens`, `top_p`, `safe_prompt` |
| `create_embedding` | Generate embeddings | `input` | `model`, `encoding_format` |
| `list_models` | List available models | - | - |
| `create_fim_completion` | Fill-in-the-middle | `prompt` | `model`, `suffix`, `temperature`, `max_tokens`, `top_p`, `stop` |
| `moderate` | Content moderation | `input` | `model` |
| `upload_file` | Upload file for fine-tuning | `file_path` | `purpose` |
| `list_files` | List uploaded files | - | `purpose`, `page`, `page_size` |
| `create_fine_tuning_job` | Create fine-tuning job | `model`, `training_files` | `validation_files`, `hyperparameters`, `suffix`, `integrations` |

### Usage Example

```python
from tinyhive.controllers import mistral_controller

# Chat completion
result = mistral_controller.execute("default", "chat_complete", {
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain quantum computing in simple terms."}
    ],
    "temperature": 0.7,
    "max_tokens": 500
})

# Generate embeddings
result = mistral_controller.execute("default", "create_embedding", {
    "input": ["The quick brown fox", "jumps over the lazy dog"]
})

# Code completion (FIM)
result = mistral_controller.execute("default", "create_fim_completion", {
    "model": "codestral-latest",
    "prompt": "def calculate_fibonacci(n):\n    ",
    "suffix": "\n    return result",
    "max_tokens": 100
})

# Content moderation
result = mistral_controller.execute("default", "moderate", {
    "input": "This is some text to check for policy violations."
})

# List available models
result = mistral_controller.execute("default", "list_models", {})

# Fine-tuning workflow
result = mistral_controller.execute("default", "upload_file", {
    "file_path": "/path/to/training_data.jsonl",
    "purpose": "fine-tune"
})

result = mistral_controller.execute("default", "create_fine_tuning_job", {
    "model": "mistral-small-latest",
    "training_files": ["file-id-from-upload"],
    "hyperparameters": {
        "learning_rate": 0.0001,
        "training_steps": 1000
    },
    "suffix": "my-custom-model"
})
```

---

## Common Patterns

### Error Handling

All controllers return responses with an `ok` field:

```python
result = controller.execute("profile", "action", params)

if result.get("ok"):
    data = result.get("data") or result.get("result")
    # Process successful response
else:
    error = result.get("error")
    # Handle error
```

### Profile Management

Profiles are stored as JSON files in the `profiles/` directory:

```
profiles/
  default.json
  production.json
  staging.json
```

### Environment Variables

Never hardcode credentials. Use environment variables:

```bash
export HUBSPOT_API_KEY="your-api-key"
export JIRA_EMAIL="your-email"
export JIRA_API_TOKEN="your-token"
```

---

## Dependencies

All controllers use Python standard library only - no external dependencies required.
