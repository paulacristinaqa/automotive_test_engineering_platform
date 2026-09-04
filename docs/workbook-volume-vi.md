# ATEP Engineering Workbook - Volume VI: Electric Vehicle

## Document Control

| Field | Value |
|---|---|
| Document | ATEP Engineering Workbook - Volume VI: Electric Vehicle |
| Version | 0.6.0 |
| Baseline date | 4 September 2026 |
| Status | VI-1 through VI-6 implemented, including deterministic range estimation |
| Audience | Automotive software, simulation, QA, functional-safety, and platform engineers |

## 1. Purpose and Scope

Volume VI turns the platform's general digital vehicle into a testable electric-energy system.
VI-1 establishes a persistent battery pack and deterministic BMS behavior. VI-2 adds a persistent
motor/inverter aggregate, torque delivery, efficiency, power loss, thermal protection, drive-mode
limits, and battery-derived propulsion availability. VI-3 adds requested-deceleration control,
regenerative energy recovery, battery charge acceptance, and blended friction braking.
VI-4 adds AC/DC charging sessions, deterministic charge curves, lifecycle control, and faults.
VI-5 adds coordinated heating and cooling for the battery, motor, inverter, and cabin.
VI-6 adds deterministic energy-consumption and remaining-range estimates for bounded drive cycles.

### In Scope for VI-1

- one battery pack per registered vehicle;
- LFP and NMC identifiers;
- 4 to 192 ordered series-cell projections;
- capacity, energy, SOC, SOH, voltage, current, power, and temperature;
- logical-time electrical and thermal steps;
- normal, warning, and protection BMS states;
- contactor opening on protection;
- optimistic concurrency and exact idempotent replay;
- dedicated RBAC, audit, outbox, migration, API, and automated tests.

### In Scope for VI-2

- one motor/inverter state per battery-equipped vehicle;
- requested and delivered torque, speed, mechanical/electrical power, efficiency, and loss;
- eco, normal, and sport torque ceilings;
- battery contactor, BMS, voltage, and inverter power constraints;
- motor and inverter thermal evolution and protection;
- stable limiting reasons, optimistic concurrency, exact replay, audit, and outbox evidence.

### In Scope for VI-3

- one regenerative-braking state per battery- and motor-equipped vehicle;
- regenerative and friction allocation with deterministic power and energy recovery;
- motor, drivetrain, speed, battery-acceptance, and friction limits;
- braking and battery optimistic versions, exact replay, audit, and outbox evidence.

### In Scope for VI-4

- one charging-system state per battery-equipped vehicle;
- AC Type 2 and DC CCS connector contracts with separate power limits;
- deterministic session lifecycle, SOC integration, taper, target, and temperature limits;
- charging and battery optimistic versions, exact replay, audit, and outbox evidence.

### In Scope for VI-5

- one vehicle-scoped state with independent battery, motor, inverter, and cabin targets;
- bounded actuators, ambient exchange, cabin heat load, logical-time integration, and auxiliary demand;
- disabled and faulted operation with triple versioning, exact replay, audit, and outbox evidence.

### In Scope for VI-6

- one calibrated range estimator per battery- and thermal-equipped vehicle;
- bounded drive-cycle segments containing duration, speed, acceleration, and road grade;
- traction, auxiliary, regenerative, net-energy, consumption, and remaining-range evidence;
- range, battery, and thermal optimistic versions, exact replay, audit, and outbox evidence.

### Deferred

- chemistry-specific circuits, cell balancing, aging, sensor faults, and module topology;
- calibrated thermal circuits and BMS ECU, CAN, UDS, dashboard, and test orchestration.

## 2. Architecture

The FastAPI electric-vehicle boundary uses `electric_vehicle:read` and
`electric_vehicle:manage`. `BatteryPackState`, `MotorInverterState`,
`RegenerativeBrakeState`, `ChargingSystemState`, `ThermalManagementState`, and
`RangeEstimatorState` own the battery, propulsion, braking, charging, thermal, and range
aggregates. Their simulation
step records preserve immutable replay evidence. `AuditRecord` and `OutboxEvent` commit in the
same database transaction as each accepted mutation.

### Cross-Volume Ownership

Volume II owns whole-vehicle aggregate state and lightweight coupled dynamics. Volume VI owns the
deeper EV energy and propulsion models. The BMS ECU remains a Volume III controller and will consume
Volume VI state through explicit integration contracts rather than sharing database internals.

## 3. Domain Model

