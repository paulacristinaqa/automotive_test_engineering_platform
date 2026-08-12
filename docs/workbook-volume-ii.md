# ATEP Volume II — Digital Vehicle Engineering Workbook

**Subtitle:** Domain architecture, deterministic simulation, verification strategy, and engineering evidence  
**Project:** Automotive Test Engineering Platform (ATEP)  
**Document version:** 0.4.0

**Baseline date:** 12 August 2026

**Status:** Living engineering document — Increments II-1 through II-4 implemented
**Language:** English

## 1. Document Purpose

This workbook is the engineering record for Volume II of ATEP. It documents the Digital Vehicle
domain independently from the Core Platform workbook while retaining explicit links to the
authentication, RBAC, persistence, event, audit, and observability services supplied by Volume I.

It is intended to serve as a domain specification, implementation journal, verification catalogue,
architecture-decision record, onboarding guide, and portfolio evidence pack. Statements are marked
as implemented, planned, or target according to repository evidence.

## 2. Document Control

| Field | Value |
|---|---|
| Owner | ATEP Digital Vehicle Engineering |
| Review audience | Automotive software architects, simulation engineers, embedded QA engineers, backend engineers, and technical recruiters |
| Review cadence | At the end of every Volume II increment |
| Source of truth | Repository code, migrations, automated tests, requirements, roadmap, and this workbook |
| Classification | Portfolio / Engineering documentation |

## 3. Revision History

| Version | Date | Change | Verification status |
|---|---|---|---|
| 0.1.0 | 12 August 2026 | II-1: introduced the versioned Digital Vehicle aggregate, safe baseline, component bounds, safety invariants, RBAC, optimistic concurrency, audit, and outbox evidence | Implemented and verified by unit, contract, RBAC, migration, and integration tests |
| 0.2.0 | 12 August 2026 | II-2: added the command-driven simulation clock and persisted `parked → ready → driving → parked` transitions | Implemented and verified by state-machine, replay, idempotency, conflict, and evidence tests |
| 0.3.0 | 12 August 2026 | II-3: added accelerator, brake, and steering actuators plus seeded speed, SOC, and temperature sensors with noise and explicit fault modes | Implemented and verified by bounds, seed, fault, retry, contract, migration, and hosted integration tests |
| 0.4.0 | 12 August 2026 | II-4: coupled road and ambient inputs with battery energy, thermal response, powertrain, regenerative braking, steering, suspension, and lighting | Implemented and verified by scenario, conservation, bounds, migration, and hosted integration tests |

## 4. Scope and Boundaries

### 4.1 Included

- one authoritative digital-state aggregate per registered vehicle;
- operational mode, battery, powertrain, brakes, steering, and lighting;
- deterministic logical time and command-driven transitions;
- bounded accelerator, brake, and steering inputs;
- seeded speed, battery SOC, and battery-temperature readings;
- explicit sensor noise, stuck faults, and offset faults;
- versioned public APIs, deny-by-default RBAC, audit, and transactional outbox evidence;
- persisted command metadata for retry safety and replay;
- compatibility boundary for the future Android Automotive Vehicle Gateway.

### 4.2 Excluded from the Current Baseline

- production-grade multi-body or tyre physics;
- ECU firmware execution, CAN/LIN/Ethernet buses, UDS, OBD-II, and DTC behavior;
- ADAS perception and planning;
- Android VHAL property writes;
- multi-vehicle sessions and distributed simulation scheduling;
- real-time guarantees or hardware-in-the-loop execution.

These capabilities belong to later Volume II increments or subsequent ATEP volumes.

## 5. Architecture

The Digital Vehicle is a bounded domain inside the modular FastAPI application. Clients use only
the public API. PostgreSQL remains the source of truth; Redis and RabbitMQ are infrastructure
services behind Volume I boundaries and are never accessed directly by CarSystemUI.

| Layer | Responsibility | Integration boundary |
|---|---|---|
| CarSystemUI and test automation | Request state changes, simulation transitions, and deterministic steps | REST/HTTPS using OpenAPI contracts |
| FastAPI Digital Vehicle router | Authenticate, authorize, validate, and map public requests | `digital_vehicle:read` and `digital_vehicle:write` |
| Domain service | Enforce invariants, optimistic concurrency, deterministic behavior, and retry identity | Typed commands and one aggregate transaction |
| PostgreSQL | Persist authoritative state, replay metadata, audit, and outbox rows | SQLAlchemy and Alembic behind the service boundary |
| RabbitMQ consumers | Receive versioned integration events after transaction commit | Transactional outbox publication supplied by Volume I |

### 5.1 Domain Aggregate

