# CAN Network and Deterministic Arbitration

Volume IV-1 introduced a vehicle-scoped classic CAN aggregate. Volume IV-2 adds deterministic
batch arbitration, calculated transmission duration, receive evidence, and bounded bus utilization.

## Implemented Boundary

- one CAN network per vehicle;
- 1-64 ECU-backed nodes with participant, gateway, or monitor roles;
- 0-256 standard or extended frame contracts;
- classic CAN DLC from 0 through 8 bytes;
- standard identifiers through `0x7FF` and extended identifiers through `0x1FFFFFFF`;
- deterministic logical microsecond clock and monotonically increasing frame sequence;
- optimistic network versioning and exact command replay;
- payload-free audit and outbox evidence.
- batches of 1-64 unique contracted contenders;
- CAN identifier priority with standard-format precedence for equal numeric identifiers;
- classic CAN nominal duration excluding bit stuffing and including three-bit intermission;
- consumer delivery evidence, latency, idle time, occupied time, and utilization;
- persisted arbitration results with exact replay and stable changed-reuse conflict.

CAN FD payloads, bit stuffing, retransmission, acknowledgement failure, error counters, bus-off,
DBC encoding, LIN, and Ethernet are deliberately deferred. Simulated truth never uses host timing.

## Public API

- `POST /api/v1/vehicles/{vehicle_id}/can-networks`
- `GET /api/v1/vehicles/{vehicle_id}/can-networks`
- `POST /api/v1/vehicles/{vehicle_id}/can-networks/frames`
- `GET /api/v1/vehicles/{vehicle_id}/can-networks/frames`
- `POST /api/v1/vehicles/{vehicle_id}/can-networks/arbitrations/execute`
- `GET /api/v1/vehicles/{vehicle_id}/can-networks/arbitrations`
- `GET /api/v1/vehicles/{vehicle_id}/can-networks/arbitrations/{command_id}`

Reads require `can_networks:read`; creation and submission require `can_networks:manage`.

## Deterministic Submission

A submission locks the network row, verifies `expected_version`, resolves the immutable frame
contract, verifies producer ownership and exact DLC, assigns `next_sequence`, advances the logical
bus clock by the requested amount, and increments the network version. Repeating the same
`command_id` and request returns stored evidence. Reusing the identifier differently returns the
stable `can_frame_command_conflict` error.

The event `atep.can.frame.submitted.v1` contains identity, contract, frame ID, DLC, sequence, time,
and versions. It intentionally excludes payload bytes.

## Deterministic Arbitration

Each contender declares a contracted frame, producer, payload, and ready offset. At each free-bus
instant, the lowest numeric CAN identifier wins. Standard format precedes extended format when the
numeric identifiers are equal; contract identity is the stable final tie-breaker. If no contender is
ready, logical time advances to the next readiness instant.

Nominal classic CAN size is `47 + 8 * DLC` bits for standard frames and `67 + 8 * DLC` bits for
extended frames. Duration is the ceiling of bits divided by configured bitrate. These transparent
engineering assumptions deliberately omit bit stuffing and physical error behavior.

One arbitration batch increments the network version once and the sequence once per winner. The
result stores frame order, timing, delivery to declared consumers, maximum latency, and utilization.
The event `atep.can.arbitration.completed.v1` and its audit record contain aggregate metrics only;
payload bytes remain confined to transmission evidence.