| Aggregate or value | Responsibility | Key bounds |
|---|---|---|
| BatteryPackState | Authoritative vehicle battery state | one per vehicle; version >= 1 |
| BatteryCellState | Ordered cell projection | 4 to 192; voltage 2.0-5.0 V; temperature -50 to 120 C |
| Simulation step | Command identity and immutable result snapshot | duration 1-3,600,000 ms |
| Chemistry | Stable chemistry identifier | `lfp`, `nmc` |
| Operating state | BMS decision | `normal`, `warning`, `protection` |
| Contactor state | High-voltage isolation state | `open`, `closed` |
| MotorInverterState | Authoritative propulsion state | one per vehicle; version >= 1 |
| Drive mode | Driver-selectable torque policy | `eco`, `normal`, `sport` |
| Powertrain state | Propulsion decision | `standby`, `ready`, `derated`, `protection` |
| RegenerativeBrakeState | Braking strategy and recovered energy | one per vehicle; version >= 1 |
| Brake state | Current allocation decision | `standby`, `regenerative`, `blended`, `friction`, `limited` |
| ChargingSystemState | Current charging session and energy transfer | one per vehicle; version >= 1 |
| Connector type | Physical charging path | `ac_type_2`, `dc_ccs` |
| Charging state | Session lifecycle | `idle`, `charging`, `paused`, `completed`, `faulted` |
| ThermalManagementState | Zone targets, cabin state, and actuator demand | one per vehicle; version >= 1 |
| Thermal state | Current controller outcome | `standby`, `heating`, `cooling`, `mixed`, `faulted` |
| RangeEstimatorState | Drive-cycle energy and remaining range | one per vehicle; version >= 1 |
| DriveCycleSegment | Reproducible route assumption | 1-3,600 s; 0-250 km/h; bounded acceleration and grade |

### Sign Convention

Positive current is discharge. Negative current is charge. Pack power follows the same sign. This
convention is explicit in the API and tests so future motor, charger, and regeneration modules do
not silently invert energy flow.

## 4. Engineering Model

SOC is updated by coulomb counting:

- Usable capacity (Ah) = nominal capacity (Ah) multiplied by SOH / 100.
- SOC delta (%) = current (A) multiplied by duration (h), divided by usable capacity, multiplied by 100.
- New SOC (%) = previous SOC minus SOC delta, clamped between 0 and 100.

Temperature uses a deterministic lumped model:

- Resistive heat (W) = current squared multiplied by internal resistance.
- Net heat (W) = resistive heat minus the cooling coefficient multiplied by the pack-to-ambient
  temperature difference.
- Temperature delta (C) = net heat multiplied by duration (s), divided by thermal mass (J/C).

VI-1 uses a 300,000 J/C thermal mass and 35 W/C passive-cooling coefficient. These values are
simulation parameters, not production calibration data. When the projected temperature reaches a
protection boundary, the model stops at the boundary, opens contactors, and reports zero delivered
current rather than extrapolating heating beyond isolation.

### VI-2 Propulsion Model

- Mode torque ceiling = configured peak torque multiplied by 0.60, 0.85, or 1.00 for eco, normal, or sport.
- Mechanical power (kW) = delivered torque multiplied by 2 pi multiplied by rpm / 60 / 1,000.
- Electrical power (kW) = mechanical power divided by deterministic efficiency.
- Conversion loss (kW) = electrical power minus mechanical power.
- Available power is the lower of inverter rating and battery voltage multiplied by the BMS current ceiling.
- Motor and inverter temperatures integrate conversion loss and passive cooling over logical time.

### VI-3 Braking Model

- Requested braking force (N) = vehicle mass multiplied by requested deceleration.
- Regenerative force is bounded by motor torque, final-drive ratio, drivetrain efficiency, and wheel radius.
- Battery-limited regenerative force is charge acceptance divided by speed and regeneration efficiency.
- Friction force supplies the remaining request within its configured limit.
- Recovered power uses force, speed, and efficiency; its logical-time integral increases SOC using
  SOH-adjusted pack energy.

Charge acceptance is zero below 0.5 m/s, with open contactors, in BMS protection, at or above 95%
SOC, or outside 0-50 C. It tapers from 80% to 95% SOC, is reduced near the temperature limits, and
is capped by the remaining energy room so a long step cannot cross 95% SOC.

### VI-4 Charging Model

- AC input power is capped by the configured onboard-charger limit.
- DC input power is capped by the configured DC inlet and battery current ceiling.
- Battery power equals delivered input power multiplied by charging efficiency.
- Step energy integrates accepted power over logical time and remaining energy caps the step at its
  target SOC.
- Charge acceptance is zero in BMS protection, outside 0-50 C, or at the target SOC.
- Above 80% SOC, the analytic curve tapers power toward zero at the configured target.

### VI-5 Thermal Control Model

- Zone request (kW) equals target minus actual temperature multiplied by 0.5 kW/C, capped by capacity.
- Positive actuator power heats a zone; negative actuator power cools it.
- Battery, motor, inverter, and cabin temperatures integrate actuator power, ambient exchange,
  and logical duration against explicit lumped thermal masses.
- Motor output uses at most 60% of the powertrain budget. Inverter output uses the remainder.
- Cabin temperature also integrates a bounded passenger, solar, or equipment heat load.
- Auxiliary demand is the sum of absolute zone powers. Disabled or faulted control draws zero.

### VI-6 Range Model

- Segment force combines rolling resistance, aerodynamic drag, road grade, and acceleration.
- Positive mechanical work is divided by drivetrain efficiency to obtain traction energy.
- Negative mechanical work is multiplied by regenerative efficiency to obtain recovered energy.
- Auxiliary energy integrates baseline demand plus the current thermal-system demand.
- Net energy equals traction plus auxiliary energy minus recovered energy, with a zero floor.
- Consumption is net energy per distance, expressed in kWh/100 km.
- Available energy uses nominal pack energy, SOH, SOC, and the configured reserve SOC.
- Estimated range equals available energy divided by consumption. Stationary cycles return an
  explicit limited result.

