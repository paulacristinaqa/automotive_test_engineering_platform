# ATEP Volume VI - Electric Vehicle Requirements

## Functional Requirements

| ID | Requirement | Evidence |
|---|---|---|
| EV-F-001 | The platform shall create at most one battery pack for each registered vehicle. | Migration `0037`; creation and duplicate tests |
| EV-F-002 | A battery pack shall contain between 4 and 192 ordered cell states. | Pydantic and database bounds; contract tests |
| EV-F-003 | The battery model shall support LFP and NMC chemistry identifiers. | `BatteryChemistry`; OpenAPI contract |
| EV-F-004 | The pack shall expose nominal capacity, nominal energy, SOC, SOH, voltage, current, power, temperature, contactors, and operating state. | Battery response contract |
| EV-F-005 | A deterministic step shall update SOC through coulomb counting from current, usable capacity, and logical duration. | Battery service tests |
| EV-F-006 | A deterministic step shall update temperature from resistive heating, passive cooling, ambient temperature, and logical duration. | Thermal-model tests |
| EV-F-007 | Positive current shall represent discharge and negative current shall represent charging. | SOC transition tests |
| EV-F-008 | The BMS shall classify normal, warning, and protection states from bounded SOC and temperature thresholds. | BMS threshold tests |
| EV-F-009 | Protection shall open the contactors and reduce delivered pack current to zero. | Overtemperature protection test |
| EV-F-010 | Battery creation and completed steps shall create audit and transactional outbox evidence in the same transaction. | Service evidence tests |
| EV-F-011 | Repeating an identical command identifier shall return the persisted result without applying the step twice. | Exact-replay test |
| EV-F-012 | Reusing a command identifier with different content shall return a stable conflict. | Changed-reuse test |
| EV-F-013 | A stale expected version shall return the current battery state version. | Optimistic-concurrency test |
| EV-F-014 | Battery read and mutation operations shall require dedicated RBAC permissions. | Permission catalogue and API dependencies |
| EV-F-015 | The platform shall create at most one motor/inverter state for a vehicle that already owns a battery pack. | Migration `0038`; creation tests |
| EV-F-016 | The powertrain shall expose requested and delivered torque, speed, mechanical power, electrical power, efficiency, loss, and temperature. | Powertrain response contract |
| EV-F-017 | Eco, normal, and sport modes shall apply deterministic torque ceilings of 60%, 85%, and 100%. | Drive-mode tests |
| EV-F-018 | Delivered torque shall not exceed the configured motor torque limit. | Torque-limit tests |
| EV-F-019 | Torque shall be zero above the configured motor speed limit. | Overspeed test |
| EV-F-020 | Mechanical power shall be calculated from delivered torque and angular speed. | Power calculation test |
| EV-F-021 | Electrical power shall include deterministic inverter/motor efficiency loss. | Efficiency and loss test |
| EV-F-022 | Available propulsion power shall be constrained by inverter rating and current battery voltage, contactor, and BMS state. | Battery-limit tests |
| EV-F-023 | Open battery contactors or BMS protection shall prevent propulsion torque. | Battery-unavailable test |
| EV-F-024 | Motor or inverter thermal protection shall remove delivered torque and power. | Thermal-protection test |
| EV-F-025 | Motor commands shall use optimistic versioning and exact idempotent replay. | Conflict and replay tests |
| EV-F-026 | Motor creation and completed steps shall produce atomic audit and outbox evidence. | Service evidence tests |
| EV-F-027 | Negative torque shall be rejected until VI-3 defines regenerative braking. | Contract-bound test |
| EV-F-028 | Powertrain read and mutation operations shall use the Volume VI RBAC permissions. | API dependencies |
| EV-F-029 | The platform shall create at most one regenerative-braking state for a vehicle with battery and motor/inverter state. | Migration `0039`; creation tests |
| EV-F-030 | A braking step shall allocate requested deceleration between regenerative and friction braking. | Regenerative and blended tests |
| EV-F-031 | Regenerative force shall be constrained by motor torque, final-drive ratio, drivetrain efficiency, and wheel radius. | Torque-limit test |
| EV-F-032 | Battery charge acceptance shall be constrained by voltage, SOC, temperature, contactors, BMS state, and configured regenerative power. | Charge-acceptance tests |
| EV-F-033 | Regeneration shall be unavailable below 0.5 m/s. | Low-speed fallback test |
| EV-F-034 | Unavailable regeneration shall fall back to friction braking. | Friction fallback tests |
| EV-F-035 | Total delivered deceleration shall not exceed regenerative plus configured friction capacity. | Brake-capacity test |
| EV-F-036 | Recovered electrical power shall include deterministic regeneration efficiency. | Power recovery test |
| EV-F-037 | Recovered energy shall be integrated over logical duration. | Energy recovery test |
| EV-F-038 | Accepted recovered energy shall increase battery SOC and battery version atomically with braking evidence. | Cross-aggregate state test |
| EV-F-039 | Braking commands shall validate both braking and battery expected versions. | Version-conflict tests |
| EV-F-040 | Braking commands shall support exact replay and reject changed command reuse. | Replay and conflict tests |
| EV-F-041 | Braking creation and completed steps shall produce atomic audit and outbox evidence. | Service evidence tests |
| EV-F-042 | Braking responses shall publish stable operating states and limiting reasons. | Strategy and limiting tests |
| EV-F-043 | Braking read and mutation operations shall use the Volume VI RBAC permissions. | API dependencies |

