# ATEP Volume III — ECU Simulator Roadmap

## Delivery Increments

| Increment | Outcome | Status |
|---|---|---|
| III-1 | Versioned ECU aggregate, lifecycle, bounded memory, faults, RBAC, audit, and outbox | Implemented |
| III-2 | Deterministic ECU execution clock, reset modes, and cyclic task scheduler | Implemented |
| III-3 | ECU-specific behavior profiles for motor, battery, body, gateway, and safety controllers | Planned |
| III-4 | Volatile/non-volatile memory regions, snapshots, reset persistence, and corruption injection | Planned |
| III-5 | Fault activation lifecycle, debouncing, latching, healing, and DTC bridge | Planned |
| III-6 | CAN signal production/consumption contract and gateway routing hooks | Planned |
| III-7 | Multi-ECU scenarios, timing diagnostics, resource metrics, and failure campaigns | Planned |

## Recommended Next Increment

III-3 should add behavior profiles for the motor, battery, body, gateway, and safety controllers.
Profiles should define supported tasks and state interactions without embedding CAN or UDS transport
logic. The deterministic III-2 clock will execute those profile tasks reproducibly.
