# ATEP Volume IV - CAN Network Engineering Workbook

**Document status:** Increments IV-1 through IV-3 implemented
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
| Baseline | Increments IV-1 through IV-3 |
| Architecture style | Vehicle-scoped aggregate with transactional domain service |
| Primary runtime | Python 3.12, FastAPI, SQLAlchemy, PostgreSQL |
| Quality gates | pytest, Ruff, strict mypy, Alembic and integration CI |

## 3. Revision History

| Release | Date | Change |
|---|---|---|
| 0.1.0 | 2026-08-24 | Added ECU-backed topology, classic CAN frame contracts, deterministic submission, RBAC, audit, outbox, migration, APIs, and tests. |
| 0.2.0 | 2026-08-24 | Added deterministic arbitration, nominal transmission duration, delivery evidence, utilization metrics, replay-safe persistence, APIs, migration, and tests. |
| 0.3.0 | 2026-08-24 | Added structured DBC catalogues, Intel/Motorola signal placement, exact decimal scaling, signed codec evidence, APIs, migration, and tests. |

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
- Batches of one to 64 unique contenders with explicit readiness offsets.
- CAN-ID priority, standard/extended tie-break, calculated nominal duration, and serial delivery.
- Occupied, idle, utilization, latency, ordered transmission, and consumer delivery evidence.
- One structured DBC catalogue mapped to existing frame contracts.
- Exact signal encode/decode with Intel and Motorola byte order, signedness, scaling, and offsets.
- Replay-safe codec evidence with payload-free audit and outbox metrics.

### 4.2 Deferred

- Bit stuffing, acknowledgement, retransmission, and oscillator/physical-layer effects.
- Textual `.dbc` parsing, attributes, value tables, comments, and multiplexing.
- CAN FD payloads and data-phase bitrate.
- Error frames, error counters, bus-off, recovery, loss, latency, and corruption.
- LIN, automotive Ethernet, physical transceivers, and SocketCAN adapters.

## 5. Architecture

The `atep.can_network` module is a protocol boundary between ECU semantic state and future physical
bus behavior. A network belongs to one vehicle and stores bounded topology and frame contracts.
Nodes reference Volume III ECU UUIDs; ECU lifecycle, memory, faults, and semantic values are not
copied into the CAN aggregate.

Request flow: authenticated client -> FastAPI router -> CAN RBAC dependency -> vehicle lookup ->
CAN domain/arbitration/DBC service -> PostgreSQL aggregate/evidence + audit + transactional outbox
-> response.

## 6. Domain Model

`CanNetwork` stores vehicle ownership, identity, bitrate, nodes, frame contracts, version, logical
microsecond time, and the next sequence. `CanFrameTransmission` stores command identity, contract,
producer, CAN ID and format, request, payload, sequence, logical time, versions, and actor.

`CanArbitrationExecution` stores the canonical batch request, ordered result, contender count,
aggregate versions, requesting actor, and timestamps. Each winner also creates normal transmission
evidence so history remains coherent across individual and arbitrated sends.

`CanDbcCatalogue` stores bounded structured messages and signals for one network. Each message
references a frame contract rather than duplicating ID, DLC, producer, or consumers.
`CanSignalCodecExecution` stores the canonical encode/decode request and deterministic payload, raw,
and physical result for exact replay.

Bounds are architectural controls: 64 nodes, 256 contracts, 8 payload bytes, a 10-second maximum
logical advance per submission, safe history pagination, and one network aggregate per vehicle.

