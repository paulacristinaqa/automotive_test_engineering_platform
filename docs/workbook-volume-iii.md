# ATEP Volume III — ECU Simulator Engineering Workbook

**Document status:** Living document — Increments III-1 through III-4 implemented
**Language:** English
**Last updated:** 2026-08-24
**Repository:** `paulacristinaqa/automotive_test_engineering_platform`

## 1. Document Purpose

This workbook records the engineering decisions, requirements, implementation evidence, verification
strategy, risks, and learning opportunities for Volume III. It is both a portfolio artifact and a
maintainable technical record for future ECU, CAN, and diagnostics development.

## 2. Document Control

| Field | Value |
|---|---|
| Volume | III — ECU Simulator |
| Baseline | Increments III-1 through III-4 |
| Architecture style | Modular monolith with transactional domain services |
| Primary runtime | Python 3.12, FastAPI, SQLAlchemy, PostgreSQL |
| Quality gates | pytest, Ruff, strict mypy, Alembic migration checks |

## 3. Revision History

| Release | Date | Change |
|---|---|---|
| 0.1.0 | 2026-08-24 | Added ECU aggregate, lifecycle, memory, faults, API, RBAC, audit, outbox, migration, and tests. |
| 0.2.0 | 2026-08-24 | Added logical time, cyclic scheduling, reset modes, replay evidence, APIs, and tests. |
| 0.3.0 | 2026-08-24 | Added versioned behavior profiles, profile APIs, deterministic state transitions, migration, and tests. |
| 0.4.0 | 2026-08-24 | Added memory regions, reset persistence, snapshots, seeded corruption, APIs, migration, and tests. |

## 4. Scope and Boundaries

### 4.1 Included

- ECU identity unique within a vehicle.
- Nine initial ECU types and six lifecycle states.
- Bounded byte-addressable memory cells.
- Explicit, typed, and bounded fault records.
- Optimistic state versioning and idempotent exact retries.
- Nested REST APIs, safe pagination, and type filtering.
- Independent read/manage permissions.
- Transactional audit and outbox evidence.
- Per-ECU logical time, cyclic task schedules, and boot counters.
- Idempotent advance/reset commands with persisted execution evidence.
- Versioned profiles with allowed schedules, bounded initial state, and deterministic transitions.
- Volatile/non-volatile regions, checksummed snapshots, and seeded corruption evidence.

### 4.2 Deferred

- Firmware or instruction execution.
- CAN, CAN FD, LIN, Ethernet, and gateway routing.
- UDS/OBD-II services, DTC aging, security access, and flashing.
- Full binary firmware images and unrestricted memory dumps.
- Time-based fault injection and healing.

## 5. Architecture

The ECU domain is a separate module under `atep.ecus`. Its public API is nested beneath a vehicle,
while its database table has a foreign key to the vehicle aggregate. The ECU state is intentionally
protocol-independent: later CAN and UDS modules will reference the ECU rather than redefine it.

Request flow: authenticated client → FastAPI router → RBAC dependency → ECU domain service →
PostgreSQL aggregate + audit record + transactional outbox event → HTTP response.

## 6. Domain Model

An ECU contains `vehicle_id`, `identifier`, `display_name`, `ecu_type`, `operational_state`, `memory`,
`faults`, memory regions, cyclic tasks, profile version, behavior state, logical time, boot count,
`version`, and
timestamps. Memory has at most 256
cells, each with a 16-bit address and an
8-bit value. Faults have a canonical code, severity, pending/confirmed status, and description.

The lifecycle contains offline, booting, running, degraded, fault, and shutdown. A confirmed critical
fault cannot coexist with a non-fault lifecycle state. This protects the simulator from representing
an obviously contradictory safety state.

Each cyclic task has a unique canonical ID, a period from 1 to 60,000 milliseconds, and an offset
smaller than its period. A maximum of 32 tasks keeps configuration and execution evidence bounded.

