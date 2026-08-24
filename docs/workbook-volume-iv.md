# ATEP Volume IV - CAN Network Engineering Workbook

**Document status:** Increment IV-1 implemented
**Language:** English
**Last updated:** 2026-08-24
**Repository:** `paulacristinaqa/automotive_test_engineering_platform`

## 1. Document Purpose

This workbook records the architecture, requirements, engineering decisions, implementation
evidence, verification strategy, risks, and study exercises for the CAN Network volume.

## 2. Document Control

| Field | Value |
|---|---|
| Volume | IV - CAN Network |
| Baseline | Increment IV-1 |
| Architecture style | Vehicle-scoped aggregate with transactional domain service |
| Primary runtime | Python 3.12, FastAPI, SQLAlchemy, PostgreSQL |
| Quality gates | pytest, Ruff, strict mypy, Alembic and integration CI |

## 3. Revision History

| Release | Date | Change |
|---|---|---|
| 0.1.0 | 2026-08-24 | Added ECU-backed topology, classic CAN frame contracts, deterministic submission, RBAC, audit, outbox, migration, APIs, and tests. |

## 4. Scope and Boundaries

### 4.1 Included

- One classic CAN network per vehicle.
- One to 64 nodes referencing ECUs from the same vehicle.
- Participant, gateway, and monitor node roles.
- Up to 256 standard or extended frame contracts.
- Classic CAN payloads from zero to eight bytes.
- Deterministic logical microsecond clock, sequence, and optimistic version.
- Exact command replay and stable changed-reuse conflicts.
- Protected create, retrieve, submit, and history APIs.
- Transactional audit and outbox evidence without payload bytes.

### 4.2 Deferred

- CAN arbitration and calculated bus timing.
- DBC parsing, scaling, byte order, multiplexing, and semantic-signal encoding.
- CAN FD payloads and data-phase bitrate.
- Error frames, error counters, bus-off, recovery, loss, latency, and corruption.
- LIN, automotive Ethernet, physical transceivers, and SocketCAN adapters.

## 5. Architecture

The `atep.can_network` module is a protocol boundary between ECU semantic state and future physical
bus behavior. A network belongs to one vehicle and stores bounded topology and frame contracts.
Nodes reference Volume III ECU UUIDs; ECU lifecycle, memory, faults, and semantic values are not
copied into the CAN aggregate.

Request flow: authenticated client -> FastAPI router -> CAN RBAC dependency -> vehicle lookup ->
CAN domain service -> PostgreSQL aggregate/transmission + audit + transactional outbox -> response.

## 6. Domain Model

`CanNetwork` stores vehicle ownership, identity, bitrate, nodes, frame contracts, version, logical
microsecond time, and the next sequence. `CanFrameTransmission` stores command identity, contract,
producer, CAN ID and format, request, payload, sequence, logical time, versions, and actor.

Bounds are architectural controls: 64 nodes, 256 contracts, 8 payload bytes, a 10-second maximum
logical advance per submission, safe history pagination, and one network aggregate per vehicle.

