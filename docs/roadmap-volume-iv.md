# ATEP Volume IV - CAN Network Roadmap

| Increment | Outcome | Status |
|---|---|---|
| IV-1 | Vehicle-scoped CAN aggregate, ECU topology, classic frame contracts, deterministic submission | Implemented |
| IV-2 | Deterministic arbitration, transmission duration, bus load, and receive delivery | Implemented |
| IV-3 | DBC catalogue, signal encoding/decoding, scaling, offsets, and byte order | Implemented |
| IV-4 | CAN FD payload/timing contracts and mixed-bus compatibility | Implemented |
| IV-5 | Error frames, counters, bus-off/recovery, latency, loss, and fault injection | Implemented |
| IV-6 | LIN and automotive Ethernet adapters plus gateway routing | Implemented |
| IV-7 | Multi-bus campaigns, traces, performance evidence, and integration scenarios | Implemented |

IV-7 completes the Volume IV baseline with bounded atomic campaigns, ordered payload-free traces,
deterministic utilization and latency evidence, explicit frame-loss and gateway-unavailable
scenarios, replay-safe persistence, and protected history APIs. The recommended next volume is
Volume V - Diagnostics, beginning with diagnostic sessions, DTC storage, and UDS service contracts.
