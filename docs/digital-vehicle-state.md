# Digital Vehicle State

## Purpose

This is the first executable increment of Volume II. It gives every ATEP vehicle one authoritative,
versioned state aggregate while keeping simulation physics, ECUs, networks, and diagnostics outside
the boundary until their dedicated volumes.

## Aggregate

| Component | Representative state |
|---|---|
| Operational mode | `parked`, `ready`, `driving`, `charging`, or `fault` |
| Battery | SOC, SOH, voltage, current, temperature, contactors, charging status |
| Powertrain | motor enablement, gear, speed, requested and delivered torque |
| Brakes | pedal position, hydraulic pressure, parking brake, ABS activity |
| Steering | wheel angle and assist status |
| Lighting | exterior-light mode, brake lamps, and indicators |
| Suspension | front/rear travel and lateral acceleration |

Numeric fields have explicit contract bounds. Vehicle creation also creates a safe baseline:
parked, stationary, traction motor disabled, contactors open, parking brake applied, and lights off.

## API and authorization

| Operation | Permission | Purpose |
|---|---|---|
| `GET /api/v1/vehicles/{vehicle_id}/state` | `digital_vehicle:read` | Read the complete current aggregate |
| `PUT /api/v1/vehicles/{vehicle_id}/state` | `digital_vehicle:write` | Replace the aggregate using `expected_version` |
| `POST /api/v1/vehicles/{vehicle_id}/simulation/transitions` | `digital_vehicle:write` | Execute one deterministic, idempotent transition |
| `POST /api/v1/vehicles/{vehicle_id}/simulation/steps` | `digital_vehicle:write` | Apply bounded actuators and capture seeded sensor readings |

These permissions are independent from vehicle catalogue administration. Clients use the public
API; they never connect directly to PostgreSQL, Redis, or RabbitMQ.

## Consistency and safety rules

- A moving vehicle must be in `driving` mode, use drive or reverse gear, have the motor enabled,
  battery contactors closed, and parking brake released.
- Charging requires `charging` mode, zero speed, park gear, disabled traction motor, and closed
  contactors.
- A parked vehicle cannot be moving.
- A disabled motor cannot request or deliver torque.

The full aggregate is validated together so one component cannot create an impossible combination
with another.

## Concurrency, retry, and evidence

The client supplies `expected_version`. The service locks the state row before evaluating the
request. A new valid state increments the version. An exact retry of the immediately preceding
replacement returns the current representation without producing duplicate evidence. A stale
request that differs from current state returns HTTP 409 with code
`vehicle_state_version_conflict` and `current_version` in the error details.

Each real transition commits the new state, an audit record named
`digital_vehicle.state_updated`, and an outbox event named
`atep.digital_vehicle.state.updated.v1` in the same PostgreSQL transaction. Audit details contain
identifiers and the state version rather than copying the complete state payload.

## Verification catalogue

| Test | Objective |
|---|---|
| Safe baseline | Prove vehicle registration creates a deterministic non-moving state |
| Field bounds | Reject invalid SOC, SOH, temperature, speed, torque, steering, and brake values |
| Cross-component invariants | Reject contradictory moving, parked, motor, brake, and charging combinations |
| Positive replacement | Persist a valid aggregate and increment its version |
| Atomic evidence | Prove state, audit, and outbox records commit together |
| Exact retry | Prove a repeated request does not duplicate state transitions or evidence |
| Stale conflict | Return a stable 409 contract and expose only the current version |
| Independent RBAC | Prove read and write permissions are enforced separately |
| API contract | Keep OpenAPI request/response schemas and routes versioned and discoverable |
| Migration integration | Apply the migration and backfill safe state for pre-existing vehicles |

## Current limitations

This increment stores snapshots; it does not integrate equations over time, simulate hardware
latency, publish CAN frames, raise DTCs, or write Android VHAL properties. Those capabilities will
be layered behind the aggregate contract in subsequent Volume II through Volume V increments.

## Deterministic transition engine

The simulation clock is an integer number of milliseconds stored with the aggregate. It advances
only when an accepted command supplies a bounded `duration_ms`; it never reads wall-clock time and
does not start a background loop. The initial state machine is deliberately small:

`parked → ready → driving → parked`

Each command carries a vehicle-scoped `command_id`, `expected_version`, target mode, duration, and
speed only when entering driving. A repeated identical command returns the original transition and
does not advance time or duplicate evidence. Reusing the identifier differently, skipping a state,
or submitting a stale version returns a stable conflict. Accepted transitions atomically update the
aggregate, persist replay metadata, audit the action, and publish
`atep.digital_vehicle.simulation.transitioned.v1`.

## Deterministic sensors and actuators

A simulation step accepts bounded accelerator, brake, and steering inputs and a duration of up to
60 seconds. Accelerator and brake cannot be applied together. Non-zero actuator inputs require the
vehicle to be in `driving` mode. The model updates speed, torque, hydraulic pressure, steering,
brake lamps, battery SOC, current, and temperature without reading wall-clock time.

Speed, battery SOC, and battery-temperature readings support bounded seeded noise plus explicit
`stuck` and `offset` faults. The noise value is derived from the supplied integer seed and sensor
name, so the same state and command always reproduce the same evidence. Sensor faults affect the
reported reading, while the authoritative physical state remains independently bounded.

Each accepted step advances simulation time, increments the aggregate version, persists command
inputs/configuration/readings for replay, records `digital_vehicle.simulation_stepped`, and enqueues
`atep.digital_vehicle.simulation.stepped.v1` in the same transaction. An exact retry returns the
stored result without repeating these effects.

## Coupled vehicle dynamics

The II-4 step model couples road grade, roughness, ambient temperature, and ambient light with the
existing actuators. Traction and auxiliary power produce energy consumption; braking produces a
bounded regenerative contribution. Published evidence retains used, recovered, and net Wh with the
identity `used - recovered = net` at contract precision, while usable battery energy and SOC remain
bounded.

Delivered torque includes regenerative braking, temperature combines load generation with ambient
cooling, and steering plus speed produces bounded lateral acceleration. Road roughness and
longitudinal inputs produce front/rear suspension travel. Brake lamps follow pedal input and low
ambient light selects low beam. The model is deliberately deterministic and scenario-oriented; it
is not a high-fidelity tyre, chassis, or thermal solver.

## Multi-vehicle sessions and snapshots

`POST /api/v1/simulation-sessions` creates a bounded composition of 1–20 unique registered
vehicles. Snapshots capture every member's aggregate version, logical time, and state in canonical
vehicle-identifier order and publish a SHA-256 digest over canonical JSON.

Restore locks matching members in deterministic order, applies each saved state only to its own
vehicle, restores logical time, and increments each current version. Session creation, snapshot,
and restore use `digital_vehicle:write`; session inspection uses `digital_vehicle:read`. Every
mutation records bounded audit and transactional outbox evidence.