## 5. BMS State Policy

| Condition | State | Contactors | Delivered current |
|---|---|---|---|
| Temperature at/below -30 C or at/above 60 C | Protection | Open | 0 A |
| Discharge at 0% SOC or charge at 100% SOC | Protection | Open | 0 A |
| Temperature at/below -20 C or at/above 50 C | Warning | Closed | Requested current |
| SOC at/below 10% | Warning | Closed | Requested current |
| Otherwise | Normal | Closed | Requested current |

The limits are deliberately simple and deterministic. Production BMS calibration would add
hysteresis, debounce, chemistry, current, voltage, isolation, and sensor-plausibility policies.

## 6. API Contract

| Method and route | Objective | Permission |
|---|---|---|
| `POST /api/v1/vehicles/{vehicle_id}/electric/battery` | Create the vehicle battery baseline | `electric_vehicle:manage` |
| `GET /api/v1/vehicles/{vehicle_id}/electric/battery` | Read pack, BMS, and cell state | `electric_vehicle:read` |
| `POST /api/v1/vehicles/{vehicle_id}/electric/battery/steps` | Execute a deterministic electrical/thermal step | `electric_vehicle:manage` |
| `POST /api/v1/vehicles/{vehicle_id}/electric/powertrain` | Create the motor/inverter baseline | `electric_vehicle:manage` |
| `GET /api/v1/vehicles/{vehicle_id}/electric/powertrain` | Read torque, power, efficiency, and thermal state | `electric_vehicle:read` |
| `POST /api/v1/vehicles/{vehicle_id}/electric/powertrain/steps` | Execute a deterministic propulsion step | `electric_vehicle:manage` |
| `POST /api/v1/vehicles/{vehicle_id}/electric/braking` | Create the regenerative-braking baseline | `electric_vehicle:manage` |
| `GET /api/v1/vehicles/{vehicle_id}/electric/braking` | Read braking allocation and recovery state | `electric_vehicle:read` |
| `POST /api/v1/vehicles/{vehicle_id}/electric/braking/steps` | Execute a deterministic braking step | `electric_vehicle:manage` |
| `POST /api/v1/vehicles/{vehicle_id}/electric/charging` | Create the charging-system baseline | `electric_vehicle:manage` |
| `GET /api/v1/vehicles/{vehicle_id}/electric/charging` | Read the current session and charging state | `electric_vehicle:read` |
| `POST /api/v1/vehicles/{vehicle_id}/electric/charging/commands` | Execute a versioned lifecycle or energy command | `electric_vehicle:manage` |
| `POST /api/v1/vehicles/{vehicle_id}/electric/thermal` | Create thermal targets and actuator capacities | `electric_vehicle:manage` |
| `GET /api/v1/vehicles/{vehicle_id}/electric/thermal` | Read zone temperatures, output, and state | `electric_vehicle:read` |
| `POST /api/v1/vehicles/{vehicle_id}/electric/thermal/steps` | Execute one deterministic thermal-control step | `electric_vehicle:manage` |
| `POST /api/v1/vehicles/{vehicle_id}/electric/range` | Create range calibration | `electric_vehicle:manage` |
| `GET /api/v1/vehicles/{vehicle_id}/electric/range` | Read the latest estimate | `electric_vehicle:read` |
| `POST /api/v1/vehicles/{vehicle_id}/electric/range/cycles` | Evaluate one reproducible drive cycle | `electric_vehicle:manage` |

### Stable Errors

| Code | Meaning |
|---|---|
| `battery_pack_already_exists` | The vehicle already owns a battery pack. |
| `battery_pack_not_found` | No battery pack exists for the vehicle. |
| `battery_state_version_conflict` | `expected_version` is stale. |
| `battery_simulation_command_conflict` | A command ID was reused with different content. |
| `motor_inverter_already_exists` | The vehicle already owns a motor/inverter state. |
| `motor_inverter_not_found` | No motor/inverter state exists for the vehicle. |
| `motor_state_version_conflict` | The powertrain `expected_version` is stale. |
| `motor_simulation_command_conflict` | A motor command ID was reused differently. |
| `regenerative_brake_already_exists` | The vehicle already owns braking state. |
| `regenerative_brake_not_found` | No braking state exists for the vehicle. |
| `brake_state_version_conflict` | The braking `expected_version` is stale. |
| `brake_battery_version_conflict` | The battery version supplied to braking is stale. |
| `brake_simulation_command_conflict` | A braking command ID was reused differently. |
| `charging_system_already_exists` | The vehicle already owns charging state. |
| `charging_system_not_found` | No charging state exists for the vehicle. |
| `charging_state_version_conflict` | The charging `expected_version` is stale. |
| `charging_battery_version_conflict` | The battery version supplied to charging is stale. |
| `charging_command_conflict` | A charging command ID was reused differently. |
| `charging_transition_invalid` | An action is invalid from the current lifecycle state. |
| `thermal_management_already_exists` | The vehicle already owns thermal-management state. |
| `thermal_management_not_found` | No thermal-management state exists for the vehicle. |
| `thermal_state_version_conflict` | The thermal state version is stale. |
| `thermal_battery_version_conflict` | The battery version supplied to thermal control is stale. |
| `thermal_motor_version_conflict` | The motor version supplied to thermal control is stale. |
| `thermal_command_conflict` | A thermal command ID was reused differently. |
| `range_estimator_already_exists` | The vehicle already owns range-estimator state. |
| `range_estimator_not_found` | No range estimator exists for the vehicle. |
| `range_state_version_conflict` | The range estimator version is stale. |
| `range_battery_version_conflict` | The battery version supplied to the estimate is stale. |
| `range_thermal_version_conflict` | The thermal version supplied to the estimate is stale. |
| `range_estimation_command_conflict` | A range command ID was reused differently. |
| `forbidden` | The authenticated user lacks the required permission. |
| `validation_error` | A request violates a declared bound or format. |

