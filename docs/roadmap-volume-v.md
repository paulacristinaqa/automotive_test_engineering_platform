# ATEP Volume V - Diagnostics Roadmap

| Increment | Outcome | Status |
|---|---|---|
| V-1 | UDS sessions, DTC persistence, services `0x10`, `0x19`, and `0x14`, RBAC, audit, and outbox | Implemented |
| V-2 | Read Data by Identifier (`0x22`) and Write Data by Identifier (`0x2E`) with a typed DID catalogue | Recommended next |
| V-3 | Routine Control (`0x31`) with deterministic execution evidence | Planned |
| V-4 | Security Access (`0x27`) with bounded seed/key attempts and lockout simulation | Planned |
| V-5 | ECU Reset (`0x11`) integrated with the ECU lifecycle | Planned |
| V-6 | Request Download/Transfer Data/Transfer Exit flash pipeline (`0x34`, `0x36`, `0x37`) | Planned |
| V-7 | OBD-II compatibility, DoIP transport boundary, campaigns, and end-to-end diagnostic scenarios | Planned |

V-1 establishes protocol-independent diagnostic persistence while retaining recognizable UDS
service identities and negative response codes. V-2 should add a typed DID catalogue before any
generic memory access is exposed.
