# ATEP Volume III — ECU Simulator Engineering Workbook

**Document status:** Living document — Increment III-1 implemented  
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
| Baseline | Increment III-1 |
| Architecture style | Modular monolith with transactional domain services |
| Primary runtime | Python 3.12, FastAPI, SQLAlchemy, PostgreSQL |
| Quality gates | pytest, Ruff, strict mypy, Alembic migration checks |

## 3. Revision History

| Release | Date | Change |
|---|---|---|
| 0.1.0 | 2026-08-24 | Added ECU aggregate, lifecycle, memory, faults, API, RBAC, audit, outbox, migration, and tests. |

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

### 4.2 Deferred

- Firmware or instruction execution.
- Logical execution cycles and task scheduling.
- CAN, CAN FD, LIN, Ethernet, and gateway routing.
- UDS/OBD-II services, DTC aging, security access, and flashing.
- Persistent memory regions and reset semantics.
- Time-based fault injection and healing.

## 5. Architecture

The ECU domain is a separate module under `atep.ecus`. Its public API is nested beneath a vehicle,
while its database table has a foreign key to the vehicle aggregate. The ECU state is intentionally
protocol-independent: later CAN and UDS modules will reference the ECU rather than redefine it.

Request flow: authenticated client → FastAPI router → RBAC dependency → ECU domain service →
PostgreSQL aggregate + audit record + transactional outbox event → HTTP response.

## 6. Domain Model

An ECU contains `vehicle_id`, `identifier`, `display_name`, `ecu_type`, `operational_state`, `memory`,
`faults`, `version`, and timestamps. Memory has at most 256 cells, each with a 16-bit address and an
8-bit value. Faults have a canonical code, severity, pending/confirmed status, and description.

The lifecycle contains offline, booting, running, degraded, fault, and shutdown. A confirmed critical
fault cannot coexist with a non-fault lifecycle state. This protects the simulator from representing
an obviously contradictory safety state.

## 7. Public API and Security

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/api/v1/vehicles/{vehicle_id}/ecus` | `ecus:manage` | Create one ECU. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecus` | `ecus:read` | List and filter ECUs. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}` | `ecus:read` | Retrieve one ECU. |
| PUT | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/state` | `ecus:manage` | Replace versioned ECU state. |

The Android Automotive client continues to access only the public ATEP API. It never connects to
PostgreSQL or RabbitMQ directly. Stable errors include `ecu_not_found`,
`ecu_identifier_already_exists`, and `ecu_state_version_conflict`.

## 8. Consistency and Evidence

Creation and state replacement add audit and outbox rows in the same transaction as the aggregate.
State mutation locks the ECU row and compares `expected_version`. Exact replay of the preceding state
is accepted as idempotent; a different stale state is rejected. Audit evidence records counts and
identity but excludes complete memory and fault payloads to reduce sensitive or excessive logging.

## 9. Functional Requirements

The authoritative catalogue is `docs/requirements-volume-iii.md`. III-1 covers ownership, uniqueness,
retrieval, bounded state, consistency invariants, optimistic concurrency, RBAC, events, and audit.

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

## 12. Implemented Evidence

- `src/atep/ecus/` contains models, schemas, services, and routers.
- Migration `0018_ecu_aggregate` owns the database schema.
- Permission catalogue contains `ecus:read` and `ecus:manage`.
- Events are `atep.ecu.created.v1` and `atep.ecu.state.updated.v1`.
- Automated tests cover validation, atomic evidence, concurrency, idempotency, permissions, and API contracts.

## 13. Risks and Technical Debt

- JSON state is practical for the baseline but may require normalized history tables for large traces.
- Whole-state replacement is not intended for high-frequency RAM writes.
- ECU type profiles are not yet behaviorally distinct.
- Memory persistence across reset is undefined until III-4.
- Fault-to-DTC mapping belongs to the Diagnostics boundary and is not implemented here.

## 14. Roadmap

The next increment adds a deterministic logical clock, cyclic tasks, and reset semantics without
wall-clock sleeps. Later increments add ECU profiles, memory regions, fault lifecycle, CAN contracts,
and multi-ECU scenarios. See `docs/roadmap-volume-iii.md`.

## 15. Study Exercises

1. Trace an ECU creation from request validation to database, audit, and outbox rows.
2. Explain why an exact retry is safe but a different stale state must fail.
3. Add a schema test for the 257th memory cell and interpret the global validation response.
4. Design reset behavior for volatile and non-volatile memory without implementing it.
5. Propose how a BMS ECU fault should later become a UDS DTC without coupling the two modules.

## 16. Workbook Maintenance Checklist

- Update requirement status and evidence with every increment.
- Add each architecture decision before introducing its implementation dependency.
- Record public event names and stable errors.
- Keep test objectives aligned with automated test names.