## 7. Persistence and Events

Migration `0037_battery_bms_foundation` creates `battery_pack_states` and
`battery_simulation_steps`. Migration `0038_motor_inverter` creates `motor_inverter_states` and
`motor_simulation_steps`. Migration `0039_regenerative_braking` creates
`regenerative_brake_states` and `brake_simulation_steps`. Database checks reinforce bounded
states, versions, and durations. Migration `0040_charging_sessions` creates
`charging_system_states` and `charging_command_steps`. Migration `0041_thermal_management` creates
`thermal_management_states` and `thermal_management_steps`.
Migration `0042_range_estimation` creates `range_estimator_states` and
`range_estimation_steps`.

| Event | Purpose | Privacy/minimization rule |
|---|---|---|
| `atep.electric_vehicle.battery.created.v1` | Announce a configured pack | Pack metadata only; no full cells |
| `atep.electric_vehicle.battery.step.completed.v1` | Announce deterministic state evolution | Pack summary and versions; no full cells |
| `atep.electric_vehicle.motor_inverter.created.v1` | Announce configured propulsion hardware | Bounded configuration only |
| `atep.electric_vehicle.motor.step.completed.v1` | Announce torque and power outcome | Summary, limit reason, and versions |
| `atep.electric_vehicle.regenerative_brake.created.v1` | Announce braking configuration | Bounded configuration only |
| `atep.electric_vehicle.brake.step.completed.v1` | Announce allocation and recovered energy | Summary, SOC, limit reason, and versions |
| `atep.electric_vehicle.charging_system.created.v1` | Announce charging capability | Bounded AC/DC configuration only |
| `atep.electric_vehicle.charging.command.completed.v1` | Announce lifecycle and energy outcome | Session summary and versions; no cells |
| `atep.electric_vehicle.thermal_management.created.v1` | Announce thermal targets and capacities | Bounded configuration only |
| `atep.electric_vehicle.thermal.step.completed.v1` | Announce temperatures and actuator demand | Zone summary and versions; no cells |
| `atep.electric_vehicle.range_estimator.created.v1` | Announce calibrated range estimation | Bounded calibration only |
| `atep.electric_vehicle.range.cycle.completed.v1` | Announce drive-cycle outcome | Consumption, range, cycle ID, and version |

## 8. Requirements Baseline

VI-1 through VI-6 implement EV-F-001 through EV-F-089 and EV-NF-001 through EV-NF-029. The authoritative
traceability table is maintained in `docs/requirements-volume-vi.md`.

## 9. Architecture Decisions

### ADR-EV-001 - Separate High-Fidelity EV State from the Volume II Projection

Decision: keep a dedicated battery aggregate in Volume VI. Rationale: Volume II needs inexpensive
whole-vehicle simulation, while EV validation needs deeper cell, electrical, thermal, and BMS
evidence. An explicit integration contract avoids one oversized aggregate.

### ADR-EV-002 - Use Logical Time and Commanded Steps

Decision: accept bounded `duration_ms` commands and persist `simulation_time_ms`. Rationale: tests
must be deterministic, fast, replayable, and independent of scheduler timing.

### ADR-EV-003 - Persist Successful Replay Snapshots

Decision: persist the complete client response for each command while minimizing shared event and
audit payloads. Rationale: an exact retry remains stable even after later pack mutations.

### ADR-EV-004 - Model Protection as Isolation at the Boundary

Decision: clamp a thermal transition at the protection threshold and set delivered current to zero.
Rationale: continuing full-current heating after contactor opening would create invalid evidence.

### ADR-EV-005 - Keep Battery and Propulsion Aggregates Separate

Decision: motor commands lock and read the battery aggregate but persist propulsion state in a
dedicated aggregate. Rationale: explicit ownership prevents a single oversized EV state while
still producing consistent power-limit evidence.

### ADR-EV-006 - Use an Explainable Analytic Efficiency Surface

Decision: VI-2 derives efficiency from bounded torque and speed ratios. Rationale: the model is
portable, deterministic, and auditable without proprietary calibration data. Versioned efficiency
maps can replace it later behind the same contract.

