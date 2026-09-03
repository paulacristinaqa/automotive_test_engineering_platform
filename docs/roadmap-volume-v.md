# ATEP Volume V - Diagnostics Roadmap

| Increment | Outcome | Status |
|---|---|---|
| V-1 | UDS sessions, DTC persistence, services `0x10`, `0x19`, and `0x14`, RBAC, audit, and outbox | Implemented |
| V-2 | Read Data by Identifier (`0x22`) and Write Data by Identifier (`0x2E`) with a typed DID catalogue | Implemented |
| V-3 | Routine Control (`0x31`) with deterministic execution evidence | Implemented |
| V-4 | Security Access (`0x27`) with bounded seed/key attempts and lockout simulation | Implemented |
| V-5 | ECU Reset (`0x11`) integrated with the ECU lifecycle | Implemented |
| V-6 | Request Download/Transfer Data/Transfer Exit flash pipeline (`0x34`, `0x36`, `0x37`) | Implemented |
| V-7 | OBD-II compatibility, DoIP transport boundary, campaigns, and end-to-end diagnostic scenarios | Implemented |

V-1 establishes protocol-independent diagnostic persistence. V-2 adds a bounded typed DID
catalogue, session-authorized reads/writes, version checks, exact replay, and value-minimized
evidence without exposing generic memory access. V-3 adds a bounded routine catalogue, session-aware
start/stop/result operations, logical-time completion, exact replay, and minimized shared evidence.
V-4 adds deterministic level-1 Security Access, protected seed/key handling, three-attempt lockout,
logical-time expiry/delay, exact positive and negative replay, and minimized shared evidence. V-5
orchestrates the existing ECU reset lifecycle through UDS `0x11`, restores the diagnostic session
and security state, advances logical time, and persists exact cross-volume evidence atomically.
V-6 adds an ECU-scoped, optimistic-versioned transfer lifecycle with a 64-KiB image bound,
256-byte blocks, programming-session and level-1 security policy, byte-counter validation, SHA-256
verification, firmware-version activation, exact replay, and payload-minimized shared evidence.
V-7 completes the Volume V baseline with four typed OBD-II Mode 01 PID projections over the DID
catalogue, Mode 03 stored-DTC compatibility, a validated logical DoIP envelope, and persistent,
atomic, idempotent campaigns that combine OBD-II and UDS reads. Real TCP/UDP DoIP framing,
ISO-TP, production vehicle discovery, and OEM diagnostic policy remain adapter or hardening work.

Volume V is now baselined. The recommended next development is Volume VI - Electric Vehicle,
beginning with the battery pack, cells, SOC/SOH, thermal state, and deterministic BMS behavior.