| Component | Representative state | Key bounds or invariants |
|---|---|---|
| Operational mode | parked, ready, driving, charging, fault | Moving requires driving mode |
| Battery | SOC, SOH, usable energy, voltage, current, temperature, contactors, charging | SOC/SOH 0–100%; energy and temperature bounded; charging requires stationary park state |
| Powertrain | motor, gear, speed, requested and delivered torque | Moving requires enabled motor, valid gear, and closed contactors |
| Brakes | pedal, hydraulic pressure, parking brake, ABS | Moving requires released parking brake |
| Steering | wheel angle and assist | Wheel angle bounded to ±720 degrees |
| Lighting | exterior mode, brake lamps, indicators | Brake lamps follow modeled brake input during steps |
| Suspension | front/rear travel and lateral acceleration | Travel bounded to ±120 mm and lateral acceleration to ±20 m/s² |

### 5.2 Public API

| Operation | Permission | Purpose |
|---|---|---|
| `GET /api/v1/vehicles/{vehicle_id}/state` | `digital_vehicle:read` | Read the current aggregate |
| `PUT /api/v1/vehicles/{vehicle_id}/state` | `digital_vehicle:write` | Replace the complete aggregate using optimistic concurrency |
| `POST /api/v1/vehicles/{vehicle_id}/simulation/transitions` | `digital_vehicle:write` | Execute a deterministic operational-mode transition |
| `POST /api/v1/vehicles/{vehicle_id}/simulation/steps` | `digital_vehicle:write` | Apply actuators, advance logical time, and capture sensor readings |

## 6. Deterministic Simulation Model

### 6.1 Safe Baseline

Vehicle registration creates a parked, stationary state with the motor disabled, contactors open,
parking brake applied, zero torque, and exterior lighting off. The initial aggregate version is one
and logical simulation time is zero milliseconds.

### 6.2 Logical Clock and Transitions

Time advances only when an accepted command supplies an explicit bounded duration. No wall-clock
timer, background simulation loop, GPU, emulator, or cloud service is required. The initial mode
sequence is:

`parked → ready → driving → parked`

Each command is scoped by vehicle and command identifier. Exact retries return the persisted result
without advancing time or duplicating evidence; altered reuse returns a stable conflict.

### 6.3 Sensors and Actuators

Simulation steps accept accelerator position, brake position, steering angle, duration, seed, and
sensor configuration. Accelerator and brake cannot both be positive. Non-zero actuator commands
require driving mode.

The initial bounded model updates speed, torque, hydraulic pressure, steering, brake lamps, battery
SOC, current, and temperature. Speed, SOC, and temperature observations may add deterministic noise
derived from the seed and sensor name. `stuck` reports a configured fixed value; `offset` adds a
configured delta. Faults affect observed readings without silently replacing physical state.

### 6.4 Coupled Dynamics

The II-4 model adds road grade, road roughness, ambient temperature, and ambient light to each
deterministic step. It publishes energy used, regenerative energy recovered, and net energy in Wh;
the three values satisfy `used - recovered = net` at the published precision. Net energy reduces
usable battery energy and SOC, while regenerative recovery remains bounded.

Torque includes grade demand and braking regeneration. Battery temperature combines load heating
and ambient cooling. Steering and speed produce bounded lateral acceleration; roughness, braking,
and acceleration produce front/rear suspension travel. Brake lamps and low-beam behavior follow
brake and ambient-light inputs.

## 7. Consistency, Security, and Evidence

- Every mutation supplies `expected_version`; stale requests return a stable HTTP 409 envelope.
- State rows are locked while commands are evaluated.
- Component schemas carry explicit numeric limits and whole-aggregate safety validation.
- Read and write permissions are independent and deny by default.
- Accepted mutations atomically commit state, replay metadata, audit evidence, and an outbox event.
- Audit records retain identifiers, versions, modes, duration, seed, and bounded readings rather
  than copying secrets or unrestricted payloads.
- Public clients never connect directly to PostgreSQL, Redis, or RabbitMQ.

## 8. Functional Requirements

