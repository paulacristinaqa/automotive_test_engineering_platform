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
| EV-F-044 | The platform shall create at most one charging-system state per battery-equipped vehicle. | Migration `0040`; creation tests |
| EV-F-045 | Charging shall support AC Type 2 and DC CCS connector contracts with separate configured limits. | Connector and power tests |
| EV-F-046 | A session shall start with a unique session identifier, connector, target SOC, and requested power. | Session-start test |
| EV-F-047 | Starting or resuming a session shall close battery contactors. | Lifecycle tests |
| EV-F-048 | Pausing, stopping, completion, or a charging fault shall open battery contactors. | Lifecycle and fault tests |
| EV-F-049 | A charge command shall advance battery SOC from deterministic accepted energy. | Energy-transfer test |
| EV-F-050 | A charge command shall not increase SOC beyond the session target. | Target-SOC ceiling test |
| EV-F-051 | Charging power shall respect connector, battery current, BMS, and configured system limits. | Power-limit tests |
| EV-F-052 | Charging power shall taper above 80% SOC toward the target SOC. | Charge-curve test |
| EV-F-053 | Charging shall transfer no energy outside the 0-50 C battery window or in BMS protection. | Safety-limit tests |
| EV-F-054 | The lifecycle shall support idle, charging, paused, completed, and faulted states. | Transition tests |
| EV-F-055 | Invalid charging-state transitions shall return `charging_transition_invalid`. | Negative transition test |
| EV-F-056 | Fault injection shall isolate the battery and preserve a stable fault code until cleared. | Fault lifecycle test |
| EV-F-057 | Charging commands shall validate charging and battery expected versions independently. | Version-conflict tests |
| EV-F-058 | An identical charging command retry shall return its persisted response without applying energy twice. | Replay test |
| EV-F-059 | Reusing a charging command identifier with changed input shall return a stable conflict. | Changed-reuse test |
| EV-F-060 | Charging state, battery state, command evidence, audit, and outbox shall commit atomically. | Atomic-evidence test |
| EV-F-061 | The platform shall create at most one thermal-management state per battery- and motor-equipped vehicle. | Migration `0041`; creation test |
| EV-F-062 | Thermal control shall expose independent targets for battery, motor, inverter, and cabin. | Response and OpenAPI contracts |
| EV-F-063 | Each zone shall use a bounded deterministic heating or cooling request. | Mixed thermal-step test |
| EV-F-064 | Motor and inverter thermal outputs shall share the configured powertrain actuator budget. | Power-budget test |
| EV-F-065 | Temperature evolution shall include logical duration, thermal mass, and ambient exchange. | Active and passive thermal tests |
| EV-F-066 | Cabin evolution shall include a bounded external heat load. | Cabin-load contract and step test |
| EV-F-067 | Disabled thermal management shall draw zero auxiliary power while passive exchange continues. | Disabled-step test |
| EV-F-068 | An injected thermal fault shall disable all actuators and publish a stable fault code. | Fault test |
| EV-F-069 | Auxiliary power shall equal the sum of absolute zone actuator demands. | Energy-demand test |
| EV-F-070 | A thermal step shall update battery, motor, inverter, cabin, and all versions atomically. | Cross-aggregate step test |
| EV-F-071 | Thermal commands shall validate thermal, battery, and motor versions independently. | Version-conflict tests |
| EV-F-072 | An identical thermal command retry shall return stored evidence without applying heat twice. | Exact-replay test |
| EV-F-073 | Reusing a thermal command identifier with changed input shall return a stable conflict. | Changed-reuse test |
| EV-F-074 | Thermal creation and steps shall produce audit and transactional outbox evidence. | Service evidence tests |
| EV-F-075 | Thermal read and mutation operations shall use the Volume VI RBAC permissions. | API dependencies |
| EV-F-076 | Thermal responses shall publish stable standby, heating, cooling, mixed, and faulted states. | State-classification tests |

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
| EV-NF-017 | Cross-aggregate consistency | Charging mutations lock battery and charging rows in a fixed order. |
| EV-NF-018 | Determinism | Charging uses bounded logical durations and an explainable analytic charge curve. |
| EV-NF-019 | Evidence minimization | Events and audit records exclude the battery cell array. |
| EV-NF-020 | Local-first operation | VI-4 requires no paid service, external API, cloud account, or GPU. |
| EV-NF-021 | Cross-aggregate consistency | Thermal mutations lock battery, motor, and thermal rows in a fixed order. |
| EV-NF-022 | Bounded thermal execution | All targets, ambient inputs, heat loads, durations, and actuator outputs have explicit limits. |
| EV-NF-023 | Explainability | Zone power, total auxiliary power, state, fault, temperatures, and versions are published together. |
| EV-NF-024 | Local-first operation | VI-5 requires no paid service, external API, cloud account, or GPU. |

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
| `POST /api/v1/vehicles/{vehicle_id}/electric/charging` | EV-F-044, EV-F-045, EV-F-060 |
| `GET /api/v1/vehicles/{vehicle_id}/electric/charging` | EV-F-045 through EV-F-057 |
| `POST /api/v1/vehicles/{vehicle_id}/electric/charging/commands` | EV-F-046 through EV-F-060 |
| `POST /api/v1/vehicles/{vehicle_id}/electric/thermal` | EV-F-061, EV-F-062, EV-F-074, EV-F-075 |
| `GET /api/v1/vehicles/{vehicle_id}/electric/thermal` | EV-F-062, EV-F-069, EV-F-075, EV-F-076 |
| `POST /api/v1/vehicles/{vehicle_id}/electric/thermal/steps` | EV-F-063 through EV-F-076 |
