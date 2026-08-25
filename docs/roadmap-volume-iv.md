# ATEP Volume IV - CAN Network Roadmap

| Increment | Outcome | Status |
|---|---|---|
| IV-1 | Vehicle-scoped CAN aggregate, ECU topology, classic frame contracts, deterministic submission | Implemented |
| IV-2 | Deterministic arbitration, transmission duration, bus load, and receive delivery | Implemented |
| IV-3 | DBC catalogue, signal encoding/decoding, scaling, offsets, and byte order | Implemented |
| IV-4 | CAN FD payload/timing contracts and mixed-bus compatibility | Implemented |
| IV-5 | Error frames, counters, bus-off/recovery, latency, loss, and fault injection | Implemented |
| IV-6 | LIN and automotive Ethernet adapters plus gateway routing | Implemented |
| IV-7 | Multi-bus campaigns, traces, performance evidence, and integration scenarios | Planned |

IV-6 adds bounded LIN and automotive Ethernet contracts, transparent cross-protocol routes through
declared gateway ECUs, deterministic destination timing, replay-safe evidence, and payload-free
observability. The recommended next increment is IV-7: multi-bus campaigns, traces, performance
evidence, and integrated failure scenarios.
