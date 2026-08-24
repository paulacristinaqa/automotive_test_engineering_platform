# ATEP Volume III — ECU Simulator Roadmap

## Delivery Increments

| Increment | Outcome | Status |
|---|---|---|
| III-1 | Versioned ECU aggregate, lifecycle, bounded memory, faults, RBAC, audit, and outbox | Implemented |
| III-2 | Deterministic ECU execution clock, reset modes, and cyclic task scheduler | Planned |
| III-3 | ECU-specific behavior profiles for motor, battery, body, gateway, and safety controllers | Planned |
| III-4 | Volatile/non-volatile memory regions, snapshots, reset persistence, and corruption injection | Planned |
| III-5 | Fault activation lifecycle, debouncing, latching, healing, and DTC bridge | Planned |
| III-6 | CAN signal production/consumption contract and gateway routing hooks | Planned |
| III-7 | Multi-ECU scenarios, timing diagnostics, resource metrics, and failure campaigns | Planned |

## Recommended Next Increment

III-2 should add a deterministic logical clock and an explicit reset command. It must avoid wall-clock
sleep, persist command identity for replay, and produce reproducible task execution evidence. This is
the minimum timing foundation needed before CAN transmission periods or diagnostic sessions are added.
