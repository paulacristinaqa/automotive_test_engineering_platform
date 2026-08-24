# ATEP Volume III — ECU Simulator Engineering Workbook

**Document status:** Volume III baseline — Increments III-1 through III-7 implemented
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
| Baseline | Increments III-1 through III-7 |
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
| 0.5.0 | 2026-08-24 | Added logical-time fault lifecycle, debounce, healing, latching, clear, DTC projection, APIs, and tests. |
| 0.6.0 | 2026-08-24 | Added typed signal contracts, publication, gateway routes, atomic transfer, migration, APIs, and tests. |
| 0.7.0 | 2026-08-24 | Added persisted multi-ECU scenarios, logical-clock diagnostics, bounded metrics, deterministic failure campaigns, APIs, migration, and tests. |

## 4. Scope and Boundaries

### 4.1 Included

- ECU identity unique within a vehicle.
- Nine initial ECU types and six lifecycle states.
- Bounded memory with volatile/non-volatile regions, snapshots, and seeded corruption.
- Bounded fault records with logical-time confirmation, healing, latching, clear, and DTC intent.
- Typed produced/consumed signals, logical-time publication, and gateway-owned routing hooks.
- Bounded multi-ECU scenarios, logical-clock diagnostics, aggregate metrics, and repeatable campaigns.
- Optimistic state versioning and idempotent exact retries.
- Nested REST APIs, safe pagination, and type filtering.
- Independent read/manage permissions.
- Transactional audit and outbox evidence.
- Per-ECU logical time, cyclic task schedules, and boot counters.
- Idempotent advance/reset commands with persisted execution evidence.
- Versioned profiles with allowed schedules, bounded initial state, and deterministic transitions.

### 4.2 Deferred

- Firmware or instruction execution.
- CAN, CAN FD, LIN, Ethernet frames, DBC encoding, arbitration, and bus simulation.
- UDS/OBD-II services, assigned DTC numbers, status-byte aging, security access, and flashing.
- Full binary firmware images and unrestricted memory dumps.
- Autonomous sensor-condition evaluation and continuous fault-trigger rules.

## 5. Architecture

The ECU domain is a separate module under `atep.ecus`. Its public API is nested beneath a vehicle,
while its database table has a foreign key to the vehicle aggregate. The ECU state is intentionally
protocol-independent: later CAN and UDS modules will reference the ECU rather than redefine it.

Request flow: authenticated client → FastAPI router → RBAC dependency → ECU domain service →
PostgreSQL aggregate + audit record + transactional outbox event → HTTP response.

The scenario orchestrator is a vehicle-scoped application service above the ECU primitives. It
serializes execution-ID claims with a vehicle row lock and performs all ordered actions in the API
transaction. Its diagnostics use ECU logical clocks; host resource sampling and wall-clock timing are
not part of simulated truth.

## 6. Domain Model

An ECU contains `vehicle_id`, `identifier`, `display_name`, `ecu_type`, `operational_state`, `memory`,
`faults`, semantic signals, memory regions, cyclic tasks, profile version, behavior state, logical time, boot count,
`version`, and
timestamps. Memory has at most 256
cells, each with a 16-bit address and an
8-bit value. Faults have a canonical code, severity, pending/confirmed/healed status, description,
bounded debounce counters, logical timestamps, thresholds, active state, and latch policy.

Signals are bounded to 64 contracts. Each contract declares a canonical name, produced/consumed
direction, strict data type, optional unit/bounds/cycle time, current value, and ECU logical update
time. Names are unique per direction, allowing an ECU to consume and produce the same semantic name
without ambiguity.

The lifecycle contains offline, booting, running, degraded, fault, and shutdown. A confirmed critical
fault cannot coexist with a non-fault lifecycle state. This protects the simulator from representing
an obviously contradictory safety state.

Each cyclic task has a unique canonical ID, a period from 1 to 60,000 milliseconds, and an offset
smaller than its period. A maximum of 32 tasks keeps configuration and execution evidence bounded.

