# ATEP Volume IV - CAN Network Roadmap

| Increment | Outcome | Status |
|---|---|---|
| IV-1 | Vehicle-scoped CAN aggregate, ECU topology, classic frame contracts, deterministic submission | Implemented |
| IV-2 | Deterministic arbitration, transmission duration, bus load, and receive delivery | Implemented |
| IV-3 | DBC catalogue, signal encoding/decoding, scaling, offsets, and byte order | Implemented |
| IV-4 | CAN FD payload/timing contracts and mixed-bus compatibility | Implemented |
| IV-5 | Error frames, counters, bus-off/recovery, latency, loss, and fault injection | Implemented |
| IV-6 | LIN and automotive Ethernet adapters plus gateway routing | Planned |
| IV-7 | Multi-bus campaigns, traces, performance evidence, and integration scenarios | Planned |

IV-5 adds deterministic TEC/REC error confinement, error-active/error-passive/bus-off states,
contract-scoped transmission/reception faults, frame loss, replay-safe evidence, and explicit
ISO-style bus-off recovery after at least 128 sequences of 11 recessive bits. The recommended next
increment is IV-6: LIN and automotive Ethernet adapters with gateway routing.
