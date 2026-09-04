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

## VI-2 Motor and Inverter

VI-2 adds a separate motor/inverter aggregate whose available propulsion power is derived from the
authoritative battery pack at every commanded step. The model exposes requested and delivered
torque, motor speed, mechanical and electrical power, efficiency, loss, motor temperature,
inverter temperature, drive mode, operating state, and a stable limiting reason.

```text
Motor command
    -> motor state and battery row locks
    -> optimistic version check
    -> drive-mode torque ceiling
    -> battery/inverter electrical-power ceiling
    -> deterministic efficiency and thermal calculations
    -> ready, derated, or protection classification
    -> motor step + audit + outbox (one transaction)
```

- Eco, normal, and sport expose 60%, 85%, and 100% of configured peak torque.
- Mechanical power follows torque multiplied by angular speed; electrical power accounts for the
  deterministic efficiency surface, and their difference is recorded as power loss.
- Battery contactors and BMS protection can reduce available power to zero. BMS warning reduces
  the assumed battery current ceiling from 1,000 A to 600 A.
- Speed above the configured motor limit produces zero delivered torque.
- Motor temperature at 150 C or inverter temperature at 110 C enters protection and removes
  delivered torque and power.
- Negative propulsion torque remains rejected; VI-3 represents regeneration through an explicit
  requested-deceleration contract.
- Commands preserve the VI-1 logical-time, optimistic-version, exact-replay, audit, and outbox
  patterns.

## VI-3 Regenerative and Blended Braking

VI-3 adds a separate regenerative-braking aggregate. It locks the motor, battery, and braking rows
in a fixed order, validates braking and battery versions, and allocates requested deceleration
between electrical recovery and friction braking.

```text
Brake command
    -> motor, battery, and braking row locks
    -> braking and battery version checks
    -> motor torque and battery charge-acceptance limits
    -> regenerative/friction force allocation
    -> recovered power, energy, and battery SOC update
    -> brake step + audit + outbox (one transaction)
```

- Regeneration is disabled below 0.5 m/s, with open contactors, in BMS protection, at or above
  95% SOC, or outside the 0-50 C battery temperature window.
- Charge acceptance tapers between 80% and 95% SOC and is reduced near the temperature window
  edges or while the BMS is in warning. The remaining energy room also caps long steps so one
  command cannot cross the 95% regenerative ceiling.
- Regenerative force is limited by motor torque, final drive, drivetrain efficiency, wheel radius,
  configured regenerative power, and battery acceptance.
- Friction braking supplies the remaining request up to its configured deceleration capacity.
- Recovered electrical energy advances battery SOC, battery version, and battery logical time in
  the same transaction as braking state, command evidence, audit, and outbox.
- Operating states are `standby`, `regenerative`, `blended`, `friction`, and `limited`.

## Deliberate VI-1 through VI-3 Limits

- SOH is persisted but degradation and cycle aging begin in a later increment.
- Cell balancing, sensor faults, thermal propagation, modules in parallel, and chemistry-specific
  voltage curves are future model refinements.
- Charging, thermal-control actuators, and range estimation remain VI-4 through VI-6 work.
- VI-2 uses an explainable analytic efficiency surface rather than a production calibration map.
- The motor step reads battery availability but does not yet debit battery SOC; full coupled energy
  flow is introduced with cross-domain drive scenarios.
- Cross-volume CAN, UDS, ECU, and automated-test orchestration is planned for VI-7.
- VI-3 uses a quasi-static step and does not integrate vehicle speed or hydraulic pressure over
  time; those dynamics remain future fidelity work.
