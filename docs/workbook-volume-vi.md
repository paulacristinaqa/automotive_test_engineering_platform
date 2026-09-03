# ATEP Engineering Workbook - Volume VI: Electric Vehicle

## Document Control

| Field | Value |
|---|---|
| Document | ATEP Engineering Workbook - Volume VI: Electric Vehicle |
| Version | 0.2.0 |
| Baseline date | 3 September 2026 |
| Status | VI-1 battery/BMS and VI-2 motor/inverter implemented |
| Audience | Automotive software, simulation, QA, functional-safety, and platform engineers |

## 1. Purpose and Scope

Volume VI turns the platform's general digital vehicle into a testable electric-energy system.
VI-1 establishes a persistent battery pack and deterministic BMS behavior. VI-2 adds a persistent
motor/inverter aggregate, torque delivery, efficiency, power loss, thermal protection, drive-mode
limits, and battery-derived propulsion availability for repeatable software tests.

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

### Deferred

- chemistry-specific equivalent-circuit and open-circuit-voltage curves;
- cell balancing, aging, sensor faults, and module topology;
- regenerative braking, charging, cooling actuators, and range estimation;
- BMS ECU, CAN, UDS, dashboard, and test-framework end-to-end orchestration.

## 2. Architecture

The FastAPI electric-vehicle boundary coordinates these explicit components:

- RBAC through `electric_vehicle:read` and `electric_vehicle:manage`;
- `BatteryPackState` as the one-per-vehicle electrical, thermal, BMS, contactor, and cell state;
- `BatterySimulationStep` as the command identity and immutable replay evidence;
- `MotorInverterState` as the one-per-vehicle propulsion, efficiency, power, and thermal state;
- `MotorSimulationStep` as the propulsion command identity and immutable replay evidence;
- `AuditRecord` and `OutboxEvent` in the same database transaction as each accepted mutation.

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

- Mode torque ceiling = configured peak torque multiplied by 0.60, 0.85, or 1.00 for eco,
  normal, or sport.
- Mechanical power (kW) = delivered torque multiplied by 2 pi multiplied by rpm / 60 / 1,000.
- Electrical power (kW) = mechanical power divided by deterministic efficiency.
- Conversion loss (kW) = electrical power minus mechanical power.
- Available electrical power is the lower of inverter rating and battery voltage multiplied by
  the BMS-dependent current ceiling.
- Motor and inverter temperatures integrate their share of conversion loss and passive cooling
  over logical time. Protection trips at 150 C motor or 110 C inverter temperature.

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
| `forbidden` | The authenticated user lacks the required permission. |
| `validation_error` | A request violates a declared bound or format. |

## 7. Persistence and Events

Migration `0037_battery_bms_foundation` creates `battery_pack_states` and
`battery_simulation_steps`. Migration `0038_motor_inverter` creates `motor_inverter_states` and
`motor_simulation_steps`. Database checks reinforce the bounded states, versions, and durations.

| Event | Purpose | Privacy/minimization rule |
|---|---|---|
| `atep.electric_vehicle.battery.created.v1` | Announce a configured pack | Pack metadata only; no full cells |
| `atep.electric_vehicle.battery.step.completed.v1` | Announce deterministic state evolution | Pack summary and versions; no full cells |
| `atep.electric_vehicle.motor_inverter.created.v1` | Announce configured propulsion hardware | Bounded configuration only |
| `atep.electric_vehicle.motor.step.completed.v1` | Announce torque and power outcome | Summary, limit reason, and versions |

## 8. Requirements Baseline

VI-1 and VI-2 implement EV-F-001 through EV-F-028 and EV-NF-001 through EV-NF-012. The authoritative
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

## 11. Verification Evidence

| Gate | VI-1 and VI-2 evidence |
|---|---|
| Domain tests | Battery/BMS plus motor torque, power, efficiency, limits, thermal protection, replay, conflicts |
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
| Motor step does not debit SOC | Energy domains can diverge across long scenarios | Couple energy flow in VI-6/VI-7 scenarios |
| Fixed motor thermal constants | Cannot represent every cooling design | Add calibration profiles in VI-5 |

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

## 14. Next Development

VI-3 will add regenerative braking, battery charge-acceptance limits, requested deceleration,
recoverable motor torque, recovered electrical energy, and blended friction-brake allocation. It
will retain logical time, explicit sign conventions, optimistic versions, idempotency, RBAC,
audit, outbox, and bounded evidence.
