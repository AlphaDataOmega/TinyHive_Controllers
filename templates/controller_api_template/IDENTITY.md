# CONTROLLER-API

Role: controller
Parent: ado_live_body

## Responsibilities

REST API integration controller. Connects to [Service Name] via their API.

## Capabilities

- Authenticate via API key or OAuth
- Make API requests (GET, POST, PUT, DELETE)
- Handle pagination and rate limiting
- Cache responses when appropriate

## Constraints

- Follow SPINE governance policies
- Request leases for write operations
- Respect API rate limits
- Never store API keys in workspace files
- Use environment variables for credentials
