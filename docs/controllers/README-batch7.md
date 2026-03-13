# TinyHive Controllers Documentation - Batch 7

This document covers controllers for enterprise CRM, headless CMS, analytics, email delivery, monitoring, and collaboration services.

---

## Table of Contents

1. [Salesforce Controller](#salesforce-controller)
2. [Sanity Controller](#sanity-controller)
3. [SAP Controller](#sap-controller)
4. [Segment Controller](#segment-controller)
5. [SendGrid Controller](#sendgrid-controller)
6. [Sentry Controller](#sentry-controller)
7. [ServiceNow Controller](#servicenow-controller)
8. [Shopify Controller](#shopify-controller)
9. [Slack Controller](#slack-controller)
10. [Spotify Controller](#spotify-controller)

---

## Salesforce Controller

### Overview

Salesforce is the world's leading customer relationship management (CRM) platform. The Salesforce controller provides integration with the Salesforce REST API, enabling SOQL queries, SOSL searches, and full CRUD operations on sObjects (Salesforce objects like Accounts, Contacts, Opportunities, etc.).

**Use Cases:**
- Query and analyze CRM data for reporting
- Automate lead and contact management
- Sync customer data between systems
- Create and update sales opportunities programmatically
- Build custom integrations with Salesforce orgs

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `SALESFORCE_ACCESS_TOKEN` | OAuth2 access token for Salesforce API |

**How to get credentials:**
1. Navigate to Salesforce Setup > Apps > App Manager
2. Create a new Connected App with OAuth settings
3. Enable OAuth scopes (API, Full access as needed)
4. Use the OAuth2 flow to obtain an access token
5. Alternatively, use the username-password flow for server-to-server integration

### Profile Configuration

```json
{
    "token_env": "SALESFORCE_ACCESS_TOKEN",
    "instance_url": "https://yourorg.salesforce.com"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `token_env` | No | Environment variable name for access token (default: `SALESFORCE_ACCESS_TOKEN`) |
| `instance_url` | Yes | Your Salesforce org instance URL |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `query` | Execute a SOQL query | `query` (str) | - |
| `search` | Execute a SOSL search | `search_query` (str) | - |
| `get_record` | Get a record by ID | `sobject` (str), `record_id` (str) | `fields` (list) |
| `create_record` | Create a new record | `sobject` (str), `fields` (dict) | - |
| `update_record` | Update an existing record | `sobject` (str), `record_id` (str), `fields` (dict) | - |
| `delete_record` | Delete a record | `sobject` (str), `record_id` (str) | - |
| `describe_object` | Get sObject metadata | `sobject` (str) | - |
| `list_objects` | List available sObjects | - | - |

### Usage Example

```python
from tinyhive.controllers import salesforce_controller

# Query accounts
result = salesforce_controller.execute("production", "query", {
    "query": "SELECT Id, Name, Industry FROM Account WHERE Industry = 'Technology' LIMIT 10"
})

# Create a new contact
result = salesforce_controller.execute("production", "create_record", {
    "sobject": "Contact",
    "fields": {
        "FirstName": "John",
        "LastName": "Doe",
        "Email": "john.doe@example.com",
        "AccountId": "001XXXXXXXXXXXX"
    }
})

# Update an existing account
result = salesforce_controller.execute("production", "update_record", {
    "sobject": "Account",
    "record_id": "001XXXXXXXXXXXX",
    "fields": {
        "Industry": "Healthcare",
        "Description": "Updated via API"
    }
})

# Search across objects
result = salesforce_controller.execute("production", "search", {
    "search_query": "FIND {Acme} IN ALL FIELDS RETURNING Account(Id, Name), Contact(Id, Name, Email)"
})

# Get object metadata
result = salesforce_controller.execute("production", "describe_object", {
    "sobject": "Opportunity"
})
```

---

## Sanity Controller

### Overview

Sanity is a headless CMS (Content Management System) that provides a real-time datastore and powerful APIs for structured content. The Sanity controller enables querying content using GROQ (Graph-Relational Object Queries), managing documents, and handling assets.

**Use Cases:**
- Build and manage content for websites and applications
- Query and filter structured content with GROQ
- Create, update, and delete CMS documents
- Manage images and files in the asset pipeline
- Perform batch mutations for content operations

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `SANITY_API_TOKEN` | Sanity API token with read/write access |

**How to get credentials:**
1. Go to your Sanity project at manage.sanity.io
2. Navigate to Settings > API > Tokens
3. Add a new token with appropriate permissions (read/write)
4. Copy the token and store it securely

### Profile Configuration

```json
{
    "project_id": "your-project-id",
    "dataset": "production",
    "api_version": "v2021-10-21",
    "token_env": "SANITY_API_TOKEN",
    "use_cdn": false
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `project_id` | Yes | Your Sanity project ID |
| `dataset` | No | Dataset name (default: `production`) |
| `api_version` | No | API version date string (default: `v2021-10-21`) |
| `token_env` | No | Environment variable for API token (default: `SANITY_API_TOKEN`) |
| `use_cdn` | No | Use CDN for read operations (default: `false`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `query` | Execute a GROQ query | `query` (str) | `params` (dict) |
| `get_document` | Get a document by ID | `document_id` (str) | - |
| `create` | Create a new document | `document` (dict with `_type`) | - |
| `create_or_replace` | Create or replace a document | `document` (dict with `_id`, `_type`) | - |
| `patch` | Patch an existing document | `document_id` (str) | `set` (dict), `unset` (list), `inc` (dict), `dec` (dict), `insert` (dict), `ifRevisionID` (str) |
| `delete` | Delete a document | `document_id` (str) | - |
| `mutate` | Execute batch mutations | `mutations` (list) | `return_ids` (bool), `return_documents` (bool), `visibility` (str) |
| `get_asset` | Get asset URL from reference | `asset_ref` (str) | - |

### Usage Example

```python
from tinyhive.controllers import sanity_controller

# Query blog posts
result = sanity_controller.execute("blog", "query", {
    "query": '*[_type == "post" && published == true] | order(publishedAt desc) [0...10]'
})

# Query with parameters
result = sanity_controller.execute("blog", "query", {
    "query": '*[_type == "post" && author._ref == $authorId]',
    "params": {"authorId": "author-123"}
})

# Create a new document
result = sanity_controller.execute("blog", "create", {
    "document": {
        "_type": "post",
        "title": "My New Blog Post",
        "slug": {"_type": "slug", "current": "my-new-blog-post"},
        "body": "Content here..."
    }
})

# Patch a document
result = sanity_controller.execute("blog", "patch", {
    "document_id": "post-123",
    "set": {"title": "Updated Title"},
    "inc": {"viewCount": 1}
})

# Batch mutations
result = sanity_controller.execute("blog", "mutate", {
    "mutations": [
        {"create": {"_type": "tag", "name": "Technology"}},
        {"patch": {"id": "post-123", "set": {"featured": True}}}
    ]
})
```

---

## SAP Controller

### Overview

SAP Business One is an enterprise resource planning (ERP) solution for small and medium businesses. The SAP controller integrates with the SAP Business One Service Layer API, providing access to business partners, sales orders, items, and inventory management.

**Use Cases:**
- Manage customers and suppliers (business partners)
- Create and track sales orders
- Query product inventory levels
- Integrate e-commerce platforms with SAP
- Automate order fulfillment workflows

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `SAP_B1_USERNAME` | SAP Service Layer username |
| `SAP_B1_PASSWORD` | SAP Service Layer password |

Or use profile-specific variables:
| Environment Variable | Description |
|---------------------|-------------|
| `SAP_B1_{PROFILE}_USERNAME` | Profile-specific username |
| `SAP_B1_{PROFILE}_PASSWORD` | Profile-specific password |

**How to get credentials:**
1. Obtain Service Layer credentials from your SAP administrator
2. Ensure the user has appropriate SAP Business One permissions
3. The Service Layer must be accessible (typically port 50000)

### Profile Configuration

```json
{
    "server": "sap-server.example.com",
    "company_db": "SBODemoUS",
    "port": 50000,
    "ssl_verify": true
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `server` | Yes | SAP Service Layer server hostname |
| `company_db` | Yes | Company database name |
| `port` | No | Service Layer port (default: `50000`) |
| `ssl_verify` | No | Verify SSL certificates (default: `true`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `login` | Authenticate and establish session | - | - |
| `list_business_partners` | List business partners | - | `filter` (str), `select` (str), `top` (int), `skip` (int), `orderby` (str) |
| `get_business_partner` | Get a business partner by code | `CardCode` (str) | `select` (str) |
| `create_business_partner` | Create a business partner | `CardName` (str), `CardType` (str) | `CardCode` (str), `fields` (dict) |
| `list_orders` | List sales orders | - | `filter` (str), `select` (str), `top` (int), `skip` (int), `orderby` (str) |
| `create_order` | Create a sales order | `CardCode` (str), `DocumentLines` (list) | `DocDate` (str), `DocDueDate` (str), `fields` (dict) |
| `list_items` | List items/products | - | `filter` (str), `select` (str), `top` (int), `skip` (int), `orderby` (str) |
| `get_stock` | Get inventory stock levels | `ItemCode` (str) | `WarehouseCode` (str) |

### Usage Example

```python
from tinyhive.controllers import sap_controller

# Login first (establishes session)
result = sap_controller.execute("production", "login", {})

# List customers
result = sap_controller.execute("production", "list_business_partners", {
    "filter": "CardType eq 'cCustomer'",
    "top": 20,
    "orderby": "CardName asc"
})

# Create a sales order
result = sap_controller.execute("production", "create_order", {
    "CardCode": "C20000",
    "DocumentLines": [
        {
            "ItemCode": "A00001",
            "Quantity": 10,
            "UnitPrice": 100.00,
            "WarehouseCode": "01"
        },
        {
            "ItemCode": "A00002",
            "Quantity": 5,
            "UnitPrice": 50.00,
            "WarehouseCode": "01"
        }
    ],
    "DocDueDate": "2024-12-31"
})

# Check inventory
result = sap_controller.execute("production", "get_stock", {
    "ItemCode": "A00001",
    "WarehouseCode": "01"
})

# Create a new customer
result = sap_controller.execute("production", "create_business_partner", {
    "CardName": "Acme Corporation",
    "CardType": "cCustomer",
    "fields": {
        "EmailAddress": "contact@acme.com",
        "Phone1": "555-0100"
    }
})
```

---

## Segment Controller

### Overview

Segment is a customer data platform (CDP) that collects, unifies, and routes customer data to various analytics and marketing tools. The Segment controller provides access to the HTTP Tracking API for user identification, event tracking, and data management.

**Use Cases:**
- Track user actions and behaviors across platforms
- Identify and associate users with traits
- Record page views and screen views
- Group users by company or organization
- Manage user data for GDPR/CCPA compliance

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `SEGMENT_WRITE_KEY` | Segment source Write Key |
| `SEGMENT_ACCESS_TOKEN` | Access token for Privacy API (for delete operations) |

**How to get credentials:**
1. Go to your Segment workspace at app.segment.com
2. Select your source and navigate to Settings > API Keys
3. Copy the Write Key for tracking operations
4. For Privacy API, create an access token under Settings > Access Management

### Profile Configuration

```json
{
    "write_key_env": "SEGMENT_WRITE_KEY",
    "workspace_slug": "my-workspace",
    "access_token_env": "SEGMENT_ACCESS_TOKEN",
    "timeout": 30
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `write_key_env` | No | Environment variable for Write Key (default: `SEGMENT_WRITE_KEY`) |
| `workspace_slug` | No | Workspace slug for Privacy API (required for delete) |
| `access_token_env` | No | Environment variable for access token (default: `SEGMENT_ACCESS_TOKEN`) |
| `timeout` | No | Request timeout in seconds (default: `30`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `identify` | Identify a user with traits | `user_id` or `anonymous_id` | `traits` (dict), `context` (dict), `timestamp` (str), `integrations` (dict) |
| `track` | Track an event | `user_id` or `anonymous_id`, `event` (str) | `properties` (dict), `context` (dict), `timestamp` (str), `integrations` (dict) |
| `page` | Track a page view | `user_id` or `anonymous_id` | `name` (str), `category` (str), `properties` (dict), `context` (dict) |
| `screen` | Track a mobile screen view | `user_id` or `anonymous_id` | `name` (str), `properties` (dict), `context` (dict) |
| `group` | Associate user with a group | `user_id` or `anonymous_id`, `group_id` (str) | `traits` (dict), `context` (dict) |
| `alias` | Alias two user IDs | `previous_id` (str), `user_id` (str) | `context` (dict) |
| `batch` | Send multiple events | `batch` (list) | `context` (dict) |
| `delete` | Delete user data (Privacy API) | `user_id` (str) | `regulation_type` (str) |

### Usage Example

```python
from tinyhive.controllers import segment_controller

# Identify a user
result = segment_controller.execute("analytics", "identify", {
    "user_id": "user-123",
    "traits": {
        "email": "john@example.com",
        "name": "John Doe",
        "plan": "premium",
        "company": "Acme Inc"
    }
})

# Track an event
result = segment_controller.execute("analytics", "track", {
    "user_id": "user-123",
    "event": "Order Completed",
    "properties": {
        "order_id": "ORD-456",
        "total": 99.99,
        "products": ["SKU-001", "SKU-002"]
    }
})

# Track a page view
result = segment_controller.execute("analytics", "page", {
    "user_id": "user-123",
    "name": "Checkout",
    "category": "Ecommerce",
    "properties": {
        "url": "https://example.com/checkout",
        "referrer": "https://example.com/cart"
    }
})

# Batch multiple events
result = segment_controller.execute("analytics", "batch", {
    "batch": [
        {"type": "identify", "userId": "user-123", "traits": {"name": "John"}},
        {"type": "track", "userId": "user-123", "event": "Signed Up"},
        {"type": "track", "userId": "user-123", "event": "Trial Started"}
    ]
})

# Delete user data (GDPR)
result = segment_controller.execute("analytics", "delete", {
    "user_id": "user-123",
    "regulation_type": "GDPR"
})
```

---

## SendGrid Controller

### Overview

SendGrid is a cloud-based email delivery service for transactional and marketing emails. The SendGrid controller provides integration with the SendGrid API v3 for sending emails, managing contacts, and retrieving analytics.

**Use Cases:**
- Send transactional emails (receipts, notifications, alerts)
- Use dynamic templates for personalized emails
- Manage marketing contact lists
- Track email delivery and engagement statistics
- Validate email addresses before sending

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `SENDGRID_API_KEY` | SendGrid API key |

**How to get credentials:**
1. Log in to your SendGrid account at app.sendgrid.com
2. Go to Settings > API Keys
3. Click "Create API Key"
4. Choose Full Access or restricted access with required scopes
5. Copy and securely store the API key

### Profile Configuration

```json
{
    "api_key_env": "SENDGRID_API_KEY"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `api_key_env` | No | Environment variable for API key (default: `SENDGRID_API_KEY`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `send_email` | Send a transactional email | `to`, `from_email`, `subject`, `content` | `from_name`, `content_type`, `cc`, `bcc`, `reply_to`, `attachments` |
| `send_template` | Send email using dynamic template | `to`, `from_email`, `template_id` | `from_name`, `dynamic_data`, `cc`, `bcc`, `reply_to` |
| `add_contact` | Add/update a marketing contact | `email` (str) | `first_name`, `last_name`, `list_ids`, `custom_fields` |
| `list_contacts` | List marketing contacts | - | `page_size` (int), `page_token` (str) |
| `create_list` | Create a contact list | `name` (str) | - |
| `get_stats` | Get email statistics | `start_date` (str) | `end_date` (str), `aggregated_by` (str) |
| `validate_email` | Validate an email address | `email` (str) | `source` (str) |
| `list_templates` | List email templates | - | `generations` (str), `page_size` (int) |

### Usage Example

```python
from tinyhive.controllers import sendgrid_controller

# Send a simple email
result = sendgrid_controller.execute("transactional", "send_email", {
    "to": "customer@example.com",
    "from_email": "noreply@mycompany.com",
    "from_name": "My Company",
    "subject": "Your Order Confirmation",
    "content": "<h1>Thank you for your order!</h1><p>Order #12345</p>",
    "content_type": "text/html"
})

# Send using a dynamic template
result = sendgrid_controller.execute("transactional", "send_template", {
    "to": ["user1@example.com", "user2@example.com"],
    "from_email": "noreply@mycompany.com",
    "template_id": "d-abc123def456",
    "dynamic_data": {
        "first_name": "John",
        "order_number": "12345",
        "total": "$99.99"
    }
})

# Add a marketing contact
result = sendgrid_controller.execute("marketing", "add_contact", {
    "email": "subscriber@example.com",
    "first_name": "Jane",
    "last_name": "Smith",
    "list_ids": ["list-id-123"]
})

# Get email statistics
result = sendgrid_controller.execute("marketing", "get_stats", {
    "start_date": "2024-01-01",
    "end_date": "2024-01-31",
    "aggregated_by": "day"
})

# Validate an email
result = sendgrid_controller.execute("transactional", "validate_email", {
    "email": "test@example.com"
})
```

---

## Sentry Controller

### Overview

Sentry is an application monitoring and error tracking platform. The Sentry controller provides integration with the Sentry API for managing projects, issues, events, and releases programmatically.

**Use Cases:**
- List and monitor project issues
- Update issue status and assignments
- Create releases and track deployments
- Capture custom events programmatically
- Build custom error monitoring dashboards

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `SENTRY_AUTH_TOKEN` | Sentry authentication token |

**How to get credentials:**
1. Go to Sentry at sentry.io
2. Navigate to Settings > Auth Tokens
3. Create a new token with required scopes
4. Copy and store the token securely

**Required Scopes:**
- `project:read` - for list_projects
- `event:read` - for list_issues, get_issue, list_events
- `event:write` - for update_issue, capture_event
- `release:read` - for list_releases
- `release:write` - for create_release

### Profile Configuration

```json
{
    "org_slug": "my-organization",
    "token_env": "SENTRY_AUTH_TOKEN"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `org_slug` | Yes | Your Sentry organization slug |
| `token_env` | No | Environment variable for auth token (default: `SENTRY_AUTH_TOKEN`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_projects` | List organization projects | - | `org_slug` (str) |
| `list_issues` | List project issues | `project_slug` (str) | `org_slug`, `query`, `statsPeriod` |
| `get_issue` | Get issue details | `issue_id` (str) | - |
| `update_issue` | Update issue status/assignment | `issue_id` (str) | `status` (str), `assignedTo` (str) |
| `list_events` | List events for an issue | `issue_id` (str) | - |
| `capture_event` | Send a custom event | `dsn` (str), `event_data` (dict) | - |
| `list_releases` | List organization releases | - | `org_slug` (str) |
| `create_release` | Create a new release | `version` (str), `projects` (list) | `org_slug`, `ref`, `url`, `dateReleased` |

### Usage Example

```python
from tinyhive.controllers import sentry_controller

# List projects
result = sentry_controller.execute("monitoring", "list_projects", {})

# List unresolved issues
result = sentry_controller.execute("monitoring", "list_issues", {
    "project_slug": "my-web-app",
    "query": "is:unresolved",
    "statsPeriod": "24h"
})

# Get issue details
result = sentry_controller.execute("monitoring", "get_issue", {
    "issue_id": "123456789"
})

# Resolve an issue
result = sentry_controller.execute("monitoring", "update_issue", {
    "issue_id": "123456789",
    "status": "resolved"
})

# Create a release
result = sentry_controller.execute("monitoring", "create_release", {
    "version": "1.2.3",
    "projects": ["my-web-app", "my-api"],
    "ref": "abc123def456"
})

# Capture a custom event
result = sentry_controller.execute("monitoring", "capture_event", {
    "dsn": "https://key@sentry.io/123456",
    "event_data": {
        "message": "Custom event captured",
        "level": "info",
        "tags": {"environment": "production"},
        "extra": {"user_id": "user-123"}
    }
})
```

---

## ServiceNow Controller

### Overview

ServiceNow is an enterprise IT service management (ITSM) platform. The ServiceNow controller provides integration with ServiceNow REST APIs for incident management, user lookups, CMDB queries, change requests, and Flow Designer automation.

**Use Cases:**
- Create and manage IT incidents
- Query user and CMDB information
- Submit change requests
- Automate ITSM workflows with Flow Designer
- Integrate helpdesk operations with external systems

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `SERVICENOW_USERNAME` | ServiceNow username |
| `SERVICENOW_PASSWORD` | ServiceNow password |

**How to get credentials:**
1. Obtain credentials from your ServiceNow administrator
2. User must have appropriate roles (itil, user_admin, etc.)
3. Ensure REST API access is enabled for the user

### Profile Configuration

```json
{
    "instance": "yourinstance.service-now.com",
    "username_env": "SERVICENOW_USERNAME",
    "password_env": "SERVICENOW_PASSWORD",
    "timeout": 30
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `instance` | Yes | ServiceNow instance hostname |
| `username_env` | No | Environment variable for username (default: `SERVICENOW_USERNAME`) |
| `password_env` | No | Environment variable for password (default: `SERVICENOW_PASSWORD`) |
| `timeout` | No | Request timeout in seconds (default: `30`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_incidents` | List incidents | - | `sysparm_query`, `sysparm_limit`, `sysparm_offset`, `sysparm_fields`, `sysparm_display_value` |
| `get_incident` | Get incident by sys_id | `sys_id` (str) | `sysparm_fields`, `sysparm_display_value` |
| `create_incident` | Create an incident | `short_description` (str) | `description`, `urgency`, `impact`, `assignment_group`, `caller_id`, `category`, `subcategory`, `state`, `additional_fields` |
| `update_incident` | Update an incident | `sys_id` (str), `fields` (dict) | - |
| `list_users` | List users | - | `sysparm_query`, `sysparm_limit`, `sysparm_offset`, `sysparm_fields` |
| `list_cmdb_items` | List CMDB configuration items | - | `table`, `sysparm_query`, `sysparm_limit`, `sysparm_offset`, `sysparm_fields` |
| `create_change_request` | Create a change request | `short_description` (str) | `description`, `type`, `category`, `priority`, `risk`, `impact`, `assignment_group`, `assigned_to`, `start_date`, `end_date`, `additional_fields` |
| `execute_flow` | Trigger a Flow Designer flow | `flow_sys_id` (str) | `inputs` (dict) |

### Usage Example

```python
from tinyhive.controllers import servicenow_controller

# List open incidents
result = servicenow_controller.execute("production", "list_incidents", {
    "sysparm_query": "active=true^priority=1",
    "sysparm_limit": 50,
    "sysparm_display_value": "true"
})

# Create an incident
result = servicenow_controller.execute("production", "create_incident", {
    "short_description": "Server unreachable",
    "description": "Production web server is not responding to requests",
    "urgency": 1,
    "impact": 1,
    "category": "Network",
    "assignment_group": "Network Support"
})

# Update incident
result = servicenow_controller.execute("production", "update_incident", {
    "sys_id": "abc123def456",
    "fields": {
        "state": 2,
        "work_notes": "Investigating the issue"
    }
})

# Query CMDB servers
result = servicenow_controller.execute("production", "list_cmdb_items", {
    "table": "cmdb_ci_server",
    "sysparm_query": "operational_status=1",
    "sysparm_fields": "name,ip_address,os,location"
})

# Create a change request
result = servicenow_controller.execute("production", "create_change_request", {
    "short_description": "Database upgrade to v15",
    "type": "normal",
    "risk": 2,
    "start_date": "2024-12-15T02:00:00",
    "end_date": "2024-12-15T04:00:00"
})
```

---

## Shopify Controller

### Overview

Shopify is a leading e-commerce platform for online stores. The Shopify controller provides integration with the Shopify Admin REST API for managing orders, products, inventory, customers, and fulfillments.

**Use Cases:**
- Process and manage customer orders
- Sync product catalog and inventory
- Create order fulfillments and track shipments
- Manage customer information
- Build custom e-commerce integrations

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `SHOPIFY_ACCESS_TOKEN` | Shopify Admin API access token |

**How to get credentials:**
1. Go to your Shopify admin at yourstore.myshopify.com/admin
2. Navigate to Apps > Develop apps
3. Create a new app or select existing
4. Configure Admin API scopes as needed
5. Install the app and copy the Admin API access token

**Required Scopes:**
- `read_orders`, `write_orders` - for order operations
- `read_products` - for product operations
- `write_inventory` - for inventory updates
- `read_customers` - for customer operations
- `write_fulfillments` - for fulfillment operations

### Profile Configuration

```json
{
    "store": "mystore.myshopify.com",
    "token_env": "SHOPIFY_ACCESS_TOKEN",
    "api_version": "2024-01"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `store` | Yes | Shopify store domain |
| `token_env` | No | Environment variable for access token (default: `SHOPIFY_ACCESS_TOKEN`) |
| `api_version` | No | Shopify API version (default: `2024-01`) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `list_orders` | List orders | - | `status`, `created_at_min`, `created_at_max`, `limit` |
| `get_order` | Get order details | `order_id` | - |
| `create_order` | Create a new order | `line_items` (list) | `customer`, `shipping_address`, `email`, `financial_status`, `send_receipt`, `send_fulfillment_receipt` |
| `update_order` | Update an order | `order_id`, `fields` (dict) | - |
| `list_products` | List products | - | `title`, `vendor`, `product_type`, `limit` |
| `get_product` | Get product details | `product_id` | - |
| `update_inventory` | Update inventory level | `inventory_item_id`, `location_id`, `available` (int) | - |
| `list_customers` | List customers | - | `email`, `created_at_min`, `limit` |
| `create_fulfillment` | Create order fulfillment | `order_id` | `tracking_number`, `tracking_company`, `tracking_url`, `notify_customer`, `line_items` |

### Usage Example

```python
from tinyhive.controllers import shopify_controller

# List recent orders
result = shopify_controller.execute("mystore", "list_orders", {
    "status": "open",
    "created_at_min": "2024-01-01T00:00:00",
    "limit": 50
})

# Create an order
result = shopify_controller.execute("mystore", "create_order", {
    "line_items": [
        {"variant_id": 12345678, "quantity": 2}
    ],
    "customer": {"email": "customer@example.com"},
    "shipping_address": {
        "first_name": "John",
        "last_name": "Doe",
        "address1": "123 Main St",
        "city": "Boston",
        "province": "MA",
        "country": "US",
        "zip": "02101"
    },
    "financial_status": "paid"
})

# Update inventory
result = shopify_controller.execute("mystore", "update_inventory", {
    "inventory_item_id": 12345678,
    "location_id": 87654321,
    "available": 100
})

# Create fulfillment with tracking
result = shopify_controller.execute("mystore", "create_fulfillment", {
    "order_id": 9876543210,
    "tracking_number": "1Z999AA10123456784",
    "tracking_company": "UPS",
    "notify_customer": True
})

# List products by vendor
result = shopify_controller.execute("mystore", "list_products", {
    "vendor": "Acme",
    "limit": 100
})
```

---

## Slack Controller

### Overview

Slack is a business communication platform for team messaging and collaboration. The Slack controller provides integration with the Slack Web API for sending messages, managing channels, uploading files, and interacting with users.

**Use Cases:**
- Send automated notifications and alerts
- Create and manage channels programmatically
- Upload files and share content
- Send direct messages to users
- Add reactions to messages

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `SLACK_BOT_TOKEN` | Slack Bot User OAuth Token (starts with `xoxb-`) |

**How to get credentials:**
1. Go to api.slack.com/apps and create a new app
2. Navigate to OAuth & Permissions
3. Add required bot token scopes
4. Install app to your workspace
5. Copy the Bot User OAuth Token

**Required Scopes:**
- `chat:write` - for send_message, send_dm
- `files:write` - for upload_file
- `channels:read` - for list_channels
- `reactions:write` - for add_reaction
- `channels:manage` - for create_channel, set_topic
- `users:read` - for list_users
- `im:write` - for send_dm

### Profile Configuration

```json
{
    "token_env": "SLACK_BOT_TOKEN",
    "default_channel": "#general"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `token_env` | No | Environment variable for bot token (default: `SLACK_BOT_TOKEN`) |
| `default_channel` | No | Default channel for messages |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `send_message` | Post a message to a channel | `channel` (str), `text` or `blocks` | `thread_ts`, `mrkdwn` |
| `send_dm` | Send direct message to user | `user_id` (str), `text` or `blocks` | - |
| `upload_file` | Upload a file to channel(s) | `channels` (str), `file_content` (str), `filename` (str) | `title`, `initial_comment`, `filetype` |
| `list_channels` | List available channels | - | `types`, `limit`, `exclude_archived`, `cursor` |
| `add_reaction` | Add emoji reaction | `channel` (str), `timestamp` (str), `emoji` (str) | - |
| `create_channel` | Create a new channel | `name` (str) | `is_private` (bool) |
| `set_topic` | Set channel topic | `channel` (str), `topic` (str) | - |
| `list_users` | List workspace users | - | `limit`, `cursor`, `include_locale` |

### Usage Example

```python
from tinyhive.controllers import slack_controller

# Send a message
result = slack_controller.execute("workspace", "send_message", {
    "channel": "#deployments",
    "text": "Deployment v1.2.3 completed successfully!"
})

# Send a message with blocks (rich formatting)
result = slack_controller.execute("workspace", "send_message", {
    "channel": "#alerts",
    "text": "Alert: High CPU usage",
    "blocks": [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Alert:* High CPU usage detected on `prod-web-01`"
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": "*CPU:* 95%"},
                {"type": "mrkdwn", "text": "*Memory:* 78%"}
            ]
        }
    ]
})

# Send a direct message
result = slack_controller.execute("workspace", "send_dm", {
    "user_id": "U1234567890",
    "text": "Your report is ready for review."
})

# Upload a file
result = slack_controller.execute("workspace", "upload_file", {
    "channels": "#reports",
    "file_content": "Date,Value\n2024-01-01,100\n2024-01-02,150",
    "filename": "report.csv",
    "title": "Weekly Report",
    "initial_comment": "Here's the weekly metrics report"
})

# Create a channel
result = slack_controller.execute("workspace", "create_channel", {
    "name": "project-phoenix",
    "is_private": False
})

# Add a reaction
result = slack_controller.execute("workspace", "add_reaction", {
    "channel": "C1234567890",
    "timestamp": "1234567890.123456",
    "emoji": "thumbsup"
})
```

---

## Spotify Controller

### Overview

Spotify is a digital music streaming service. The Spotify controller provides access to the Spotify Web API for searching the music catalog, retrieving track/album/artist information, accessing playlists, and getting personalized recommendations.

**Use Cases:**
- Search for tracks, albums, artists, and playlists
- Retrieve detailed music catalog information
- Access user playlists and profiles
- Generate music recommendations
- Build music-related applications and integrations

### Authentication

| Environment Variable | Description |
|---------------------|-------------|
| `SPOTIFY_ACCESS_TOKEN` | OAuth2 access token from Spotify authorization |

**How to get credentials:**
1. Go to developer.spotify.com/dashboard
2. Create a new application
3. Configure redirect URIs for OAuth flow
4. Implement OAuth2 authorization code flow or client credentials flow
5. Exchange authorization code for access token

**Required Scopes (depending on action):**
- `user-read-private` - for get_current_user
- `user-read-email` - for get_current_user
- `playlist-read-private` - for private playlists
- `playlist-read-collaborative` - for collaborative playlists

### Profile Configuration

```json
{
    "token_env": "SPOTIFY_ACCESS_TOKEN",
    "default_market": "US"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `token_env` | No | Environment variable for access token (default: `SPOTIFY_ACCESS_TOKEN`) |
| `default_market` | No | Default market/country code (ISO 3166-1 alpha-2) |

### Actions

| Action | Description | Required Params | Optional Params |
|--------|-------------|-----------------|-----------------|
| `search` | Search the catalog | `q` (str), `type` (str) | `limit`, `market`, `offset` |
| `get_track` | Get track information | `track_id` (str) | `market` |
| `get_album` | Get album information | `album_id` (str) | `market` |
| `get_artist` | Get artist information | `artist_id` (str) | - |
| `get_playlist` | Get playlist details | `playlist_id` (str) | `market`, `fields` |
| `get_user_playlists` | Get user's playlists | `user_id` (str) | `limit`, `offset` |
| `get_current_user` | Get current user profile | - | - |
| `get_recommendations` | Get track recommendations | At least one of: `seed_artists`, `seed_tracks`, `seed_genres` | `limit`, `market` |

### Usage Example

```python
from tinyhive.controllers import spotify_controller

# Search for tracks
result = spotify_controller.execute("music", "search", {
    "q": "Bohemian Rhapsody",
    "type": "track",
    "limit": 10
})

# Search for artists
result = spotify_controller.execute("music", "search", {
    "q": "Taylor Swift",
    "type": "artist",
    "limit": 5
})

# Get track details
result = spotify_controller.execute("music", "get_track", {
    "track_id": "4u7EnebtmKWzUH433cf5Qv"
})

# Get album details
result = spotify_controller.execute("music", "get_album", {
    "album_id": "4LH4d3cOWNNsVw41Gqt2kv"
})

# Get artist information
result = spotify_controller.execute("music", "get_artist", {
    "artist_id": "06HL4z0CvFAxyc27GXpf02"
})

# Get playlist
result = spotify_controller.execute("music", "get_playlist", {
    "playlist_id": "37i9dQZF1DXcBWIGoYBM5M",
    "fields": "name,description,tracks.items(track(name,artists))"
})

# Get recommendations
result = spotify_controller.execute("music", "get_recommendations", {
    "seed_artists": "4NHQUGzhtTLFvgF5SZesLK",
    "seed_genres": "pop,rock",
    "limit": 20
})

# Get current user profile
result = spotify_controller.execute("music", "get_current_user", {})
```

---

## Summary

This batch covers 10 controllers spanning enterprise CRM (Salesforce), headless CMS (Sanity), ERP (SAP), analytics (Segment), email delivery (SendGrid), error monitoring (Sentry), IT service management (ServiceNow), e-commerce (Shopify), team communication (Slack), and music streaming (Spotify).

Each controller follows the TinyHive pattern:
- Profile-based configuration stored in `profiles/{name}.json`
- Credentials stored in environment variables for security
- Standard `execute(profile, action, params)` dispatch interface
- Consistent response format with `ok`, `data`/`error` fields

For additional controllers, see other batch documentation files in this directory.
