# ATEP Volume V - Diagnostics Roadmap

| Increment | Outcome | Status |
|---|---|---|
| V-1 | UDS sessions, DTC persistence, services `0x10`, `0x19`, and `0x14`, RBAC, audit, and outbox | Implemented |
| V-2 | Read Data by Identifier (`0x22`) and Write Data by Identifier (`0x2E`) with a typed DID catalogue | Implemented |
| V-3 | Routine Control (`0x31`) with deterministic execution evidence | Recommended next |
| V-4 | Security Access (`0x27`) with bounded seed/key attempts and lockout simulation | Planned |
| V-5 | ECU Reset (`0x11`) integrated with the ECU lifecycle | Planned |
| V-6 | Request Download/Transfer Data/Transfer Exit flash pipeline (`0x34`, `0x36`, `0x37`) | Planned |
| V-7 | OBD-II compatibility, DoIP transport boundary, campaigns, and end-to-end diagnostic scenarios | Planned |

V-1 establishes protocol-independent diagnostic persistence. V-2 adds a bounded typed DID
catalogue, session-authorized reads/writes, version checks, exact replay, and value-minimized
evidence without exposing generic memory access. V-3 should add deterministic Routine Control.
