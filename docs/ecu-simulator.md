# ECU Simulator — Aggregate Baseline

Volume III begins with a protocol-independent Electronic Control Unit (ECU) aggregate. The baseline
provides durable identity, vehicle ownership, ECU type, operational state, bounded byte-addressable
memory, explicit faults, and optimistic concurrency. CAN frames and UDS services will depend on this
aggregate in later increments rather than owning a second ECU representation.

## Domain Boundary

Each ECU belongs to exactly one digital vehicle and is identified uniquely inside that vehicle.
Supported initial types are motor, battery, door, ABS, ADAS, climate, gateway, lighting, and body.
The lifecycle states are offline, booting, running, degraded, fault, and shutdown.

Memory is represented as at most 256 unique address/value pairs. Addresses are unsigned 16-bit
values and cells contain unsigned bytes. An ECU can expose at most 64 unique faults. Faults have a
canonical code, severity, status, and bounded description. A confirmed critical fault requires the
ECU to be in the fault state.

## API

- `POST /api/v1/vehicles/{vehicle_id}/ecus` creates an ECU.
- `GET /api/v1/vehicles/{vehicle_id}/ecus` lists ECUs with safe pagination and type filtering.
- `GET /api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}` returns one ECU.
- `PUT /api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/state` replaces state using `expected_version`.

The API uses `ecus:read` and `ecus:manage`. State replacement locks the row and rejects stale
updates with the stable `ecu_state_version_conflict` error. An exact retry is idempotent.

## Evidence and Events

Creation writes `ecu.created` audit evidence and `atep.ecu.created.v1` to the transactional outbox.
State replacement writes `ecu.state_updated` and `atep.ecu.state.updated.v1`. Audit details contain
identity, version, state, and counts, but not full mutable memory or fault payloads.

## Deterministic Execution Clock

Each ECU owns `simulation_time_ms`, `boot_count`, and up to 32 cyclic task definitions. A task has a
canonical ID, period, and offset. `POST .../simulation/advance` moves the logical clock without
wall-clock sleep and returns execution count plus first and last due times for every task. The result
is reproducible and remains small even when many cycles are due.

Advance commands run only when the ECU is running or degraded. A row lock and expected version make
concurrent updates explicit. Persisted command identity provides exact replay without advancing the
clock twice. Successful advances emit `atep.ecu.simulation.advanced.v1`.

## Reset Semantics

`POST .../reset` supports soft, hard, and power-cycle modes with fixed logical durations of 10, 100,
and 500 milliseconds. A reset increments `boot_count`, advances logical time, and returns the ECU to
offline unless a confirmed critical fault requires it to remain in fault state. Memory and faults are
preserved deliberately until volatile/non-volatile regions are defined in III-4. Successful resets
emit `atep.ecu.reset.completed.v1`.

## Current Limits

This baseline does not execute ECU firmware, model non-volatile memory, emit CAN frames, expose UDS
services, or inject faults over time. Those capabilities are planned as
separate increments so their timing and protocol contracts can be tested independently.