### ADR-EV-007 - Reserve Negative Torque for Regeneration

Decision: reject negative requested torque in VI-2. Rationale: regeneration requires battery
charge-acceptance and blended-brake policies that belong together in VI-3.

### ADR-EV-008 - Represent Braking as Requested Deceleration

Decision: expose nonnegative requested deceleration rather than negative propulsion torque.
Rationale: the service can allocate one vehicle-level request across regenerative and friction
actuators without overloading the propulsion command contract.

### ADR-EV-009 - Update Recovered Battery Energy Atomically

Decision: a regenerative step validates the battery version and commits recovered energy, SOC,
braking state, replay evidence, audit, and outbox together. Rationale: partial energy evidence would
make cross-domain test results internally inconsistent.

### ADR-EV-010 - Use Deterministic Charge-Acceptance Tapering

Decision: VI-3 uses explicit SOC, temperature, contactor, BMS, voltage, and current ceilings.
Rationale: explainable bounds support repeatable QA before chemistry-specific calibration exists.

### ADR-EV-011 - Model Charging as a Versioned State Machine

Decision: express session start, energy transfer, pause, resume, stop, fault injection, and fault
clearing as explicit actions. Rationale: invalid transitions become stable test evidence rather
than implicit side effects.

### ADR-EV-012 - Commit Charging and Battery State Together

Decision: charging commands validate both versions and commit battery contactors, SOC, session
state, replay evidence, audit, and outbox in one transaction. Rationale: a session result cannot
claim transferred energy without the matching battery state.

### ADR-EV-013 - Use Bounded Proportional Thermal Control

Decision: derive each zone request from its target error and cap it by declared actuator capacity.
Rationale: the controller remains deterministic and explainable without proprietary calibration.

### ADR-EV-014 - Commit Thermal Zones and Component Temperatures Together

Decision: lock battery, motor, and thermal state in a fixed order and validate all three versions.
Rationale: thermal evidence cannot describe cooling that is absent from component state.

### ADR-EV-015 - Preserve Passive Exchange When Control Is Inactive

Decision: set actuator output to zero but continue ambient exchange during disabled and faulted
operation. Rationale: stopping the controller must not freeze physical temperature state.

### ADR-EV-016 - Use Reproducible Drive-Cycle Segments

Decision: represent a route as bounded duration, speed, acceleration, and grade segments rather
than querying a map provider. Rationale: the same input remains deterministic, local, free, and
usable in regression tests.

### ADR-EV-017 - Estimate Without Mutating Battery Energy

Decision: VI-6 reads versioned battery and thermal state but treats a drive cycle as an analytical
estimate. Rationale: repeated scenario execution must not silently debit SOC before VI-7 defines a
cross-domain trip transaction.

## 10. Test Catalogue