| ID | Requirement | Evidence |
|---|---|---|
| DV-F-001 | Every vehicle shall own exactly one digital-state aggregate. | Model, migration, registration test |
| DV-F-002 | The aggregate shall represent operational mode, battery, powertrain, brakes, steering, and lighting. | Typed schemas and OpenAPI |
| DV-F-003 | Vehicle registration shall create a deterministic safe baseline. | Service and tests |
| DV-F-004 | Authorized clients shall read and replace the complete state through versioned APIs. | GET/PUT API tests |
| DV-F-005 | Replacement shall validate bounds and cross-component safety invariants. | Schema tests |
| DV-F-006 | Replacement shall use optimistic concurrency and a stable conflict error. | Service and integration tests |
| DV-F-007 | Exact retries shall not duplicate transitions or evidence. | Retry tests |
| DV-F-008 | Real mutations shall atomically persist state, audit, and outbox evidence. | Transaction tests |
| DV-F-009 | Simulation time shall advance only through explicit bounded commands. | Deterministic sequence test |
| DV-F-010 | The initial state machine shall enforce the documented transition sequence. | State-machine tests |
| DV-F-011 | Simulation commands shall be vehicle-scoped and idempotent. | Retry and conflict tests |
| DV-F-012 | Transitions shall retain replay metadata. | Service and integration tests |
| DV-F-013 | Steps shall model bounded accelerator, brake, and steering inputs. | Contract and step tests |
| DV-F-014 | Sensors shall support seeded noise and explicit stuck/offset faults. | Seed and fault tests |
| DV-F-015 | Steps shall be versioned, idempotent, and persisted for replay. | Retry, conflict, migration, and evidence tests |
| DV-F-016 | Steps shall calculate bounded energy use, regeneration, usable energy, and SOC. | Conservation and braking tests |
| DV-F-017 | Thermal response shall combine load generation, ambient cooling, and absolute bounds. | Scenario and boundary tests |
| DV-F-018 | Road and ambient inputs shall influence powertrain, suspension, steering response, and lighting deterministically. | Coupled scenario test |

## 9. Non-Functional Requirements

| ID | Requirement | Evidence |
|---|---|---|
| DV-NF-001 | Read and write access shall use independent deny-by-default permissions. | RBAC tests |
| DV-NF-002 | Numeric inputs shall carry explicit safe bounds and units. | Pydantic tests and documentation |
| DV-NF-003 | Errors shall use the global correlation-aware envelope. | API contract tests |
| DV-NF-004 | Audit details shall remain bounded and exclude complete state copies. | Audit assertions |
| DV-NF-005 | Migrations shall support existing vehicles without cloud infrastructure. | Disposable integration |
| DV-NF-006 | Increments shall pass Ruff, strict mypy, unit/contract, and integration gates. | CI evidence |
| DV-NF-007 | Simulation shall not depend on wall-clock loops, GPU, or cloud services. | Design and tests |
| DV-NF-008 | Equal state, command, and seed inputs shall produce equal readings. | Deterministic seed test |
| DV-NF-009 | Published energy evidence shall conserve energy at contract precision. | Conservation assertions |

## 10. Architecture Decisions

### ADR-DV-001 — Use One Versioned Aggregate Before Adding Protocol Complexity

**Decision.** Represent the initial vehicle as one validated aggregate and require all integrations
to translate through its public contract.

**Rationale.** A coherent state and invariant boundary is required before ECU, CAN, UDS, physics,
or Android adapters can interoperate safely.

### ADR-DV-002 — Advance Time Only through Persisted Commands

**Decision.** Store logical time in integer milliseconds and advance it only through accepted,
bounded, idempotent commands.

**Rationale.** Command-driven time removes scheduler jitter and background resource consumption,
making failures exactly reproducible.

### ADR-DV-003 — Make Sensor Variance Seeded and Faults Explicit

**Decision.** Derive variance from a persisted seed and sensor name. Configure `stuck` and `offset`
faults explicitly and keep physical state separate from reported readings.

**Rationale.** Reproducible evidence and later diagnostic plausibility tests require deterministic
observations and a clear distinction between plant state and sensor output.

### ADR-DV-004 — Prefer Bounded Scenario Physics over Real-Time Fidelity

**Decision.** Couple vehicle components through explicit, bounded, command-driven equations and
publish their conservation evidence instead of introducing a wall-clock or high-fidelity solver.

**Rationale.** The platform first needs repeatable automotive QA scenarios and explainable failures.
Higher-fidelity models can replace individual equations later without changing API, replay, audit,
or logical-time contracts.

## 11. Verification Catalogue

