# ATEP Volume III — ECU Simulator Roadmap

## Delivery Increments

| Increment | Outcome | Status |
|---|---|---|
| III-1 | Versioned ECU aggregate, lifecycle, bounded memory, faults, RBAC, audit, and outbox | Implemented |
| III-2 | Deterministic ECU execution clock, reset modes, and cyclic task scheduler | Implemented |
| III-3 | ECU-specific behavior profiles for motor, battery, body, gateway, and safety controllers | Implemented |
| III-4 | Volatile/non-volatile memory regions, snapshots, reset persistence, and corruption injection | Implemented |
| III-5 | Fault activation lifecycle, debouncing, latching, healing, and DTC bridge | Implemented |
| III-6 | CAN signal production/consumption contract and gateway routing hooks | Implemented |
| III-7 | Multi-ECU scenarios, timing diagnostics, resource metrics, and failure campaigns | Planned |

## Recommended Next Increment

III-7 should add multi-ECU scenarios, logical-time diagnostics, bounded resource metrics, and
repeatable failure campaigns. It should orchestrate the existing vehicle, ECU, fault, memory, and
signal contracts without introducing CAN-bus or UDS transport behavior prematurely.