## 7. Public API and Security

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/api/v1/vehicles/{vehicle_id}/can-networks` | `can_networks:manage` | Create topology and contracts. |
| GET | `/api/v1/vehicles/{vehicle_id}/can-networks` | `can_networks:read` | Retrieve the network. |
| POST | `/api/v1/vehicles/{vehicle_id}/can-networks/frames` | `can_networks:manage` | Submit one contracted frame. |
| GET | `/api/v1/vehicles/{vehicle_id}/can-networks/frames` | `can_networks:read` | Read safely paginated evidence. |

The Android Automotive application and future gateways continue to use the public ATEP API. They
never connect directly to PostgreSQL or RabbitMQ.

## 8. Consistency and Evidence

Creation verifies that every declared node is an ECU owned by the vehicle. Submission locks the
network row, verifies the expected version, resolves the immutable frame contract, checks producer
ownership and exact DLC, assigns the next sequence, advances logical time, and increments version.

Exact retry returns the persisted transmission without a second mutation or event. Differing reuse
of a command ID fails with `can_frame_command_conflict`. Audit and outbox evidence retains IDs,
format, DLC, sequence, logical time, and versions while excluding payload bytes.

## 9. Functional Requirements

The authoritative catalogue is `docs/requirements-volume-iv.md`. IV-1 implements CAN-F-001 through
CAN-F-012 and CAN-NF-001 through CAN-NF-006.

## 10. Architecture Decisions

### ADR-CAN-001 - Reference ECUs Instead of Recreating Controllers

The CAN topology stores ECU UUIDs. Volume III remains the source of controller identity and state.

### ADR-CAN-002 - Separate Semantic Signals from Transport Frames

ECUs own physical meaning and values. CAN owns identifiers, DLC, payload bytes, sequence, and future
transport timing. DBC will become the explicit adapter between these representations.

### ADR-CAN-003 - Use Logical Bus Time

Explicit microsecond advances make tests repeatable across machines. Host duration and resource
load never alter simulated truth.

### ADR-CAN-004 - Persist Replay-Safe Submission Evidence

A unique command ID plus the canonical request distinguishes exact retries from conflicting reuse.

### ADR-CAN-005 - Minimize Audit and Event Payloads

Evidence records transport identity and metrics without copying physical payload bytes into logs or
messages.

### ADR-CAN-006 - Defer Arbitration Until Its Timing Model Is Explicit

A submitted frame is not yet a physically arbitrated transmission. IV-2 will define priority,
duration, delivery, and bus-load semantics rather than hiding them in IV-1.

## 11. Verification Catalogue

| Test | Objective | Level |
|---|---|---|
| Standard ID bound | Reject IDs above `0x7FF` in standard format. | Schema |
| Extended ID bound | Accept only IDs through 29 bits. | Schema |
| Node bound | Reject the 65th ECU node. | Schema |
| Contract bound | Reject the 257th frame contract. | Schema |
| Topology ownership | Reject an ECU belonging to another vehicle. | Service/integration |
| Unique topology | Reject duplicate nodes, contract names, and format/ID pairs. | Schema |
| DLC validation | Require payload length to equal the contracted DLC. | Service/API |
| Producer ownership | Reject submission by an undeclared producer. | Service/API |
| Deterministic order | Assign monotonically increasing sequence numbers. | Service |
| Logical time | Derive transmission time only from explicit inputs. | Service |
| Optimistic conflict | Return current version for stale submissions. | Service/API |
| Exact replay | Avoid advancing time, sequence, or version twice. | Service/API |
| Command conflict | Reject changed reuse with a stable error. | Service/API |
| Atomic evidence | Commit aggregate, frame, audit, and outbox together. | Integration |
| Evidence minimization | Exclude payload bytes from audit and events. | Service |
| RBAC | Separate read and manage permissions. | API/integration |
| OpenAPI | Publish typed contracts and pagination bounds. | Contract |
| Migration lifecycle | Upgrade and downgrade the PostgreSQL schema. | Integration |

## 12. Implemented Evidence

- `src/atep/can_network/` contains models, schemas, service, and router.
- Migration `0024_can_network_baseline` owns the database schema.
- Events are `atep.can.network.created.v1` and `atep.can.frame.submitted.v1`.
- Permissions are `can_networks:read` and `can_networks:manage`.
- Automated tests cover validation, deterministic mutation, replay, errors, evidence, and OpenAPI.

## 13. Risks and Technical Debt

- JSON topology is practical for the bounded baseline but may later need normalized history.
- One network per vehicle is intentionally conservative; real vehicles contain multiple buses.
- Stored payloads are test evidence and may require a future retention policy.
- Submission order is not arbitration order until IV-2 defines timing and priority behavior.
- No DBC adapter currently maps Volume III semantic values into payload bytes.

## 14. Roadmap

The recommended next increment is IV-2: deterministic arbitration, calculated transmission
duration, receive delivery, and bounded bus-load evidence. See `docs/roadmap-volume-iv.md`.

## 15. Study Exercises

1. Explain why a CAN node references an ECU UUID instead of copying ECU state.
2. Compare standard 11-bit and extended 29-bit identifier limits.
3. Design a battery-status contract with a two-byte payload and three consumers.
4. Trace a successful submission through row lock, version, sequence, audit, and outbox.
5. Explain why host elapsed time cannot be used as simulated bus time.
6. Prove why an exact retry must not increment sequence twice.
7. Compare `can_network_version_conflict` and `can_frame_command_conflict`.
8. Explain why payload bytes are stored as evidence but excluded from audit and events.
9. Propose an IV-2 arbitration rule for simultaneous standard frames.
10. Calculate approximate classic CAN frame duration and list the assumptions still required.
11. Design the DBC adapter boundary between a BMS semantic signal and a CAN payload.
12. Propose how multiple buses per vehicle could be added without breaking current identifiers.