| ID | Test and objective | Expected result |
|---|---|---|
| DV-T-001 | Register a vehicle | One safe aggregate exists at version 1 and time 0 |
| DV-T-002 | Submit component values outside bounds | Validation rejects the request without persistence |
| DV-T-003 | Submit contradictory moving, motor, brake, or charging state | Whole-aggregate invariants reject the state |
| DV-T-004 | Replace state using the expected version | State commits and version increments once |
| DV-T-005 | Repeat the exact replacement | Current state returns without duplicate evidence |
| DV-T-006 | Submit a stale different replacement | Stable HTTP 409 reports only the current version |
| DV-T-007 | Exercise independent read/write roles | Missing permission returns HTTP 403 |
| DV-T-008 | Execute the complete initial transition sequence | Modes, versions, and logical time are exact |
| DV-T-009 | Skip a required transition | Stable simulation-state conflict, no mutation |
| DV-T-010 | Retry an identical transition command | Persisted response returns without advancing time |
| DV-T-011 | Reuse a transition ID differently | Stable command conflict, no mutation |
| DV-T-012 | Submit out-of-range actuator, duration, seed, or sensor values | Public contract rejects the request |
| DV-T-013 | Apply accelerator and brake together | Pedal conflict validation rejects the request |
| DV-T-014 | Apply non-zero actuators outside driving mode | Operational safety rejects the step |
| DV-T-015 | Apply a valid deterministic step | Physical components update predictably |
| DV-T-016 | Repeat equal state, command, and seed | Sensor readings are identical |
| DV-T-017 | Configure a stuck sensor | Reading remains at the configured value while state is independent |
| DV-T-018 | Configure an offset sensor | Reading applies the configured bounded delta |
| DV-T-019 | Retry an identical simulation step | Persisted step returns without duplicate time or evidence |
| DV-T-020 | Inspect successful transaction evidence | State, replay row, audit, and outbox commit together |
| DV-T-021 | Inspect OpenAPI | All state, transition, and step contracts are discoverable |
| DV-T-022 | Apply migrations 0013–0015 | Existing vehicles backfill safely and the schema reaches head |
| DV-T-023 | Execute a drive-corner-brake scenario | Energy, torque, thermal, steering, suspension, and lighting outputs update together |
| DV-T-024 | Inspect used, recovered, and net Wh | Published values conserve energy at contract precision and recovery is bounded |
| DV-T-025 | Apply road, ambient, and roughness extremes | All component states remain inside declared limits |
| DV-T-026 | Apply migration 0016 | Existing states receive the safe suspension baseline and schema reaches head |

## 12. Implemented Evidence

| Evidence | Repository location |
|---|---|
| Domain models | `src/atep/vehicles/models.py` |
| API schemas and validation | `src/atep/vehicles/schemas.py` |
| Domain behavior | `src/atep/vehicles/service.py` |
| HTTP boundary and RBAC | `src/atep/vehicles/router.py` |
| Stable errors | `src/atep/core/errors.py` |
| Database evolution | `migrations/versions/0013_digital_vehicle_state.py` through `0015_vehicle_sensor_models.py` |
| Focused verification | `tests/test_digital_vehicle_state.py` and `tests/test_api_contract.py` |
| Disposable integration | `tests/integration/test_identity_flow.py` and GitHub Actions |
| Domain design | `docs/digital-vehicle-state.md` |
| Requirements and roadmap | `docs/requirements-volume-ii.md` and `docs/roadmap-volume-ii.md` |

## 13. Risks and Technical Debt

| Risk | Impact | Planned treatment |
|---|---|---|
| Equations are intentionally scenario-oriented | Results are deterministic but not a substitute for validated tyre, chassis, or thermal solvers | Calibrate or replace component equations behind stable contracts when higher fidelity is required |
| Sensor calibration is represented by noise/fault configuration only | Offset correction and calibration lifecycle are incomplete | Add explicit calibration parameters and provenance |
| No multi-vehicle session abstraction | Reproducibility exists per vehicle but not across coordinated fleets | Add isolated sessions and snapshots in II-5 |
| No VHAL property mapping | CarSystemUI integration remains API/gateway-oriented | Add contract mappings and end-to-end evidence in II-6 |

## 14. Roadmap

| Increment | Scope | Status |
|---|---|---|
| II-1 | Versioned aggregate, safe baseline, RBAC, invariants, audit, and outbox | Implemented |
| II-2 | Logical clock and command-driven state transitions | Implemented |
| II-3 | Sensors and actuators with seeded noise and explicit fault modes | Implemented |
| II-4 | Coupled energy, thermal, powertrain, braking, steering, suspension, and lighting behavior | Implemented |
| II-5 | Multi-vehicle simulation sessions and reproducible snapshots | Planned next |
| II-6 | Android Automotive/VHAL Vehicle Gateway mappings | Planned |

## 15. Workbook Maintenance Checklist

- update the document version and revision history after each increment;
- reconcile requirements and roadmap status against repository evidence;
- record new domain decisions and superseded assumptions;
- add positive, negative, boundary, fault, replay, and scenario tests;
- update risks, limitations, and integration boundaries;
- regenerate the DOCX, run accessibility checks, and inspect every rendered page.