## 7. Public API and Security

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/api/v1/vehicles/{vehicle_id}/ecus` | `ecus:manage` | Create one ECU. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecus` | `ecus:read` | List and filter ECUs. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}` | `ecus:read` | Retrieve one ECU. |
| PUT | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/state` | `ecus:manage` | Replace versioned ECU state. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/simulation/advance` | `ecus:manage` | Advance logical time and summarize due tasks. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/reset` | `ecus:manage` | Execute a deterministic reset mode. |
| GET | `/api/v1/ecu-profiles` | `ecus:read` | List versioned behavior profiles. |
| GET | `/api/v1/ecu-profiles/{ecu_type}` | `ecus:read` | Inspect one profile contract. |
| POST/GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/memory/snapshots` | `ecus:manage` / `ecus:read` | Create or list memory snapshots. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/memory/snapshots/{snapshot_id}/restore` | `ecus:manage` | Restore a versioned snapshot. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/memory/corrupt` | `ecus:manage` | Apply deterministic seeded bit flips. |

The Android Automotive client continues to access only the public ATEP API. It never connects to
PostgreSQL or RabbitMQ directly. Stable errors include `ecu_not_found`,
`ecu_identifier_already_exists`, and `ecu_state_version_conflict`.

## 8. Consistency and Evidence

Creation and state replacement add audit and outbox rows in the same transaction as the aggregate.
State mutation locks the ECU row and compares `expected_version`. Exact replay of the preceding state
is accepted as idempotent; a different stale state is rejected. Audit evidence records counts and
identity but excludes complete memory and fault payloads to reduce sensitive or excessive logging.

### 8.1 Deterministic Scheduling and Reset

The scheduler counts due executions over `(previous_time, new_time]` using arithmetic, not loops over
every millisecond, and never real-time sleep. Each result reports count and first and last due times
per task. Response size therefore follows configured task count rather than elapsed cycles.

Reset durations are fixed: soft 10 ms, hard 100 ms, and power cycle 500 ms. Reset increments the boot
counter, advances logical time, and becomes offline unless a confirmed critical fault requires fault
state. Soft reset preserves memory; hard and power-cycle reset restore volatile cells to their region
reset value while preserving non-volatile cells. Fault records remain unchanged.

### 8.2 Profile Execution

The immutable registry defines a version, allowed task schedules, initial behavior state, and a
state effect for every task. Creation applies defaults when callers omit them. State replacement
rejects unknown task IDs, modified schedules, and unknown state keys. During logical-time advance,
aggregated execution counts update integer counters once; no wall-clock or protocol adapter is used.

### 8.3 Memory Persistence and Evidence

Regions are non-overlapping and every initialized sparse cell belongs to exactly one region. Soft
reset preserves all cells; hard and power-cycle reset restore volatile cells to their region reset
value while retaining non-volatile cells. Snapshots contain no more than 256 cells and use a
canonical SHA-256 checksum. Audit records store checksum and counts rather than full memory images.
Seeded corruption flips a bounded number of bits and persists command identity for exact replay.

## 9. Functional Requirements

The authoritative catalogue is `docs/requirements-volume-iii.md`. III-1 covers the aggregate, III-2
covers deterministic execution and reset, III-3 covers versioned profiles, and III-4 covers memory
regions, snapshots, persistence, and corruption.

## 10. Architecture Decisions

### ADR-ECU-001 — Establish a Protocol-Independent ECU Aggregate

CAN and UDS will depend on a single ECU identity and state model. This prevents protocol modules from
creating incompatible controller representations.

### ADR-ECU-002 — Model Memory as a Bounded Sparse Byte Map

A sparse address/value list is easy to validate, serialize, and inspect. It supports early tests while
avoiding the resource cost and ambiguity of arbitrary binary blobs.

### ADR-ECU-003 — Make Faults Explicit Domain Data

Faults are not hidden flags. Canonical codes, severity, confirmation status, and descriptions provide
traceable inputs for later DTC, diagnostics, test generation, and root-cause analysis.

### ADR-ECU-004 — Use Whole-State Optimistic Replacement First

One versioned command gives deterministic conflict behavior and atomic evidence. Fine-grained memory
and fault commands can be introduced later when their timing semantics are defined.

### ADR-ECU-005 — Use Logical Time and Aggregated Schedule Evidence

Wall-clock scheduling would make tests slow and nondeterministic. Arithmetic task summaries provide
due-cycle evidence with bounded storage and no dependency on host performance.

### ADR-ECU-006 — Preserve State Until Memory Regions Exist

Clearing state before defining volatile and non-volatile regions would invent behavior. III-2
therefore preserved all memory; III-4 supersedes that transitional rule with explicit, region-driven
persistence semantics.

### ADR-ECU-007 — Keep Behavior Profiles Immutable and Protocol-Independent

Profiles are source-controlled contracts rather than mutable database configuration. This makes
tests reproducible and reviewable. CAN production, UDS diagnostics, and continuous physical models
remain outside the profile registry and will integrate through later explicit boundaries.

### ADR-ECU-008 — Make Memory Persistence Region-Driven

Reset behavior follows explicit region kind rather than address conventions. This avoids hidden
assumptions, preserves backward compatibility through `legacy_nvm`, and makes volatile-state tests
portable across ECU types.

### ADR-ECU-009 — Use Checksums and Seeds for Reproducible Memory Evidence

Canonical checksums identify snapshot content without copying complete memory into audit logs. An
explicit corruption seed, bounded flip count, optimistic version, and persisted command ID make
fault injection repeatable and retry-safe.

## 11. Verification Catalogue

| Test | Objective | Level |
|---|---|---|
| Valid ECU creation | Prove identity, defaults, ownership, audit, and event creation. | Service |
| Duplicate identifier | Return one stable conflict within the same vehicle. | Service/integration |
| Vehicle isolation | Prevent retrieving an ECU through a different vehicle. | API/integration |
| Pagination bounds | Prevent unbounded list reads and excessive offsets. | Contract/API |
| Type filter | Return only ECUs of the requested type. | Service/integration |
| Memory byte bounds | Reject negative addresses, addresses above 65535, and values above 255. | Schema |
| Unique memory addresses | Reject ambiguous duplicate cell updates. | Schema |
| Fault code normalization | Normalize valid codes and reject unsafe formats. | Schema |
| Unique fault codes | Reject duplicate faults in one state. | Schema |
| Critical fault invariant | Require fault state for a confirmed critical fault. | Schema |
| Successful state replacement | Increment version and persist complete requested state. | Service |
| Exact retry | Return the current aggregate without duplicate evidence. | Service |
| Stale conflicting update | Return HTTP 409 with the current version. | Service/API |
| Read RBAC | Return HTTP 403 without `ecus:read`. | API/integration |
| Manage RBAC | Return HTTP 403 without `ecus:manage`. | API/integration |
| Atomic outbox | Roll back aggregate and event together on transaction failure. | Integration |
| Audit minimization | Ensure full memory and fault state is absent from audit details. | Service |
| OpenAPI publication | Prove paths, schemas, filters, and safe limits are published. | Contract |
| Migration upgrade/downgrade | Prove schema lifecycle on PostgreSQL. | Integration |

## 11.1 III-2 Verification

| Test | Objective | Level |
|---|---|---|
| Deterministic schedule | Reproduce task counts and due boundaries from the same inputs. | Service |
| Large advance bound | Keep output proportional to tasks rather than elapsed cycles. | Service |
| Offline execution rejection | Prevent cyclic execution outside running/degraded states. | Service/API |
| Advance exact retry | Prevent logical time and version from advancing twice. | Service |
| Command-ID conflict | Reject reuse of an ID with a different command. | Service/API |
| Reset duration matrix | Verify fixed soft, hard, and power-cycle durations. | Unit/service |
| Reset preservation | Prove memory and faults remain unchanged in III-2. | Service |
| Reset boot counter | Increment boot count exactly once, including after retry. | Service |
| Critical reset invariant | Keep fault state while a confirmed critical fault remains. | Service |

## 11.2 III-3 Verification

| Test | Objective | Level |
|---|---|---|
| Profile coverage | Publish a versioned profile for every supported ECU type. | Unit/contract |
| Distinct controller profiles | Verify motor, battery, body, gateway, and ABS safety schedules differ. | Unit |
| Creation defaults | Apply profile tasks and initial state when omitted. | Service |
| Unsupported task rejection | Reject task IDs outside the ECU type contract. | Service/API |
| Schedule drift rejection | Reject changed periods or offsets for a known task. | Service/API |
| State-key rejection | Prevent unbounded or unknown behavior-state fields. | Service/API |
| Deterministic transition | Derive counter changes from aggregated task-run counts. | Service |
| Profile RBAC | Require `ecus:read` for catalogue and detail endpoints. | API/integration |
| OpenAPI publication | Publish profile paths and typed schemas. | Contract |

## 11.3 III-4 Verification

| Test | Objective | Level |
|---|---|---|
| Region overlap | Reject ambiguous memory ownership. | Schema |
| Unassigned cell | Require every initialized cell to belong to one region. | Schema |
| Soft reset persistence | Preserve volatile and non-volatile cells. | Service |
| Hard reset persistence | Reset volatile cells and preserve non-volatile cells. | Service |
| Power-cycle persistence | Apply the same defined volatile-memory rule. | Service |
| Snapshot checksum | Produce the same checksum for canonical memory content. | Service |
| Snapshot restore conflict | Reject stale expected versions. | Service/API |
| Seeded corruption | Reproduce the same bit changes from the same state and seed. | Service |
| Corruption replay | Avoid applying an exact command twice. | Service |
| Memory RBAC and OpenAPI | Publish protected, typed memory endpoints. | Contract/integration |

## 12. Implemented Evidence

- `src/atep/ecus/` contains models, schemas, services, and routers.
- Migrations `0018_ecu_aggregate`, `0019_ecu_execution_clock`, and
  `0020_ecu_behavior_profiles`, and `0021_ecu_memory_regions` own the database schema.
- Permission catalogue contains `ecus:read` and `ecus:manage`.
- Events are `atep.ecu.created.v1` and `atep.ecu.state.updated.v1`.
- Simulation events are `atep.ecu.simulation.advanced.v1` and `atep.ecu.reset.completed.v1`.
- Memory events cover snapshot creation/restoration and deterministic corruption.
- Automated tests cover validation, atomic evidence, concurrency, idempotency, permissions, and API contracts.

## 13. Risks and Technical Debt

- JSON state is practical for the baseline but may require normalized history tables for large traces.
- Whole-state replacement is not intended for high-frequency RAM writes.
- Coordination profiles for door, ADAS, climate, and lighting intentionally share a baseline and
  need specialization in later scenario-driven work.
- Snapshot retention limits and deletion policy require an enterprise storage decision.
- Fault-to-DTC mapping belongs to the Diagnostics boundary and is not implemented here.

## 14. Roadmap

The next increment adds fault activation lifecycle, debouncing, latching, healing, and a future DTC
bridge. Later increments add CAN contracts and multi-ECU scenarios. See `docs/roadmap-volume-iii.md`.

## 15. Study Exercises

1. Trace an ECU creation from request validation to database, audit, and outbox rows.
2. Explain why an exact retry is safe but a different stale state must fail.
3. Add a schema test for the 257th memory cell and interpret the global validation response.
4. Compare the implemented reset behavior for volatile and non-volatile memory across all modes.
5. Propose how a BMS ECU fault should later become a UDS DTC without coupling the two modules.
6. Calculate the due times for a 100 ms task with a 20 ms offset over two consecutive advances.
7. Explain how III-4 safely supersedes the transitional III-2 memory-preservation rule.
8. Compare the battery and gateway schedules and explain why both remain protocol-independent.
9. Calculate the behavior-state counters after advancing a new battery ECU by 2,100 ms.
10. Design a dedicated ADAS profile without adding camera or CAN dependencies to the registry.
11. Model RAM and EEPROM regions for a BMS ECU and predict each reset mode's result.
12. Explain why snapshot audits contain checksums and counts instead of the complete memory image.
13. Design a corruption campaign that remains reproducible across CI machines.
