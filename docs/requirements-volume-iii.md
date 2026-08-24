# ATEP Volume III — ECU Simulator Requirements

Status: Increments III-1 through III-5 implemented.

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
| ECU-FR-012 | Each ECU shall maintain an independent monotonic logical clock. | Advance/reset service tests |
| ECU-FR-013 | Cyclic tasks shall define unique IDs, bounded periods, and offsets smaller than periods. | Schema tests |
| ECU-FR-014 | Advancing time shall calculate due task runs deterministically without wall-clock waits. | Scheduling tests |
| ECU-FR-015 | Advance and reset commands shall persist identifiers and return exact retries idempotently. | Command evidence tests |
| ECU-FR-016 | Cyclic execution shall be restricted to running or degraded ECUs. | Lifecycle conflict test |
| ECU-FR-017 | Soft, hard, and power-cycle resets shall use fixed logical durations. | Reset-mode tests |
| ECU-FR-018 | Reset shall preserve memory and faults until memory-region semantics are introduced. | Reset evidence test |
| ECU-FR-019 | Every supported ECU type shall expose a versioned behavior profile. | Profile registry and OpenAPI tests |
| ECU-FR-020 | Motor, battery, body, gateway, and safety controllers shall have distinct task and state contracts. | Profile definition tests |
| ECU-FR-021 | New ECUs shall receive their profile tasks and initial behavior state when these values are omitted. | Creation-default test |
| ECU-FR-022 | State replacement shall reject unsupported task IDs, schedules, and behavior-state keys. | Profile contract tests |
| ECU-FR-023 | Logical-time advancement shall apply profile transitions from aggregated task-run counts. | Deterministic transition test |
| ECU-FR-024 | Clients shall be able to list and inspect profiles using `ecus:read`. | Profile API contract test |
| ECU-FR-025 | ECU memory shall support non-overlapping volatile and non-volatile regions. | Region validation tests |
| ECU-FR-026 | Hard and power-cycle reset shall restore initialized volatile cells while preserving non-volatile cells. | Reset persistence tests |
| ECU-FR-027 | Soft reset shall preserve both volatile and non-volatile memory. | Reset-mode test |
| ECU-FR-028 | Authorized clients shall create, list, and restore bounded memory snapshots with checksums. | Snapshot service and API tests |
| ECU-FR-029 | Memory corruption shall use an explicit seed and bounded bit-flip count. | Determinism and validation tests |
| ECU-FR-030 | Exact corruption retries shall not mutate memory or version twice. | Command replay test |
| ECU-FR-031 | Fault observations shall use bounded confirmation and healing thresholds. | Lifecycle service tests |
| ECU-FR-032 | Fault timing evidence shall use the ECU logical clock. | Timestamp assertions |
| ECU-FR-033 | Confirmed critical faults shall move the ECU to fault state. | Confirmation transition test |
| ECU-FR-034 | Latched confirmed faults shall require an explicit clear command. | Latch and clear test |
| ECU-FR-035 | Exact lifecycle-command retries shall not increment counters or versions twice. | Replay test |
| ECU-FR-036 | Authorized clients shall read a protocol-independent DTC-candidate projection. | OpenAPI and bridge tests |
| ECU-FR-037 | Fault mutations shall emit minimized audit and versioned outbox evidence atomically. | Service evidence test |

## Non-Functional Requirements

| ID | Requirement | Verification |
|---|---|---|
| ECU-NFR-001 | State payloads shall be bounded to protect API and storage resources. | 256 cells, 64 faults, bounded strings |
| ECU-NFR-002 | Persistence, outbox, and audit writes shall share one database transaction. | Service tests and endpoint commit boundary |
| ECU-NFR-003 | Public failures shall use the global stable error envelope. | Application error handler and contract tests |
| ECU-NFR-004 | The aggregate shall remain protocol-independent. | Architecture review |
| ECU-NFR-005 | The implementation shall pass pytest, Ruff, and strict mypy. | Local and CI quality gates |
| ECU-NFR-006 | Scheduler output shall remain bounded independently of due execution count. | Aggregated task-run summaries |
| ECU-NFR-007 | Deterministic simulation operations shall not call real-time sleep. | Design review and unit tests |
| ECU-NFR-008 | Profile transitions shall remain independent of CAN, UDS, and wall-clock infrastructure. | Boundary review |
| ECU-NFR-009 | Behavior state and published profile metadata shall remain bounded and JSON-compatible. | Schema limits and typed registry |
| ECU-NFR-010 | Snapshot and corruption evidence shall avoid copying complete memory into audit details. | Audit minimization review |
| ECU-NFR-011 | Memory operations shall remain deterministic and independent of host timing. | Seeded service tests |
| ECU-NFR-012 | Fault lifecycle behavior shall remain deterministic and independent of wall-clock timing. | Logical-clock review |
| ECU-NFR-013 | The DTC bridge shall not import UDS types or assign diagnostic codes. | Boundary review |
