# TinyHive Controllers Documentation

Controllers are the execution layer that connects TinyHive agents to external systems. They translate agent requests into real-world actions - calling APIs, automating workflows, managing cloud resources, and integrating with third-party services.

---

## Quick Stats

| Metric | Value |
|--------|-------|
| **Total Controllers** | 92 |
| **Total Actions** | 725+ |
| **Dependencies** | Python stdlib only |

---

## Controller Categories

### AI/ML
| Controller | Description |
|------------|-------------|
| anthropic | Claude AI models - chat completions, streaming, tool use |
| mistral | Mistral AI models - chat, embeddings, code generation |
| openai | OpenAI GPT models - completions, embeddings, DALL-E |
| replicate | Run ML models via Replicate API |
| vapi | Voice AI platform - calls, assistants, phone numbers |

### Analytics
| Controller | Description |
|------------|-------------|
| amplitude | Product analytics - events, user tracking, retention |
| mixpanel | User analytics - events, profiles, funnels |
| plausible | Privacy-focused web analytics |
| posthog | Product analytics - events, feature flags, experiments |
| segment | Customer data platform - track, identify, group |

### Cloud
| Controller | Description |
|------------|-------------|
| aws | Amazon Web Services - S3, EC2, Lambda, SQS, SNS |
| cloudflare | DNS, Workers, KV storage, R2 buckets |
| gcp | Google Cloud Platform - Storage, Compute, BigQuery |
| oracle | Oracle Cloud Infrastructure - Compute, Storage, Database |
| vercel | Frontend deployment - projects, deployments, domains |
| netlify | Web hosting - sites, deploys, functions |

### CMS
| Controller | Description |
|------------|-------------|
| contentful | Headless CMS - entries, assets, content types |
| sanity | Structured content - documents, assets, GROQ queries |
| webflow | Visual web design - sites, collections, items |
| wordpress | Blog/CMS - posts, pages, media, users |

### Communication
| Controller | Description |
|------------|-------------|
| discord | Discord bot - messages, channels, guilds, reactions |
| slack | Slack integration - messages, channels, users, files |
| teams | Microsoft Teams - messages, channels, chats |
| telegram | Telegram bot - messages, chats, media, updates |
| twilio | SMS, voice calls, messaging services |
| vonage | SMS, voice, verify, messaging APIs |

### CRM/Sales
| Controller | Description |
|------------|-------------|
| hubspot | CRM - contacts, companies, deals, tickets |
| pipedrive | Sales CRM - persons, deals, organizations |
| salesforce | Enterprise CRM - objects, SOQL, bulk operations |
| marketo | Marketing automation - leads, campaigns, emails |

### Database
| Controller | Description |
|------------|-------------|
| database | SQL databases - PostgreSQL, MySQL, SQLite |
| elasticsearch | Search and analytics - index, search, aggregations |
| firebase | Firebase - Firestore, Auth, Realtime Database |
| mongodb | MongoDB - documents, collections, aggregations |
| redis | Redis - key-value, caching, pub/sub |
| supabase | Postgres + Auth - tables, storage, realtime |

### DevOps
| Controller | Description |
|------------|-------------|
| bitbucket | Git repos - repositories, PRs, pipelines |
| circleci | CI/CD - pipelines, workflows, jobs |
| dockerhub | Container registry - images, tags, repositories |
| github | GitHub - repos, issues, PRs, actions |
| gitlab | GitLab - projects, merge requests, CI/CD |
| jenkins | CI/CD server - jobs, builds, pipelines |
| kubernetes | Container orchestration - pods, deployments, services |
| prometheus | Monitoring - metrics, alerts, queries |
| terraform | Infrastructure as code - state, workspaces, runs |

### E-commerce
| Controller | Description |
|------------|-------------|
| bigcommerce | E-commerce - products, orders, customers |
| shopify | E-commerce - products, orders, inventory |
| stripe | Payments - charges, subscriptions, customers |
| paypal | Payments - orders, transactions, payouts |
| woocommerce | WordPress e-commerce - products, orders |

### Finance
| Controller | Description |
|------------|-------------|
| quickbooks | Accounting - invoices, customers, payments |
| xero | Accounting - invoices, contacts, bank transactions |

### Identity/Auth
| Controller | Description |
|------------|-------------|
| auth0 | Identity - users, roles, authentication logs |
| okta | Identity management - users, groups, applications |

### Media/Entertainment
| Controller | Description |
|------------|-------------|
| spotify | Music - playlists, tracks, user library |
| twitch | Streaming - channels, streams, chat |
| youtube | Video - channels, videos, playlists, comments |

### Monitoring
| Controller | Description |
|------------|-------------|
| datadog | Monitoring - metrics, logs, dashboards |
| grafana | Visualization - dashboards, panels, alerts |
| pagerduty | Incident management - incidents, services, schedules |
| sentry | Error tracking - issues, events, releases |

### Productivity
| Controller | Description |
|------------|-------------|
| asana | Work management - tasks, projects, workspaces |
| calendly | Scheduling - events, event types, invitees |
| clickup | Project management - tasks, lists, spaces |
| confluence | Wiki - pages, spaces, content |
| jira | Issue tracking - issues, projects, sprints |
| linear | Issue tracking - issues, projects, cycles |
| monday | Work OS - boards, items, updates |
| notion | Workspace - pages, databases, blocks |
| trello | Kanban boards - cards, lists, boards |

### Social
| Controller | Description |
|------------|-------------|
| pinterest | Pins, boards, user content |
| reddit | Posts, comments, subreddits |
| tiktok | Videos, user data, analytics |

