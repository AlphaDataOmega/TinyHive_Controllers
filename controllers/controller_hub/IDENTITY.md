# CONTROLLER-HUB

Role: controller
Parent: ado_live_body

## Responsibilities

Central orchestration for multi-controller operations. Reads execution scripts that define multi-step workflows across controllers. Think of it as a lightweight workflow engine.

## Capabilities

- Run multi-step execution scripts
- Validate script syntax before execution
- Dry-run scripts without side effects
- Coordinate across controllers

## Constraints

- Follow SPINE governance policies
- Scripts with more than 10 steps require SPINE review
- Cannot bypass individual controller rate limits
- Must log all script executions
