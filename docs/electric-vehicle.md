# Electric Vehicle Domain

## VI-1 Boundary

Volume VI owns high-fidelity electric-energy and propulsion behavior. Volume II retains the
lightweight whole-vehicle projection used for general simulation. VI-1 introduces a persistent,
vehicle-scoped battery aggregate that can later feed the BMS ECU, CAN signals, UDS data identifiers,
charging, powertrain limits, range prediction, and automated fault scenarios.

```text
Battery command
    -> optimistic version check
    -> coulomb-counting SOC model
    -> resistive-heating/passive-cooling thermal model
    -> BMS threshold evaluation
    -> ordered cell and pack projection
    -> battery step + audit + outbox (one transaction)
```

## Core Semantics

- LFP and NMC are explicit chemistry identifiers; VI-1 does not yet implement chemistry-specific
  open-circuit-voltage curves.
- A series pack contains 4 to 192 ordered deterministic cell projections.
- Positive pack current discharges the battery; negative pack current charges it.
- SOC uses coulomb counting against nominal capacity adjusted by SOH.
- Pack temperature uses a documented lumped thermal mass, internal resistance, passive cooling,
  ambient temperature, and logical duration.
- Normal and warning states keep contactors closed. Protection opens the contactors and delivered
  current becomes zero.
- Thermal protection is bounded at its trip threshold rather than extrapolating heating after the
  contactors have opened.
- Every accepted step advances `simulation_time_ms`; no background or wall-clock loop exists.

## Concurrency and Replay

The client supplies `expected_version`. A mutation obtains a database row lock and rejects stale
versions with `battery_state_version_conflict`. A command identifier is unique per vehicle. An
identical retry returns the persisted response snapshot with `duplicate=true`; different reuse
returns `battery_simulation_command_conflict`.

## Security and Evidence

`electric_vehicle:read` protects queries and `electric_vehicle:manage` protects creation and steps.
Creation emits `atep.electric_vehicle.battery.created.v1`; steps emit
`atep.electric_vehicle.battery.step.completed.v1`. Audit and event evidence includes pack-level
state and versions but intentionally excludes the full cell array.

## Deliberate VI-1 Limits

- SOH is persisted but degradation and cycle aging begin in a later increment.
- Cell balancing, sensor faults, thermal propagation, modules in parallel, and chemistry-specific
  voltage curves are future model refinements.
- Motor/inverter, regenerative braking, charging, thermal-control actuators, and range estimation
  remain VI-2 through VI-6 work.
- Cross-volume CAN, UDS, ECU, and automated-test orchestration is planned for VI-7.