An ECU scenario execution stores a request hash, bounded request, bounded aggregate result, iteration
count, actor, and timestamps. One request has 1 to 32 actions, references at most 16 ECUs, repeats at
most eight times, and returns at most 256 action summaries. Results include before/after counts and
per-ECU clock lag rather than complete memory, signal-value, or fault payloads.

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
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/faults/observe` | `ecus:manage` | Record one detected or absent observation. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/faults/{fault_code}/clear` | `ecus:manage` | Explicitly clear an active fault. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/faults/dtc-candidates` | `ecus:read` | Read diagnostic-intent projections. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/signals/{signal_name}/publish` | `ecus:manage` | Publish one produced signal value. |
| POST/GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/signal-routes` | `ecus:manage` / `ecus:read` | Create or list gateway routes. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/signal-routes/{route_id}/transfer` | `ecus:manage` | Transfer a routed value atomically. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecu-scenarios/execute` | `ecus:manage` | Execute a bounded deterministic scenario or campaign. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecu-scenarios` | `ecus:read` | List persisted scenario evidence safely. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecu-scenarios/{execution_id}` | `ecus:read` | Inspect one scenario execution. |

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

### 8.4 Fault Lifecycle and Diagnostic Intent

Each observation is evaluated at the ECU's current logical time. Consecutive detections increment
the occurrence counter and confirm the fault at its configured threshold. Consecutive absences
increment the healing counter and heal non-latched faults at their configured threshold. Confirmed
critical faults force the ECU into fault state; after the final critical fault heals or is cleared,
the ECU moves to degraded state for explicit recovery handling.

Latched confirmed faults ignore automatic healing and require an explicit clear command. Observation
and clear commands persist command identity, so exact retries do not mutate counters or versions
twice. Audit and outbox evidence includes the transition, code, status, and bounded counts, not the
complete fault collection. DTC candidates express diagnostic intent but deliberately contain no UDS
types or assigned DTC numbers.

### 8.5 Signal Publication and Gateway Routes

Signal publication changes a produced contract under a row lock and expected ECU version. The
published timestamp is the ECU logical clock, not host time. Persisted command identity makes exact
retries safe. Evidence includes contract identity, type, direction, and logical time but excludes the
physical value.

Only a gateway ECU can own a route. Its source and target are distinct ECUs in the same vehicle; the
source contract must be produced, the target consumed, and type/unit must match. Transfer locks both
ECUs, compares source and target versions, copies the source value to the target at target logical
time, and increments only the target version. This is an adapter hook: no CAN ID, frame, DBC,
arbitration, bitrate, or bus timing exists in the ECU domain.

### 8.6 Scenario Orchestration and Timing Diagnostics

Scenario actions call the existing advance, fault, corruption, publication, and transfer services.
The orchestrator supplies each primitive's current version and derives a stable command ID from the
execution ID, iteration, and action index. Corruption seeds derive from the declared base seed and
the same logical coordinates, making a campaign repeatable from an identical initial state.

Exact request replay returns persisted evidence without executing actions again; changed reuse of an
execution ID fails with `ecu_scenario_execution_conflict`. Before/after evidence counts ECUs, memory
cells, semantic signals, active faults, routes, and aggregate versions. Timing evidence reports the
minimum and maximum ECU clocks, skew, synchronization state, and lag for at most 16 ECUs. Aggregate
audit and outbox evidence excludes action requests, memory contents, physical values, and fault sets.

## 9. Functional Requirements

The authoritative catalogue is `docs/requirements-volume-iii.md`. III-1 covers the aggregate, III-2
covers deterministic execution and reset, III-3 covers versioned profiles, III-4 covers memory
regions, snapshots, persistence, and corruption, III-5 covers fault lifecycle and DTC intent, and
III-6 covers semantic signal contracts and gateway routing hooks. III-7 covers multi-ECU scenarios,
logical-clock diagnostics, bounded resource evidence, and deterministic campaigns.

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

### ADR-ECU-010 — Use Logical-Time Observations for Fault Debounce

Wall-clock timers make simulations host-dependent. Explicit detected/absent observations evaluated
against bounded thresholds at the ECU logical time make confirmation and healing reproducible.

### ADR-ECU-011 — Keep the DTC Bridge Protocol-Independent

The ECU owns fault truth, while Diagnostics will own UDS identifiers, status bytes, and services.
Publishing diagnostic intent prevents both domains from creating competing fault representations.

### ADR-ECU-012 — Separate Semantic Signals from CAN Transport

ECUs own physical meaning, direction, value constraints, and logical timestamps. Volume IV owns CAN
identifiers, encoding, frames, arbitration, bus timing, and network faults. This allows alternate
Ethernet or simulation adapters to reuse the same ECU contract.

### ADR-ECU-013 — Make Gateway Routing Explicit and Version-Guarded

Persistent routes provide reviewable source/target ownership. Matching type/unit rules prevent
implicit conversion, while source and target versions expose stale transfers rather than silently
copying a different value.

### ADR-ECU-014 — Orchestrate Existing Commands Instead of Duplicating ECU Behavior

Scenario actions call the already validated ECU primitives and calculate optimistic versions at the
point of execution. This keeps fault, memory, timing, and signal invariants in one implementation.

### ADR-ECU-015 — Treat Logical Clocks as Timing Diagnostics

Clock skew and lag come only from ECU simulation clocks. Host CPU/GPU load and wall-clock duration
describe the test environment, not vehicle behavior, and therefore never affect scenario results.

### ADR-ECU-016 — Bound and Minimize Campaign Evidence

Iteration, action, and ECU limits cap response and transaction size. Aggregate evidence retains
identities, counts, versions, and skew while excluding memory images, physical values, and full faults.

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

## 11.4 III-5 Verification

| Test | Objective | Level |
|---|---|---|
| Confirmation debounce | Confirm only when the configured detection threshold is reached. | Service |
| Healing debounce | Heal only after the configured consecutive-absence threshold. | Service |
| Logical timestamps | Derive first-seen, last-seen, confirmed, and healed evidence from ECU time. | Service |
| Critical transition | Move an ECU to fault state when a critical fault confirms. | Service |
| Latched absence | Preserve an active confirmed latch despite absent observations. | Service |
| Explicit clear | Heal and unlatch a fault only through an authorized clear command. | Service/API |
| Exact replay | Avoid incrementing lifecycle counters or versions twice. | Service |
| Policy conflict | Reject policy changes while one fault activation is active. | Service/API |
| DTC projection | Publish protocol-independent diagnostic intent without UDS coupling. | Unit/contract |
| Fault RBAC and OpenAPI | Publish protected, typed lifecycle endpoints. | Contract/integration |

## 11.5 III-6 Verification

| Test | Objective | Level |
|---|---|---|
| Signal bound | Reject the 65th contract. | Schema |
| Strict data type | Reject coercion and values that disagree with the declaration. | Schema |
| Physical bounds | Reject values below minimum or above maximum. | Schema/service |
| Direction uniqueness | Reject duplicate names within one direction. | Schema |
| Publication clock | Record the ECU logical time without wall-clock access. | Service |
| Publication replay | Avoid changing value or version twice. | Service |
| Gateway ownership | Reject route creation by a non-gateway ECU. | Service/API |
| Route compatibility | Require produced-to-consumed direction plus matching type and unit. | Service |
| Transfer concurrency | Reject stale source or target versions. | Service/API |
| Atomic transfer | Copy the value and commit target, audit, command, and event together. | Integration |
| Signal RBAC/OpenAPI | Publish protected, typed, safely paginated endpoints. | Contract/integration |
| Transport boundary | Verify no CAN ID, frame, DBC, arbitration, or bitrate type is imported. | Review |

## 11.6 III-7 Verification

| Test | Objective | Level |
|---|---|---|
| Action contract | Require kind-specific fields and reject the 33rd action. | Schema |
| ECU scope | Reject a scenario referencing more than 16 ECUs. | Schema |
| Campaign bound | Reject the ninth iteration and cap results at 256 summaries. | Schema |
| Ordered orchestration | Execute existing ECU commands in declared iteration/action order. | Service |
| Deterministic seed | Derive the same corruption seed and command identity from the same coordinates. | Unit/service |
| Timing diagnostic | Report logical minimum, maximum, skew, synchronization, and lag. | Service |
| Resource evidence | Compare bounded before/after aggregate counts without host sampling. | Service |
| Exact replay | Return persisted evidence without applying actions twice. | Service/API |
| Execution-ID conflict | Return one stable conflict for a changed request. | Service/API |
| Concurrent claim | Serialize one vehicle's scenario identifiers with a row lock. | Design/integration |
| Atomic campaign | Commit primitive mutations, scenario, audit, and outbox together. | Integration |
| Evidence minimization | Exclude action payloads, physical values, memory, and full faults. | Service |
| Scenario RBAC/OpenAPI | Publish protected execute, list, and detail endpoints with safe limits. | Contract/integration |
| Protocol boundary | Keep CAN frames, DBC, UDS, and wall-clock schedulers outside the orchestrator. | Review |

## 12. Implemented Evidence

- `src/atep/ecus/` contains models, schemas, services, and routers.
- Migrations `0018_ecu_aggregate`, `0019_ecu_execution_clock`, and
  `0020_ecu_behavior_profiles`, `0021_ecu_memory_regions`, `0022_ecu_signal_contracts`, and
  `0023_ecu_scenarios` own the database schema.
- Permission catalogue contains `ecus:read` and `ecus:manage`.
- Events are `atep.ecu.created.v1` and `atep.ecu.state.updated.v1`.
- Simulation events are `atep.ecu.simulation.advanced.v1` and `atep.ecu.reset.completed.v1`.
- Memory events cover snapshot creation/restoration and deterministic corruption.
- Fault events use `atep.ecu.fault.lifecycle.changed.v1` for observation and explicit-clear evidence; signal events cover publication, route creation, and routed transfer without physical values in audit evidence.
- Scenario completion uses `atep.ecu.scenario.completed.v1` with bounded counts and clock skew.
- Automated tests cover validation, atomic evidence, concurrency, idempotency, permissions, and API contracts.

## 13. Risks and Technical Debt

- JSON state is practical for the baseline but may require normalized history tables for large traces.
- Whole-state replacement is not intended for high-frequency RAM writes.
- Coordination profiles for door, ADAS, climate, and lighting intentionally share a baseline and
  need specialization in later scenario-driven work.
- Snapshot retention limits and deletion policy require an enterprise storage decision.
- Actual DTC identifiers, status-byte semantics, and aging belong to the Diagnostics boundary.
- Cross-route lock ordering must be hardened before high-concurrency multi-gateway execution.
- Unit conversion is intentionally absent; routes currently require exact unit equality.
- Vehicle-level serialization is intentionally conservative; later scale work may introduce ordered
  multi-aggregate locks after measuring real campaign contention.
- Scenario definitions are request-persisted execution evidence, not yet a reusable catalogue with
  approval workflow or scheduled execution.

## 14. Roadmap

The initial Volume III baseline is complete. The recommended next development starts Volume IV with a
protocol-independent CAN network aggregate, bounded frame contracts, topology, and deterministic bus
submission semantics. DBC encoding, arbitration, CAN FD, fault injection, and timing follow in later
Volume IV increments. See `docs/roadmap-volume-iii.md`.

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
14. Trace three detected observations and two absent observations through configurable thresholds.
15. Explain why a latched confirmed fault cannot heal from an absent observation alone.
16. Map a DTC candidate to future UDS responsibilities without assigning a DTC number in the ECU.
17. Model battery temperature as a produced BMS signal and consumed thermal-controller signal.
18. Explain why a gateway route rejects Celsius-to-Kelvin transfer instead of converting silently.
19. Trace publication and transfer versions through an exact retry and one stale-source conflict.
20. Design the future Volume IV adapter that maps a semantic signal to a DBC without changing ECU state.
21. Build a two-ECU scenario and calculate every derived command ID and campaign seed.
22. Compare synchronized ECU clocks with a 250 ms skew and explain the diagnostic result.
23. Prove why aggregate scenario evidence is safer than copying action requests and physical values.
24. Propose a reusable scenario catalogue without weakening immutable execution evidence.