| ID | Test | Objective | Expected result |
|---|---|---|---|
| EV-T-001 | Cell-count lower bound | Reject fewer than four cells | Stable validation error |
| EV-T-002 | Cell-count upper bound | Reject more than 192 cells | Stable validation error |
| EV-T-003 | Current bounds | Reject current outside +/-1,000 A | Stable validation error |
| EV-T-004 | Duration bounds | Reject zero or over-one-hour steps | Stable validation error |
| EV-T-005 | Battery creation | Create one pack with ordered cells | Version 1, contactors open |
| EV-T-006 | Duplicate pack | Enforce one pack per vehicle | Stable 409 conflict |
| EV-T-007 | Discharge SOC | Verify positive-current coulomb counting | SOC decreases deterministically |
| EV-T-008 | Charge SOC | Verify negative-current sign convention | SOC increases deterministically |
| EV-T-009 | Resistive heating | Verify current-squared heat input | Temperature matches formula |
| EV-T-010 | Passive cooling | Verify convergence toward ambient | Temperature decreases when pack is hotter |
| EV-T-011 | Low-SOC warning | Exercise the warning threshold | Warning with contactors closed |
| EV-T-012 | Overtemperature protection | Exercise the 60 C boundary | Protection, contactors open, 0 A |
| EV-T-013 | Empty-pack protection | Discharge at the lower SOC bound | Protection and no delivered current |
| EV-T-014 | Full-pack charge protection | Charge at the upper SOC bound | Protection and no delivered current |
| EV-T-015 | Version conflict | Submit a stale expected version | Stable conflict with current version |
| EV-T-016 | Exact replay | Retry an identical command | Persisted snapshot, duplicate true |
| EV-T-017 | Changed reuse | Reuse ID with different input | Stable command conflict |
| EV-T-018 | RBAC read denial | Query without read permission | HTTP 403 |
| EV-T-019 | RBAC mutation denial | Mutate without manage permission | HTTP 403 |
| EV-T-020 | Atomic evidence | Observe pack/step, audit, and outbox transaction | All commit or all roll back |
| EV-T-021 | Evidence minimization | Inspect audit and event payloads | No full cell array |
| EV-T-022 | OpenAPI contract | Inspect routes and numeric limits | Versioned bounded schema published |
| EV-T-023 | Migration upgrade | Apply revision from Volume V head | Both VI-1 tables and indexes exist |
| EV-T-024 | Migration downgrade | Revert revision in disposable database | VI-1 tables removed cleanly |
| EV-T-025 | Motor creation | Create one state after battery creation | Version 1 and standby |
| EV-T-026 | Duplicate motor | Enforce one state per vehicle | Stable 409 conflict |
| EV-T-027 | Normal torque delivery | Request torque within all limits | Requested torque delivered |
| EV-T-028 | Mechanical power | Apply torque at nonzero speed | Torque times angular speed |
| EV-T-029 | Electrical power | Inspect conversion input | Greater than mechanical power |
| EV-T-030 | Efficiency loss | Compare electrical and mechanical power | Positive deterministic loss |
| EV-T-031 | Eco limit | Request peak torque in eco | Delivery capped at 60% |
| EV-T-032 | Normal limit | Request peak torque in normal | Delivery capped at 85% |
| EV-T-033 | Sport limit | Request peak torque in sport | Delivery capped at 100% |
| EV-T-034 | Battery unavailable | Open battery contactors | Zero delivered torque |
| EV-T-035 | Battery power limit | Exceed available electrical power | Derated torque and reason |
| EV-T-036 | Overspeed | Exceed configured motor speed | Zero torque and speed-limit reason |
| EV-T-037 | Thermal protection | Reach motor or inverter trip | Protection and zero power |
| EV-T-038 | Regen deferred | Submit negative torque | Stable validation error |
| EV-T-039 | Motor exact replay | Retry identical motor command | Persisted snapshot returned |
| EV-T-040 | Motor changed reuse | Reuse ID with changed input | Stable command conflict |
| EV-T-041 | Motor version conflict | Submit stale state version | Current version returned |
| EV-T-042 | Motor atomic evidence | Inspect step, audit, and outbox | All commit or all roll back |
| EV-T-043 | Powertrain OpenAPI | Inspect routes and physical bounds | Bounded schema published |
| EV-T-044 | Migration 0038 | Upgrade and downgrade disposable DB | Tables created and removed cleanly |
| EV-T-045 | Braking creation | Create state after battery and motor | Version 1 and standby |
| EV-T-046 | Duplicate braking state | Enforce one state per vehicle | Stable 409 conflict |
| EV-T-047 | Pure regeneration | Request deceleration within regenerative capacity | No friction contribution |
| EV-T-048 | Blended braking | Exceed regenerative torque capacity | Regen plus friction meets request |
| EV-T-049 | Low-speed fallback | Brake below 0.5 m/s | Friction only and stable reason |
| EV-T-050 | High-SOC fallback | Brake at or above 95% SOC | Friction only and no recovered energy |
| EV-T-051 | Open-contactor fallback | Brake with contactors open | Friction only and stable reason |
| EV-T-052 | Temperature acceptance | Brake outside charge window | Regeneration unavailable |
| EV-T-053 | Charge taper | Compare acceptance at 80% and near 95% SOC | Higher SOC has lower acceptance |
| EV-T-054 | Regen torque limit | Exceed recoverable motor torque | Stable torque-limit reason |
| EV-T-055 | Battery power limit | Exceed charge acceptance | Stable charge-limit reason |
| EV-T-056 | Brake capacity | Exceed combined capacity | Limited delivered deceleration |
| EV-T-057 | Recovered power | Verify force, speed, and efficiency formula | Deterministic electrical power |
| EV-T-058 | Recovered energy and SOC | Integrate a logical step | Energy and SOC increase atomically |
| EV-T-059 | Braking exact replay | Retry identical command | Persisted cross-aggregate snapshot |
| EV-T-060 | Braking changed reuse | Reuse ID with changed input | Stable command conflict |
| EV-T-061 | Braking version conflict | Submit stale braking version | Current version returned |
| EV-T-062 | Battery version conflict | Submit stale battery version | Current battery version returned |
| EV-T-063 | Braking atomic evidence | Inspect state, battery, step, audit, outbox | All commit or all roll back |
| EV-T-064 | Braking OpenAPI | Inspect routes and numeric bounds | Bounded schema published |
| EV-T-065 | Migration 0039 | Upgrade and downgrade disposable DB | Tables created and removed cleanly |
| EV-T-066 | Long-step SOC ceiling | Recover energy near 95% SOC for one hour | SOC stops at 95% and friction supplies the remainder |
| EV-T-067 | Charging contract bounds | Exceed AC/DC power or omit action fields | Stable validation error |
| EV-T-068 | Charging-system creation | Create one state for a battery-equipped vehicle | Version 1 and idle |
| EV-T-069 | Session start | Start with connector, target, and power | Charging and contactors closed |
| EV-T-070 | AC energy transfer | Charge through AC Type 2 | Energy and SOC increase deterministically |
| EV-T-071 | DC power limit | Request above DC or battery capacity | Delivered power is capped |
| EV-T-072 | Charge taper | Compare DC acceptance below and above 80% SOC | Higher SOC has lower acceptance |
| EV-T-073 | Target-SOC ceiling | Use a long step near the target | Exact target, completed, contactors open |
| EV-T-074 | Temperature limit | Charge outside 0-50 C | No transferred energy and stable reason |
| EV-T-075 | Pause and resume | Interrupt and continue a session | Valid state and contactor transitions |
| EV-T-076 | Manual stop | Stop an active or paused session | Completed and isolated |
| EV-T-077 | Fault lifecycle | Inject and clear a charging fault | Fault preserved, isolated, then idle |
| EV-T-078 | Invalid transition | Charge while idle | Stable transition conflict |
| EV-T-079 | Charging exact replay | Retry an identical command | Persisted snapshot, no duplicate energy |
| EV-T-080 | Charging changed reuse | Reuse command ID differently | Stable command conflict |
| EV-T-081 | Dual version conflicts | Submit stale charging or battery version | Distinct current version returned |
| EV-T-082 | Charging OpenAPI and migration | Inspect routes and revision 0040 | Bounded schema and reversible tables |
| EV-T-083 | Thermal contract bounds | Exceed power, target, duration, load, or fault bounds | Stable validation error |
| EV-T-084 | Thermal-system creation | Create state after battery and motor | Version 1 and standby |
| EV-T-085 | Hot battery cooling | Run an enabled step above target | Bounded cooling and lower temperature |
| EV-T-086 | Cold cabin heating | Run an enabled step below target | Bounded heating and higher temperature |
| EV-T-087 | Mixed operation | Cool components while heating the cabin | Mixed state and combined demand |
| EV-T-088 | Powertrain budget | Demand motor and inverter cooling | Combined output stays within capacity |
| EV-T-089 | Passive exchange | Disable control away from ambient | Zero auxiliary power and passive evolution |
| EV-T-090 | Cabin heat load | Compare equal steps with and without load | Loaded cabin retains more heat |
| EV-T-091 | Thermal fault | Inject a pump or sensor fault | Faulted state, stable code, zero output |
| EV-T-092 | Thermal exact replay | Retry an identical command | Persisted snapshot and no repeated integration |
| EV-T-093 | Thermal changed reuse | Reuse the ID with changed input | Stable command conflict |
| EV-T-094 | Triple version conflicts | Submit stale thermal, battery, or motor version | Distinct current version returned |
| EV-T-095 | Thermal atomic evidence | Inspect states, step, audit, and outbox | All commit or all roll back |
| EV-T-096 | Thermal OpenAPI and migration | Inspect routes and revision 0041 | Bounded schema and reversible tables |
| EV-T-097 | Range contract bounds | Exceed calibration, segment, or collection limits | Stable validation error |
| EV-T-098 | Range-estimator creation | Create one estimator after battery and thermal setup | Version 1 and ready |
| EV-T-099 | Constant-speed cycle | Execute a reproducible level-road profile | Deterministic distance and energy |
| EV-T-100 | Aerodynamic sensitivity | Compare equal cycles at different speeds | Higher speed raises consumption |
| EV-T-101 | Auxiliary sensitivity | Compare equal cycles with different thermal demand | Higher load reduces range |
| EV-T-102 | Road-grade sensitivity | Compare level and uphill segments | Uphill demand raises traction energy |
| EV-T-103 | Regenerative recovery | Include a negative-acceleration segment | Recovered energy is positive and bounded |
| EV-T-104 | Battery reserve | Estimate at or below configured reserve SOC | Limited state and zero available energy |
| EV-T-105 | Insufficient distance | Execute a stationary cycle | Stable limited reason and no division by zero |
| EV-T-106 | Range exact replay | Retry an identical cycle command | Persisted snapshot and duplicate true |
| EV-T-107 | Range changed reuse | Reuse command ID with different input | Stable command conflict |
| EV-T-108 | Triple version conflicts | Submit stale range, battery, or thermal version | Distinct current version returned |
| EV-T-109 | Range atomic evidence | Inspect estimator, step, audit, and outbox | All commit or all roll back |
| EV-T-110 | Range OpenAPI and migration | Inspect routes and revision 0042 | Bounded schema and reversible tables |

