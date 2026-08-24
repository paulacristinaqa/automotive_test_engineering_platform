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
offline unless a confirmed critical fault requires it to remain in fault state. Soft reset preserves
memory; hard and power-cycle reset restore volatile cells and retain non-volatile cells. Faults are
preserved. Successful resets emit `atep.ecu.reset.completed.v1`.

## Versioned Behavior Profiles

Every supported ECU type resolves to a versioned profile. Motor, battery, body, gateway, and ABS
safety controllers have distinct tasks, initial state, and counter transitions; door, ADAS, climate,
and lighting controllers currently use an explicitly identified coordination baseline. New ECUs
receive profile defaults when tasks and behavior state are omitted.

`GET /api/v1/ecu-profiles` lists the catalogue and `GET /api/v1/ecu-profiles/{ecu_type}` returns one
contract. Both require `ecus:read`. State replacement rejects unknown task IDs, altered profile
schedules, and unknown behavior-state keys with `ecu_profile_contract_invalid`.

Logical-time advancement applies state transitions from the arithmetic task summaries. For example,
ten due battery cell-monitor cycles increment `cell_samples` by ten without executing a real-time
loop. Profile behavior is therefore repeatable, bounded, and independent of CAN and UDS transport.

## Memory Regions, Snapshots, and Corruption

Each ECU can define up to 16 non-overlapping regions over the 16-bit address space. Every initialized
memory cell belongs to exactly one `volatile` or `non_volatile` region. New ECUs without an explicit
map receive a full-address-space `legacy_nvm` region so existing sparse-memory behavior remains
compatible.

Soft reset preserves all cells. Hard and power-cycle reset restore initialized volatile cells to the
region's `reset_value` and preserve non-volatile cells. Reset evidence reports how many volatile
cells changed and how many non-volatile cells remained intact.

Memory snapshots store at most the aggregate's 256 initialized cells, state version, logical time,
and a canonical SHA-256 checksum. Snapshot audit and events contain counts and checksum, not the full
memory image. Seeded corruption flips 1 to 32 bits in selected initialized regions and persists its
command identity, making exact retries safe and results reproducible.

## Fault Lifecycle and DTC Bridge

`POST .../faults/observe` records a detected or absent observation at the ECU's current logical
time. Consecutive detections promote a pending fault to confirmed at its configured threshold;
consecutive absences heal a non-latched fault at its healing threshold. Confirmed critical faults
move the ECU to fault state. Latched confirmed faults remain active until `POST
.../faults/{fault_code}/clear` is executed explicitly.

Both commands use optimistic versions and persisted command IDs. Exact retries do not increment
counters or versions twice. Lifecycle evidence is minimized and published as
`atep.ecu.fault.lifecycle.changed.v1` in the same transaction as the aggregate and audit record.

`GET .../faults/dtc-candidates` returns a protocol-independent projection containing pending,
confirmed, test-failed, and warning-indicator intent. The Diagnostics volume will own actual UDS DTC
numbers, aging rules, storage status bytes, and diagnostic services.

## Signal Contracts and Gateway Routing Hooks

An ECU can define at most 64 semantic signal contracts. Each contract has a canonical name,
`produced` or `consumed` direction, strict boolean/integer/decimal data type, optional unit and
physical bounds, optional cycle time, current value, and last ECU logical update time. Duplicate
names are rejected within one direction.

`POST .../signals/{signal_name}/publish` changes only a produced signal under optimistic versioning.
The command records exact-replay identity and uses `simulation_time_ms`; its audit/outbox evidence
omits the physical value. Successful publication emits `atep.ecu.signal.published.v1`.

A gateway ECU owns routes created through `POST .../signal-routes`. A route connects a produced
source signal to a consumed target signal on a different ECU in the same vehicle. Data type and unit
must match. `POST .../signal-routes/{route_id}/transfer` copies the current value while checking both
source and target versions, then updates only the target ECU. Route creation and transfer emit
`atep.ecu.signal.route.created.v1` and `atep.ecu.signal.routed.v1`.

## Multi-ECU Scenarios and Failure Campaigns

`POST /api/v1/vehicles/{vehicle_id}/ecu-scenarios/execute` executes a persisted, vehicle-scoped
scenario with `ecus:manage`. A request contains 1 to 32 ordered actions, references at most 16 ECU
identifiers, and runs from one to eight iterations. Supported actions reuse existing domain commands:
logical-time advance, fault observation, seeded memory corruption, signal publication, and gateway
signal transfer. The orchestrator calculates current optimistic versions internally and derives a
stable command ID from the execution ID, iteration, and action position.

Memory-corruption campaigns derive each action seed from the declared base seed and logical action
coordinates. The same initial database state and request therefore produce the same mutations and
evidence on any CI machine. Exact retries return the stored execution; reuse of an execution ID with
a changed request returns `ecu_scenario_execution_conflict`. A vehicle row lock closes concurrent
claim races, and the endpoint commits every primitive action, the scenario row, audit records, and
outbox events together.

The result contains at most 256 action summaries, aggregate resource counts before and after the
scenario, and at most 16 per-ECU clock diagnostics. Resource evidence counts ECUs, initialized memory
cells, semantic signals, active faults, routes, and aggregate state versions. Timing diagnostics use
only ECU logical clocks and report minimum, maximum, skew, and lag from the leading ECU. Host CPU,
GPU, RAM, and wall-clock duration are deliberately excluded from simulation truth. Read access uses
the bounded list and detail endpoints with `ecus:read`.

Scenario evidence emits `atep.ecu.scenario.completed.v1` without memory contents, physical signal
values, or complete fault payloads. The orchestrator does not add CAN frames, DBC mapping, UDS
services, condition evaluators, or real-time background workers.

These are transport hooks, not a CAN bus. CAN IDs, frames, payload encoding, DBC parsing,
arbitration, timing, bitrate, and error injection remain owned by Volume IV.

## Current Limits

This baseline does not execute ECU firmware, emit CAN frames, arbitrate a bus, expose UDS services,
or assign actual DTC numbers. Fault observations and signal transfers are explicit commands rather
than autonomous physical/network evaluation. Those capabilities remain separate so timing and
protocol contracts can be tested independently.