## 7. Public API and Security

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/api/v1/vehicles/{vehicle_id}/can-networks` | `can_networks:manage` | Create topology and contracts. |
| GET | `/api/v1/vehicles/{vehicle_id}/can-networks` | `can_networks:read` | Retrieve the network. |
| POST | `/api/v1/vehicles/{vehicle_id}/can-networks/frames` | `can_networks:manage` | Submit one contracted frame. |
| GET | `/api/v1/vehicles/{vehicle_id}/can-networks/frames` | `can_networks:read` | Read safely paginated evidence. |
| POST | `/api/v1/vehicles/{vehicle_id}/can-networks/arbitrations/execute` | `can_networks:manage` | Execute a bounded arbitration batch. |
| GET | `/api/v1/vehicles/{vehicle_id}/can-networks/arbitrations` | `can_networks:read` | List persisted arbitration evidence. |
| GET | `/api/v1/vehicles/{vehicle_id}/can-networks/arbitrations/{command_id}` | `can_networks:read` | Retrieve one arbitration result. |
| POST | `/api/v1/vehicles/{vehicle_id}/can-networks/dbc-catalogues` | `can_networks:manage` | Create the structured DBC catalogue. |
| GET | `/api/v1/vehicles/{vehicle_id}/can-networks/dbc-catalogues` | `can_networks:read` | Retrieve the DBC catalogue. |
| POST | `/api/v1/vehicles/{vehicle_id}/can-networks/dbc/encode` | `can_networks:manage` | Encode physical values into payload bytes. |
| POST | `/api/v1/vehicles/{vehicle_id}/can-networks/dbc/decode` | `can_networks:manage` | Decode payload bytes into signal values. |
| GET | `/api/v1/vehicles/{vehicle_id}/can-networks/dbc/executions` | `can_networks:read` | List safely paginated codec evidence. |
| GET | `/api/v1/vehicles/{vehicle_id}/can-networks/dbc/executions/{command_id}` | `can_networks:read` | Retrieve one codec result. |

The Android Automotive application and future gateways continue to use the public ATEP API. They
never connect directly to PostgreSQL or RabbitMQ.

## 8. Consistency and Evidence

Creation verifies that every declared node is an ECU owned by the vehicle. Submission locks the
network row, verifies the expected version, resolves the immutable frame contract, checks producer
ownership and exact DLC, assigns the next sequence, advances logical time, and increments version.

Exact retry returns the persisted transmission without a second mutation or event. Differing reuse
of a command ID fails with `can_frame_command_conflict`. Audit and outbox evidence retains IDs,
format, DLC, sequence, logical time, and versions while excluding payload bytes.

### 8.1 Arbitration Semantics

Each contender is resolved against an immutable frame contract and checked for producer ownership
and exact DLC. The bus selects only ready contenders. Lowest numeric CAN ID wins; standard format
precedes extended format for an equal numeric ID; contract identity provides a stable final
tie-break. When no frame is ready, the logical clock advances to the next readiness instant.

Nominal size is `47 + 8 * DLC` bits for standard and `67 + 8 * DLC` bits for extended classic CAN.
This includes a three-bit intermission and excludes bit stuffing. Duration uses the ceiling of
`bit_count * 1000 / bitrate_kbps`. Frames are serialized, delivered to every declared consumer at
completion, and assigned latency from readiness to completion.

The utilization window begins at the prior network time and ends at the last completion. Occupied
time is the sum of nominal durations; idle time is the remainder. A batch advances the network
version once and the sequence once per winner. Exact retry returns stored evidence without another
mutation, event, or audit record.

### 8.2 DBC Signal Semantics

Catalogue creation locks the network, verifies optimistic version, resolves every message against an
existing frame contract, and rejects duplicate messages, duplicate signals, occupied-bit overlap, or
positions outside the contracted DLC. One catalogue is allowed per network in this increment.

Intel signals begin at their least-significant bit and occupy increasing bit positions. Motorola
signals begin at their most-significant bit and follow DBC sawtooth numbering: bits descend within a
byte, then bit 0 advances to bit 15 of the next byte. Signed signals use two's complement.

Physical-to-raw conversion uses decimal arithmetic: `(physical - offset) / factor`. A value is
rejected if it violates optional physical bounds, exceeds its signed or unsigned raw range, or would
require fractional rounding. Decode applies `raw * factor + offset`. Encode requires exactly the
declared signal set, preventing accidental default values or ignored names.

Codec commands lock the network row to serialize command identity checks. Exact retry returns the
stored result; changed reuse fails with `can_signal_codec_command_conflict`. Payload, raw values, and
physical values are persisted as engineering evidence but excluded from audit and outbox messages.

## 9. Functional Requirements

The authoritative catalogue is `docs/requirements-volume-iv.md`. IV-1 through IV-3 implement
CAN-F-001 through CAN-F-030 and CAN-NF-001 through CAN-NF-011.

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

A submitted frame is distinct from a batch contender. IV-2 makes priority, duration, delivery, and
bus-load assumptions explicit and independently testable.

### ADR-CAN-007 - Model Nominal Timing Before Physical Effects

The first timing model includes fixed classic CAN fields and intermission but excludes bit stuffing,
acknowledgement failure, retransmission, propagation delay, and oscillator drift. This produces a
reproducible engineering baseline without claiming electrical-bus fidelity.

### ADR-CAN-008 - Persist Both Batch and Frame Evidence

The batch preserves arbitration context and metrics. Winner transmissions preserve a unified frame
history. A single aggregate version increment represents the atomic command, while each frame gets
its own monotonically increasing sequence.

### ADR-CAN-009 - Reference Frame Contracts from DBC Messages

DBC messages do not duplicate frame ID, format, DLC, producer, or consumers. The CAN contract stays
authoritative while the catalogue supplies signal interpretation.

### ADR-CAN-010 - Implement Explicit Intel and Motorola Bit Traversal

Intel uses increasing LSB-first positions. Motorola uses MSB-first DBC sawtooth traversal. The bit
position function is independently tested so byte-order behavior remains reviewable.

### ADR-CAN-011 - Reject Inexact Physical Values

Decimal arithmetic avoids binary floating-point drift. Encoding rejects non-integral raw results
instead of selecting an implicit rounding policy that could hide test-data errors.

### ADR-CAN-012 - Separate Codec Evidence from Bus Transmission

Encoding creates a payload but does not automatically transmit it. A later caller may submit or
arbitrate that payload, keeping semantic conversion and transport execution independently testable.

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
| Arbitration priority | Select lowest ready CAN ID and standard before extended on equal ID. | Service |
| Readiness | Advance only logical time when the bus has no ready contender. | Service |
| Nominal bit count | Apply documented standard and extended classic CAN formulas. | Unit |
| Duration rounding | Round calculated microseconds upward to avoid zero or partial evidence. | Unit |
| Serial delivery | Start the next winner only after prior completion. | Service |
| Consumer evidence | Record receipt and readiness-to-completion latency per declared consumer. | Service |
| Utilization | Derive window, occupied, idle, percentage, and maximum latency consistently. | Service |
| Batch versioning | Increment version once and sequence once per winning frame. | Service |
| Arbitration replay | Return persisted result without advancing simulation state twice. | Service/API |
| Arbitration conflict | Reject changed command reuse with a stable error. | Service/API |
| Arbitration RBAC | Require manage to execute and read to query evidence. | API/integration |
| Arbitration minimization | Exclude CAN payload bytes from event and audit metrics. | Service |
| Catalogue uniqueness | Reject a second catalogue for the same CAN network. | Service/database |
| Contract mapping | Reject a DBC message without an existing frame contract. | Service |
| Signal uniqueness | Reject duplicate signal names within one message. | Schema |
| DLC boundary | Reject Intel or Motorola positions outside contracted payload bits. | Service |
| Signal overlap | Reject any two signals that occupy a common payload bit. | Service |
| Intel placement | Verify LSB-first contiguous positions and payload bytes. | Unit |
| Motorola placement | Verify MSB-first sawtooth positions and payload bytes. | Unit |
| Signed round-trip | Preserve negative two's-complement raw values. | Unit/service |
| Decimal conversion | Apply factor and offset without binary floating-point drift. | Unit |
| Exact representation | Reject physical values requiring fractional raw rounding. | Unit/service |
| Physical bounds | Reject values below minimum or above maximum. | Unit/service |
| Exact signal set | Reject missing or unexpected encode values. | Unit/service |
| Codec replay | Reuse exact command evidence without duplicate observability. | Service/API |
| Codec conflict | Reject changed command reuse with a stable error. | Service/API |
| Codec concurrency | Serialize command identity checks on the network row. | Integration |
| Codec minimization | Exclude payload and values from audit and events. | Service |

## 12. Implemented Evidence

- `src/atep/can_network/` contains models, schemas, service, and router.
- Migrations `0024_can_network_baseline`, `0025_can_arbitration`, and `0026_can_dbc_codec` own the database schema.
- Events include `atep.can.network.created.v1`, `atep.can.frame.submitted.v1`, and `atep.can.arbitration.completed.v1`.
- DBC events are `atep.can.dbc.catalogue.created.v1` and `atep.can.signal.codec.completed.v1`.
- Permissions are `can_networks:read` and `can_networks:manage`.
- Automated tests cover validation, priority, timing mathematics, readiness, delivery, utilization, versioning, replay, errors, DBC bit placement, signed scaling, exact conversion, evidence minimization, persistence, and OpenAPI.

## 13. Risks and Technical Debt

- JSON topology is practical for the bounded baseline but may later need normalized history.
- One network per vehicle is intentionally conservative; real vehicles contain multiple buses.
- Stored payloads are test evidence and may require a future retention policy.
- Nominal duration excludes variable bit stuffing and physical-layer effects.
- Arbitration currently models one attempt; acknowledgement and retransmission are future work.
- The catalogue is structured JSON; importing and exporting textual `.dbc` files remains future work.
- Multiplexed signals, value tables, attributes, and comments are not yet represented.
- Encoding produces evidence but does not automatically submit the frame to the simulated bus.

## 14. Roadmap

The recommended next increment is IV-4: CAN FD payload and timing contracts with explicit nominal
and data-phase bitrate plus mixed classic/FD compatibility. See `docs/roadmap-volume-iv.md`.

## 15. Study Exercises

1. Explain why a CAN node references an ECU UUID instead of copying ECU state.
2. Compare standard 11-bit and extended 29-bit identifier limits.
3. Design a battery-status contract with a two-byte payload and three consumers.
4. Trace a successful submission through row lock, version, sequence, audit, and outbox.
5. Explain why host elapsed time cannot be used as simulated bus time.
6. Prove why an exact retry must not increment sequence twice.
7. Compare `can_network_version_conflict` and `can_frame_command_conflict`.
8. Explain why payload bytes are stored as evidence but excluded from audit and events.
9. Prove the winner order for simultaneous IDs `0x100`, `0x180`, and `0x200`.
10. Calculate nominal duration for standard DLC 8 at 500 kbit/s and list omitted effects.
11. Design the DBC adapter boundary between a BMS semantic signal and a CAN payload.
12. Propose how multiple buses per vehicle could be added without breaking current identifiers.
13. Explain why standard format precedes extended format for an equal numeric identifier.
14. Calculate utilization when a frame becomes ready 50 microseconds after the window begins.
15. Explain why one batch increments aggregate version once but sequence once per winner.
16. Design an acknowledgement-failure extension without changing the nominal IV-2 evidence.
17. Encode a 12-bit Intel value `0xABC` beginning at bit 0 and list the resulting bytes.
18. Trace a 12-bit Motorola value beginning at bit 7 through sawtooth bit positions.
19. Explain how two's-complement decoding reconstructs a negative raw value.
20. Prove why `300.05` is not representable when factor is `0.1` and offset is zero.
21. Explain why DBC messages reference frame contracts instead of repeating their metadata.
22. Design a test that detects overlap between one Intel and one Motorola signal.
23. Trace encode evidence into a later arbitration command without coupling the two operations.
24. Propose a backward-compatible textual `.dbc` import boundary.
