# ATEP Volume V - Diagnostics Roadmap

| Increment | Outcome | Status |
|---|---|---|
| V-1 | UDS sessions, DTC persistence, services `0x10`, `0x19`, and `0x14`, RBAC, audit, and outbox | Implemented |
| V-2 | Read Data by Identifier (`0x22`) and Write Data by Identifier (`0x2E`) with a typed DID catalogue | Implemented |
| V-3 | Routine Control (`0x31`) with deterministic execution evidence | Implemented |
| V-4 | Security Access (`0x27`) with bounded seed/key attempts and lockout simulation | Implemented |
| V-5 | ECU Reset (`0x11`) integrated with the ECU lifecycle | Implemented |
| V-6 | Request Download/Transfer Data/Transfer Exit flash pipeline (`0x34`, `0x36`, `0x37`) | Recommended next |
| V-7 | OBD-II compatibility, DoIP transport boundary, campaigns, and end-to-end diagnostic scenarios | Planned |

V-1 establishes protocol-independent diagnostic persistence. V-2 adds a bounded typed DID
catalogue, session-authorized reads/writes, version checks, exact replay, and value-minimized
evidence without exposing generic memory access. V-3 adds a bounded routine catalogue, session-aware
start/stop/result operations, logical-time completion, exact replay, and minimized shared evidence.
V-4 adds deterministic level-1 Security Access, protected seed/key handling, three-attempt lockout,
logical-time expiry/delay, exact positive and negative replay, and minimized shared evidence. V-5
orchestrates the existing ECU reset lifecycle through UDS `0x11`, restores the diagnostic session
and security state, advances logical time, and persists exact cross-volume evidence atomically.
