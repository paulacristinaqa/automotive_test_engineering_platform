# CAN Network Baseline

Volume IV-1 introduces a vehicle-scoped classic CAN network aggregate. It references existing ECU
identities and does not duplicate ECU state or semantic signal meaning.

## Implemented Boundary

- one CAN network per vehicle;
- 1-64 ECU-backed nodes with participant, gateway, or monitor roles;
- 0-256 standard or extended frame contracts;
- classic CAN DLC from 0 through 8 bytes;
- standard identifiers through `0x7FF` and extended identifiers through `0x1FFFFFFF`;
- deterministic logical microsecond clock and monotonically increasing frame sequence;
- optimistic network versioning and exact command replay;
- payload-free audit and outbox evidence.

CAN FD payloads, arbitration, bit stuffing, error counters, bus-off, DBC encoding, LIN, and Ethernet
are deliberately deferred. `advance_time_us` is an explicit simulation input, not a measured host
duration.

## Public API

- `POST /api/v1/vehicles/{vehicle_id}/can-networks`
- `GET /api/v1/vehicles/{vehicle_id}/can-networks`
- `POST /api/v1/vehicles/{vehicle_id}/can-networks/frames`
- `GET /api/v1/vehicles/{vehicle_id}/can-networks/frames`

Reads require `can_networks:read`; creation and submission require `can_networks:manage`.

## Deterministic Submission

A submission locks the network row, verifies `expected_version`, resolves the immutable frame
contract, verifies producer ownership and exact DLC, assigns `next_sequence`, advances the logical
bus clock by the requested amount, and increments the network version. Repeating the same
`command_id` and request returns stored evidence. Reusing the identifier differently returns the
stable `can_frame_command_conflict` error.

The event `atep.can.frame.submitted.v1` contains identity, contract, frame ID, DLC, sequence, time,
and versions. It intentionally excludes payload bytes.
