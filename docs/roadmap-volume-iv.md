# ATEP Volume IV - CAN Network Roadmap

| Increment | Outcome | Status |
|---|---|---|
| IV-1 | Vehicle-scoped CAN aggregate, ECU topology, classic frame contracts, deterministic submission | Implemented |
| IV-2 | Deterministic arbitration, transmission duration, bus load, and receive delivery | Implemented |
| IV-3 | DBC catalogue, signal encoding/decoding, scaling, offsets, and byte order | Implemented |
| IV-4 | CAN FD payload/timing contracts and mixed-bus compatibility | Planned |
| IV-5 | Error frames, counters, bus-off/recovery, latency, loss, and fault injection | Planned |
| IV-6 | LIN and automotive Ethernet adapters plus gateway routing | Planned |
| IV-7 | Multi-bus campaigns, traces, performance evidence, and integration scenarios | Planned |

IV-3 establishes a structured DBC-compatible signal layer with exact decimal conversion and explicit
Intel/Motorola bit semantics. Textual `.dbc` file parsing and multiplexing remain future extensions.
The recommended next increment is IV-4.
