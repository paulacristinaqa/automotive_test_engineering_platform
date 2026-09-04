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

## VI-4 AC and DC Charging

VI-4 adds a vehicle-scoped charging-system aggregate and a deterministic command lifecycle for AC
Type 2 and DC CCS sessions.

```text
Charging command
    -> battery and charging row locks
    -> charging and battery version checks
    -> session-state transition validation
    -> connector, BMS, temperature, SOC, and energy-room limits
    -> battery SOC and contactor update
    -> command evidence + audit + outbox (one transaction)
```

- A session starts with a connector, target SOC, and requested input power. Starting closes the
  battery contactors; pausing, stopping, completion, and faults open them.
- AC charging is capped by the configured onboard-charger limit. DC charging is capped by the DC
  inlet limit and the battery current ceiling.
- Charge acceptance is unavailable in BMS protection, outside 0-50 C, or at the target SOC. Power
  is reduced near temperature-window edges and tapers above 80% SOC.
- A charge step cannot cross its target SOC because remaining battery energy room caps accepted
  power for the requested logical duration.
- The lifecycle supports `idle`, `charging`, `paused`, `completed`, and `faulted` states. Invalid
  transitions return a stable conflict.
- Commands support exact replay, changed-reuse rejection, separate charging/battery version
  conflicts, minimized evidence, audit, and transactional outbox publication.

## VI-5 Active Thermal Management

VI-5 coordinates the existing battery and motor temperature states with a vehicle-scoped thermal
controller and cabin model.

```text
Thermal step
    -> battery, motor, and thermal row locks
    -> three independent optimistic-version checks
    -> bounded heating or cooling requests for four thermal zones
    -> ambient exchange and cabin heat-load integration
    -> battery, motor, inverter, cabin, replay, audit, and outbox commit
```

- Positive actuator power heats a zone and negative power cools it.
- Proportional requests are capped by separate battery, combined powertrain, and cabin ratings.
- The motor receives at most 60% of the powertrain budget; the inverter uses the remaining budget.
- Logical temperature changes use explicit thermal masses and ambient-loss coefficients.
- Disabled or faulted control draws zero auxiliary power while passive ambient exchange continues.
- Exact replay returns the stored cross-aggregate result. Changed reuse and stale thermal, battery,
  or motor versions return distinct stable conflicts.

## VI-6 Deterministic Range Estimation

VI-6 evaluates bounded drive-cycle segments using local physical calibration. Rolling resistance,
aerodynamic drag, grade, acceleration, drivetrain loss, regenerative recovery, battery SOC/SOH and
reserve, plus thermal auxiliary demand produce an explainable consumption and range result.
Commands support exact replay and independent range, battery, and thermal version checks. No map,
weather, cloud, LLM, or paid API is required.

## Deliberate VI-1 through VI-6 Limits

- SOH is persisted but degradation and cycle aging begin in a later increment.
- Cell balancing, sensor faults, thermal propagation, modules in parallel, and chemistry-specific
  voltage curves are future model refinements.
- Range evaluation is analytical and does not debit battery SOC until VI-7 defines cross-domain trips.
- VI-2 uses an explainable analytic efficiency surface rather than a production calibration map.
- The motor step reads battery availability but does not yet debit battery SOC; full coupled energy
  flow is introduced with cross-domain drive scenarios.
- Cross-volume CAN, UDS, ECU, and automated-test orchestration is planned for VI-7.
- VI-3 uses a quasi-static step and does not integrate vehicle speed or hydraulic pressure over
  time; those dynamics remain future fidelity work.
- VI-4 uses an explainable charging curve rather than chemistry- or charger-specific calibration
  maps, and does not yet simulate EVSE protocol handshakes or grid behavior.
- VI-5 uses lumped thermal zones and proportional control rather than coolant-flow, heat-pump,
  refrigerant, or passenger-comfort calibration maps.