## Non-Functional Requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| EV-NF-001 | Determinism | Equal initial state and command produce equal domain output. |
| EV-NF-002 | Bounded execution | Cell count, current, duration, capacity, voltage, SOC, SOH, and temperatures have explicit limits. |
| EV-NF-003 | No wall-clock coupling | Domain evolution uses `duration_ms` and persisted `simulation_time_ms`. |
| EV-NF-004 | Concurrency safety | Mutations lock the pack and require an exact expected version. |
| EV-NF-005 | Replay safety | Successful results are persisted as snapshots and returned for exact retries. |
| EV-NF-006 | Evidence minimization | Shared audit/events exclude the full per-cell array. |
| EV-NF-007 | Local-first operation | VI-1 requires no paid API, cloud account, or GPU. |
| EV-NF-008 | Traceability | Requirements, implementation, migration, automated tests, and workbook remain linked. |
| EV-NF-009 | Cross-domain consistency | Each motor step reads the locked authoritative battery state before deriving power availability. |
| EV-NF-010 | Explainability | Every derated or protected result publishes a stable limiting reason. |
| EV-NF-011 | Bounded thermal behavior | Motor and inverter temperature inputs and protection thresholds are explicit. |
| EV-NF-012 | Local-first operation | VI-2 uses no paid service, external API, cloud account, or GPU. |
| EV-NF-013 | Cross-aggregate consistency | A braking mutation locks motor, battery, and braking state in a fixed order. |
| EV-NF-014 | Energy conservation evidence | Recovered power, energy, battery SOC, and versions are published together. |
| EV-NF-015 | Explainable degradation | Fallback and capacity outcomes use stable limiting reasons. |
| EV-NF-016 | Local-first operation | VI-3 uses no paid service, external API, cloud account, or GPU. |

## API Traceability

| Route | Requirements |
|---|---|
| `POST /api/v1/vehicles/{vehicle_id}/electric/battery` | EV-F-001 through EV-F-004, EV-F-010, EV-F-014 |
| `GET /api/v1/vehicles/{vehicle_id}/electric/battery` | EV-F-004, EV-F-014 |
| `POST /api/v1/vehicles/{vehicle_id}/electric/battery/steps` | EV-F-005 through EV-F-014 |
| `POST /api/v1/vehicles/{vehicle_id}/electric/powertrain` | EV-F-015, EV-F-016, EV-F-026, EV-F-028 |
| `GET /api/v1/vehicles/{vehicle_id}/electric/powertrain` | EV-F-016, EV-F-022, EV-F-028 |
| `POST /api/v1/vehicles/{vehicle_id}/electric/powertrain/steps` | EV-F-017 through EV-F-028 |
| `POST /api/v1/vehicles/{vehicle_id}/electric/braking` | EV-F-029, EV-F-041, EV-F-043 |
| `GET /api/v1/vehicles/{vehicle_id}/electric/braking` | EV-F-030 through EV-F-038, EV-F-042, EV-F-043 |
| `POST /api/v1/vehicles/{vehicle_id}/electric/braking/steps` | EV-F-030 through EV-F-043 |
