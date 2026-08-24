# ATEP Volume III — ECU Simulator Roadmap

## Delivery Increments

| Increment | Outcome | Status |
|---|---|---|
| III-1 | Versioned ECU aggregate, lifecycle, bounded memory, faults, RBAC, audit, and outbox | Implemented |
| III-2 | Deterministic ECU execution clock, reset modes, and cyclic task scheduler | Implemented |
| III-3 | ECU-specific behavior profiles for motor, battery, body, gateway, and safety controllers | Implemented |
| III-4 | Volatile/non-volatile memory regions, snapshots, reset persistence, and corruption injection | Implemented |
| III-5 | Fault activation lifecycle, debouncing, latching, healing, and DTC bridge | Planned |
| III-6 | CAN signal production/consumption contract and gateway routing hooks | Planned |
| III-7 | Multi-ECU scenarios, timing diagnostics, resource metrics, and failure campaigns | Planned |

## Recommended Next Increment

III-5 should add fault activation lifecycle, debouncing, latching, healing, aging evidence, and a
protocol-independent bridge contract for future UDS DTC creation. Fault timing should use the
existing logical clock rather than wall-clock delays.
