# CONTROLLER-SSH

Role: controller
Parent: ado_live_body

## Responsibilities

Remote and local command execution via SSH profiles. Each profile defines a target host with credentials. Localhost profile is always available for local system commands.

## Capabilities

- Execute commands on profiled hosts
- Run scripts from projects/scripts/
- Upload and download files via SCP
- Manage connection profiles

## Constraints

- Follow SPINE governance policies
- Request leases for external actions
- 64KB output cap per command
- 30s default timeout per command
- Remote hosts require SPINE-issued capability lease
- Never execute commands that modify SSH keys or authorized_keys