## 11. Verification Evidence

| Gate | VI-1 through VI-6 evidence |
|---|---|
| Domain tests | Battery/BMS, propulsion, braking, charging, thermal zones, drive-cycle range, faults, replay, conflicts |
| API contract | Routes and safe numeric limits published in OpenAPI |
| Ruff | Required before merge |
| Strict mypy | Required before merge |
| Full pytest suite | Required before merge |
| Docker integration | Required in GitHub Actions before merge |
| Workbook render and accessibility | Required before delivery |

## 12. Risks and Technical Debt

| Risk | Impact | Treatment |
|---|---|---|
| Simplified linear cell voltage | Insufficient production fidelity | Add chemistry-specific OCV curves and equivalent circuits later |
| Uniform SOC across cells | Cannot yet test imbalance behavior | Add per-cell capacity and balancing in a future increment |
| Fixed thermal constants | Limited pack-design fidelity | Introduce versioned calibration profiles |
| SOH does not age | Cannot test degradation yet | Add cycle/calendar aging after charge and drive behavior stabilizes |
| No current derating | Warning state remains simplistic | Add temperature/SOC-dependent charge and discharge limits |
| Separate Volume II battery projection | Possible divergence | Add an explicit projection/synchronization contract in VI-7 |
| Analytic efficiency surface | Lower fidelity than dyno calibration | Add versioned torque-speed-efficiency maps later |
| Motor step does not debit SOC | Energy domains can diverge across long scenarios | Couple energy flow in VI-7 scenarios |
| Fixed thermal masses and controller gain | Cannot represent every cooling design | Add versioned calibration profiles later |
| Quasi-static braking step | Vehicle speed is not integrated over time | Couple braking to Volume II dynamics in VI-7 |
| Simplified charge acceptance | Cannot represent chemistry-specific power maps | Add versioned SOC-temperature maps later |
| No hydraulic pressure model | Cannot test valve or pressure dynamics yet | Add brake-system actuator fidelity in a later volume |
| Analytic charging curve | Cannot reproduce every chemistry or EVSE calibration | Add versioned SOC-temperature-power maps later |
| No EVSE protocol model | Cannot test ISO 15118 or PLC handshakes yet | Add protocol adapters after core session behavior stabilizes |
| Quasi-static drive-cycle segments | Transient chassis dynamics are simplified | Couple range estimation to Volume II dynamics in VI-7 |
| Fixed air density and calibration | Weather and vehicle variants are approximate | Add versioned environment and vehicle calibration profiles |
| Range cycle does not debit battery SOC | Repeated estimates are analytical rather than stateful trips | Apply energy through cross-domain scenarios in VI-7 |

