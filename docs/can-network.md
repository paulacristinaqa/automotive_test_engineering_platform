# CAN Network and Deterministic Arbitration

Volume IV-1 introduced a vehicle-scoped classic CAN aggregate. Volume IV-2 added deterministic
arbitration and timing. Volume IV-3 adds a structured DBC catalogue and exact signal codec.

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
- one bounded DBC catalogue mapped to existing frame contracts;
- Intel LSB-first and Motorola MSB-first sawtooth bit placement;
- unsigned and two's-complement signed signals with decimal factor and offset;
- exact physical-to-raw representability, optional physical bounds, and overlap detection;
- replay-safe encode/decode evidence with payload-free audit and events.

CAN FD payloads, bit stuffing, retransmission, acknowledgement failure, error counters, bus-off,
textual `.dbc` parsing, multiplexed signals, LIN, and Ethernet are deliberately deferred.

## Public API

- `POST /api/v1/vehicles/{vehicle_id}/can-networks`
- `GET /api/v1/vehicles/{vehicle_id}/can-networks`
- `POST /api/v1/vehicles/{vehicle_id}/can-networks/frames`
- `GET /api/v1/vehicles/{vehicle_id}/can-networks/frames`
- `POST /api/v1/vehicles/{vehicle_id}/can-networks/arbitrations/execute`
- `GET /api/v1/vehicles/{vehicle_id}/can-networks/arbitrations`
- `GET /api/v1/vehicles/{vehicle_id}/can-networks/arbitrations/{command_id}`
- `POST /api/v1/vehicles/{vehicle_id}/can-networks/dbc-catalogues`
- `GET /api/v1/vehicles/{vehicle_id}/can-networks/dbc-catalogues`
- `POST /api/v1/vehicles/{vehicle_id}/can-networks/dbc/encode`
- `POST /api/v1/vehicles/{vehicle_id}/can-networks/dbc/decode`
- `GET /api/v1/vehicles/{vehicle_id}/can-networks/dbc/executions`
- `GET /api/v1/vehicles/{vehicle_id}/can-networks/dbc/executions/{command_id}`

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

## Structured DBC Signal Codec

Each catalogue message references an existing frame contract, so frame ID, format, DLC, producer,
and consumers remain owned by the CAN topology. Signals add transport interpretation: start bit,
length, byte order, signedness, factor, offset, optional physical bounds, and unit. Catalogue
creation rejects unknown contracts, signals outside the DLC, and overlapping occupied bits.

Intel positions increase from the declared least-significant start bit. Motorola positions begin at
the signal's most-significant bit and follow DBC sawtooth numbering: decrement within a byte, then
jump from bit 0 to bit 15 of the next byte. Signed raw values use two's complement.

Encoding calculates `(physical - offset) / factor` with decimal arithmetic and rejects fractional raw
results instead of rounding silently. Decoding calculates `raw * factor + offset`. Commands require
exact signal sets, are serialized on the network row, and persist deterministic payload, raw, and
physical evidence. Exact retries reuse the stored result; changed reuse returns
`can_signal_codec_command_conflict`. The event `atep.can.signal.codec.completed.v1` exposes only
operation, identities, signal count, and DLC.