### Storage
| Controller | Description |
|------------|-------------|
| airtable | Spreadsheet-database - records, bases, tables |
| box | Cloud storage - files, folders, sharing |
| dropbox | Cloud storage - files, folders, sharing |

### Support
| Controller | Description |
|------------|-------------|
| freshdesk | Help desk - tickets, contacts, agents |
| intercom | Customer messaging - conversations, contacts |
| servicenow | IT service management - incidents, requests |
| zendesk | Customer support - tickets, users, organizations |

### Enterprise
| Controller | Description |
|------------|-------------|
| sap | SAP integration - business objects, RFC calls |
| docusign | E-signatures - envelopes, templates, signing |

### Forms/Surveys
| Controller | Description |
|------------|-------------|
| typeform | Forms and surveys - responses, forms, workspaces |

### Design
| Controller | Description |
|------------|-------------|
| figma | Design collaboration - files, comments, components |

### Development Tools
| Controller | Description |
|------------|-------------|
| retool | Internal tools - apps, queries, resources |

### Email
| Controller | Description |
|------------|-------------|
| mailchimp | Email marketing - campaigns, audiences, templates |
| sendgrid | Transactional email - send, templates, stats |

### Video/Meetings
| Controller | Description |
|------------|-------------|
| zoom | Video conferencing - meetings, webinars, users |

---

## Documentation Files

Detailed documentation for each controller is organized into batch files:

| File | Controllers |
|------|-------------|
| [README-batch1.md](controllers/README-batch1.md) | Airtable, Amplitude, Anthropic, Asana, Auth0, AWS, BigCommerce, Bitbucket, Box, Calendly |
| [README-batch2.md](controllers/README-batch2.md) | CircleCI, ClickUp, Cloudflare, Confluence, Contentful, Datadog, Discord, DocuSign, Dropbox, Elasticsearch |
| [README-batch3.md](controllers/README-batch3.md) | Figma, Firebase, Freshdesk, GCP, GitHub, GitLab, Grafana, HubSpot, Intercom, Jenkins |
| [README-batch4.md](controllers/README-batch4.md) | Jira, Kubernetes, Linear, Mailchimp, Marketo, Microsoft Teams, Mistral, Mixpanel, Monday, MongoDB |
| [README-batch5.md](controllers/README-batch5.md) | Netlify, Notion, Okta, OpenAI, Oracle, PagerDuty, PayPal, Pipedrive, Pinterest, Plausible |
| [README-batch6.md](controllers/README-batch6.md) | PostHog, Prometheus, QuickBooks, Reddit, Redis, Replicate, Retool, Salesforce, Sanity, SAP |
| [README-batch7.md](controllers/README-batch7.md) | Segment, SendGrid, Sentry, ServiceNow, Shopify, Slack, Spotify, Stripe, Supabase, Telegram |
| [README-batch8.md](controllers/README-batch8.md) | Terraform, TikTok, Trello, Twilio, Twitch, Typeform, Vapi, Vercel, Vonage, Webflow |
| [README-batch9.md](controllers/README-batch9.md) | WooCommerce, WordPress, Xero, YouTube, Zendesk, Zoom |

---

## Getting Started

### Basic Usage

```python
from tinyhive.controller import execute

# Execute a controller action
result = execute("controller_name", "profile_name", "action_name", {
    "param1": "value1",
    "param2": "value2"
})

# Check result
if result.get("ok"):
    data = result.get("result") or result.get("data")
    print(data)
else:
    print(f"Error: {result.get('error')}")
```

### Method ID Format

All controller invocations use the format:
```
controller.{type}.{profile}.{action}
```

Examples:
- `controller.slack.production.send_message`
- `controller.github.default.create_issue`
- `controller.stripe.live.create_charge`

---

## Profile Configuration

Profiles define how controllers authenticate with external services. Each profile is stored as a JSON file in the `profiles/` directory.

### Profile Structure

```
profiles/
  dev.json          # Development environment
  staging.json      # Staging environment
  production.json   # Production environment
```

### Example Profile

```json
{
  "slack": {
    "token_env": "SLACK_BOT_TOKEN",
    "default_channel": "#general"
  },
  "github": {
    "token_env": "GITHUB_TOKEN",
    "owner": "myorg"
  },
  "aws": {
    "region": "us-east-1",
    "access_key_env": "AWS_ACCESS_KEY_ID",
    "secret_key_env": "AWS_SECRET_ACCESS_KEY"
  }
}
```

### Environment Variables

Controllers read credentials from environment variables specified in the profile. This keeps secrets out of configuration files:

| Pattern | Description |
|---------|-------------|
| `*_env` | Field contains the name of an environment variable |
| Direct values | Non-sensitive config like regions, defaults |

### Creating a Profile

1. Copy an existing profile or create a new JSON file
2. Add controller configurations with appropriate `*_env` references
3. Set the corresponding environment variables
4. Reference the profile name when calling controllers

---

## Response Format

All controllers return a consistent response structure:

### Success Response
```json
{
  "ok": true,
  "result": { ... }
}
```

or

```json
{
  "ok": true,
  "data": { ... }
}
```

### Error Response
```json
{
  "ok": false,
  "error": "Error message describing what went wrong"
}
```

---

## Architecture

```
SPINE (governance) --> BODY (execution) --> MIND (orchestration)
                          |
                          +-- Controllers live here
```

Controllers are child agents of BODY. They receive work through the inbox system and execute actions on external platforms, devices, and tools.

---

## Additional Resources

- [Controller Development Guide](DEVELOPMENT.md)
- [Workspace Standard](WORKSPACE_STANDARD.md)
- [Runtime Model](RUNTIME_MODEL.md)
- [Governance & Constraints](GOVERNANCE.md)