## 13. Exercises

1. Create an LFP pack at 80% SOC and calculate its nominal energy.

2. Execute a one-hour 10 A discharge and verify the expected SOC delta.

3. Repeat the command identifier and prove that logical time does not advance twice.

4. Reuse the identifier with a different duration and inspect the stable conflict envelope.

5. Start at 59 C, apply a high-current step, and verify protection and zero delivered current.

6. Inspect audit and outbox evidence and confirm that the 96-cell array is absent.

7. Design a chemistry-specific OCV curve without breaking persisted replay evidence.

8. Create the motor/inverter baseline and explain why it begins in standby.

9. Compare eco, normal, and sport peak-torque limits.

10. Calculate mechanical and electrical power for 100 Nm at 3,000 rpm.

11. Open the battery contactors and prove that propulsion torque becomes unavailable.

12. Trigger the motor thermal boundary and inspect the stable limiting reason.

13. Request 1 m/s2 at 20 m/s and verify pure regenerative braking and recovered energy.

14. Increase the request until friction braking is blended with regeneration.

15. Compare regenerative availability at 80% and 95% SOC.

16. Repeat a successful braking command and prove that battery SOC does not increase twice.

17. Start an AC Type 2 session and calculate battery energy after a ten-minute step.

18. Compare DC acceptance at 70% and 90% SOC with the same battery temperature.

19. Pause and resume a session and verify the battery contactor transitions.

20. Inject an EVSE communication fault and prove that no charging current remains.

21. Retry a successful charge command and prove that SOC does not increase twice.

22. Cool a hot battery and motor while heating a cold cabin, then verify the mixed state.

23. Disable thermal management and confirm passive exchange with zero auxiliary power.

24. Inject a coolant-pump fault and verify that every active output becomes zero.

25. Retry a thermal step and prove that component temperatures do not integrate twice.

26. Run equal urban and highway cycles and explain the aerodynamic consumption difference.

27. Increase thermal auxiliary demand and verify that estimated range decreases.

28. Add a downhill deceleration segment and inspect recovered energy.

29. Move battery SOC to the reserve boundary and verify the stable limited result.

30. Retry a range command and prove that the persisted cycle is not integrated twice.

## 14. VI-6 Range and Energy Consumption

VI-6 implements a vehicle-scoped range estimator with bounded physical calibration and reproducible
drive-cycle segments. Each segment supplies duration, speed, longitudinal acceleration, and road
grade. The service calculates rolling, aerodynamic, grade, and acceleration forces; converts
positive mechanical work through drivetrain efficiency; captures bounded regenerative recovery;
and adds baseline plus active thermal auxiliary energy.

Available energy is derived from nominal pack energy, SOH, current SOC, and a configurable reserve.
The response reports distance, duration, traction energy, auxiliary energy, recovered energy, net
energy, consumption per 100 km, and remaining range. Stationary cycles and depleted reserve produce
explicit limited results instead of unstable division or misleading estimates.

The public contract consists of `POST /range`, `GET /range`, and `POST /range/cycles` under the
vehicle electric API. Mutations require electric-vehicle management permission. Every accepted
operation records audit and transactional-outbox evidence. Cycle commands use exact replay,
changed-reuse rejection, and version checks against the estimator, battery, and thermal aggregate.

The model is local and free to run. It requires no commercial map, routing, weather, LLM, or cloud
API. Charging history influences the result through the authoritative battery SOC and SOH rather
than a second derived energy ledger.

## 15. Next Development

VI-7 will add cross-domain EV scenarios that coordinate battery, powertrain, regenerative braking,
charging, thermal management, and range through BMS ECU, CAN, UDS, automated tests, and correlated
evidence.
