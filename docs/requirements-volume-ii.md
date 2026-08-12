# Volume II requirements — Digital Vehicle

## Functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| DV-F-001 | Every vehicle shall own exactly one digital-state aggregate. | Model, migration, registration test |
| DV-F-002 | The aggregate shall represent operational mode, battery, powertrain, brakes, steering, and lighting. | Typed schemas and OpenAPI |
| DV-F-003 | Vehicle registration shall create a deterministic safe baseline. | Service and tests |
| DV-F-004 | Authorized clients shall read and replace the complete state through versioned HTTP APIs. | GET/PUT API tests |
| DV-F-005 | Replacement shall validate component bounds and cross-component safety invariants. | Schema tests |
| DV-F-006 | Replacement shall use optimistic version control and report stale updates with a stable conflict error. | Service and integration tests |
| DV-F-007 | An exact retry shall be idempotent and shall not duplicate transition evidence. | Retry test |
| DV-F-008 | A real transition shall atomically persist state, audit evidence, and a versioned outbox event. | Transaction test |

## Non-functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| DV-NF-001 | Read and write access shall use independent deny-by-default permissions. | RBAC tests |
| DV-NF-002 | Numeric inputs shall have explicit safe contract bounds. | Pydantic schema tests |
| DV-NF-003 | Error responses shall use the platform-wide correlation-aware envelope. | API contract tests |
| DV-NF-004 | Audit details shall avoid copying the complete state payload. | Audit assertions |
| DV-NF-005 | The migration shall backfill existing vehicles without requiring cloud infrastructure. | Alembic and disposable integration |
| DV-NF-006 | The increment shall pass Ruff, strict mypy, unit/contract tests, and disposable integration. | CI quality gates |
