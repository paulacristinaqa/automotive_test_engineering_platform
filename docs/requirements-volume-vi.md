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

## API Traceability

| Route | Requirements |
|---|---|
| `POST /api/v1/vehicles/{vehicle_id}/electric/battery` | EV-F-001 through EV-F-004, EV-F-010, EV-F-014 |
| `GET /api/v1/vehicles/{vehicle_id}/electric/battery` | EV-F-004, EV-F-014 |
| `POST /api/v1/vehicles/{vehicle_id}/electric/battery/steps` | EV-F-005 through EV-F-014 |
