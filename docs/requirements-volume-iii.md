# ATEP Volume III — ECU Simulator Requirements

Status: Increment III-1 implemented.

## Functional Requirements

| ID | Requirement | Evidence |
|---|---|---|
| ECU-FR-001 | The platform shall create ECUs owned by an existing vehicle. | Nested create API and foreign key |
| ECU-FR-002 | ECU identifiers shall be unique within a vehicle. | Unique constraint and stable conflict |
| ECU-FR-003 | The platform shall list and retrieve ECUs with bounded pagination. | List/detail APIs and OpenAPI test |
| ECU-FR-004 | An ECU shall expose type, lifecycle state, memory, faults, and version. | Aggregate schema and response |
| ECU-FR-005 | Memory cells shall use unique 16-bit addresses and byte values. | Pydantic validation tests |
| ECU-FR-006 | Fault codes shall be canonical and unique per ECU state. | Fault validation tests |
| ECU-FR-007 | Confirmed critical faults shall require the fault lifecycle state. | Cross-field invariant test |
| ECU-FR-008 | State replacement shall reject stale versions and allow exact retries. | Concurrency/idempotency tests |
| ECU-FR-009 | Creation and state updates shall emit versioned outbox events. | Service atomicity tests |
| ECU-FR-010 | Creation and state updates shall be auditable without copying full state into audit details. | Audit evidence tests |
| ECU-FR-011 | Read and management operations shall use independent permissions. | RBAC and OpenAPI dependencies |

## Non-Functional Requirements

| ID | Requirement | Verification |
|---|---|---|
| ECU-NFR-001 | State payloads shall be bounded to protect API and storage resources. | 256 cells, 64 faults, bounded strings |
| ECU-NFR-002 | Persistence, outbox, and audit writes shall share one database transaction. | Service tests and endpoint commit boundary |
| ECU-NFR-003 | Public failures shall use the global stable error envelope. | Application error handler and contract tests |
| ECU-NFR-004 | The aggregate shall remain protocol-independent. | Architecture review |
| ECU-NFR-005 | The implementation shall pass pytest, Ruff, and strict mypy. | Local and CI quality gates |
