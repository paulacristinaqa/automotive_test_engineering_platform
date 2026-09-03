# ATEP Engineering Workbook - Volume VI: Electric Vehicle

## Document Control

| Field | Value |
|---|---|
| Document | ATEP Engineering Workbook - Volume VI: Electric Vehicle |
| Version | 0.1.0 |
| Baseline date | 3 September 2026 |
| Status | VI-1 battery and BMS foundation implemented |
| Audience | Automotive software, simulation, QA, functional-safety, and platform engineers |

## 1. Purpose and Scope

Volume VI turns the platform's general digital vehicle into a testable electric-energy system.
The first increment establishes a persistent battery pack and deterministic BMS behavior suitable
for repeatable software tests. It provides the foundation for motor torque, charging, thermal
control, regenerative braking, range estimation, and full cross-domain EV scenarios.

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

### Deferred

- chemistry-specific equivalent-circuit and open-circuit-voltage curves;
- cell balancing, aging, sensor faults, and module topology;
- inverter, motor, regen, charging, cooling actuators, and range estimation;
- BMS ECU, CAN, UDS, dashboard, and test-framework end-to-end orchestration.

## 2. Architecture

The FastAPI electric-vehicle boundary coordinates these explicit components:

- RBAC through `electric_vehicle:read` and `electric_vehicle:manage`;
- `BatteryPackState` as the one-per-vehicle electrical, thermal, BMS, contactor, and cell state;
- `BatterySimulationStep` as the command identity and immutable replay evidence;
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

### Stable Errors

| Code | Meaning |
|---|---|
| `battery_pack_already_exists` | The vehicle already owns a battery pack. |
| `battery_pack_not_found` | No battery pack exists for the vehicle. |
| `battery_state_version_conflict` | `expected_version` is stale. |
| `battery_simulation_command_conflict` | A command ID was reused with different content. |
| `forbidden` | The authenticated user lacks the required permission. |
| `validation_error` | A request violates a declared bound or format. |

## 7. Persistence and Events

Migration `0037_battery_bms_foundation` creates `battery_pack_states` and
`battery_simulation_steps`. Database checks reinforce API limits for cell count, capacity, SOC,
SOH, versions, duration, BMS state, and contactor state.

| Event | Purpose | Privacy/minimization rule |
|---|---|---|
| `atep.electric_vehicle.battery.created.v1` | Announce a configured pack | Pack metadata only; no full cells |
| `atep.electric_vehicle.battery.step.completed.v1` | Announce deterministic state evolution | Pack summary and versions; no full cells |

## 8. Requirements Baseline

VI-1 implements EV-F-001 through EV-F-014 and EV-NF-001 through EV-NF-008. The authoritative
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

## 11. Verification Evidence

| Gate | VI-1 evidence |
|---|---|
| Domain tests | Contract, creation, deterministic discharge, thermal protection, replay, conflicts |
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

## 13. Exercises

1. Create an LFP pack at 80% SOC and calculate its nominal energy.

2. Execute a one-hour 10 A discharge and verify the expected SOC delta.

3. Repeat the command identifier and prove that logical time does not advance twice.

4. Reuse the identifier with a different duration and inspect the stable conflict envelope.

5. Start at 59 C, apply a high-current step, and verify protection and zero delivered current.

6. Inspect audit and outbox evidence and confirm that the 96-cell array is absent.

7. Design a chemistry-specific OCV curve without breaking persisted replay evidence.

## 14. Next Development

VI-2 will add motor and inverter state, requested and delivered torque, efficiency, electrical power,
thermal loss, speed limits, and battery-derived charge/discharge power constraints. It should reuse
the same logical-time, optimistic-version, idempotency, RBAC, audit, outbox, and evidence patterns.
