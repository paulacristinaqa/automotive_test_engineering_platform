# ATEP Volume V - Diagnostics Requirements

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| DG-F-001 | The platform shall maintain one current diagnostic session per ECU. | Implemented in V-1 |
| DG-F-002 | The platform shall support UDS default, programming, and extended session types through service `0x10`. | Implemented in V-1 |
| DG-F-003 | Diagnostic mutation commands shall provide exact idempotent replay and stable changed-reuse conflicts. | Implemented in V-1 |
| DG-F-004 | The platform shall persist six-hex-digit DTCs independently from internal ECU fault state. | Implemented in V-1 |
| DG-F-005 | A DTC report shall maintain status mask, severity, occurrence count, logical timestamps, bounded snapshot data, and version. | Implemented in V-1 |
| DG-F-006 | The platform shall expose safely paginated DTC retrieval compatible with the UDS `0x19` service boundary. | Implemented in V-1 |
| DG-F-007 | The platform shall support the all-DTC group `FFFFFF` through service `0x14`. | Implemented in V-1 |
| DG-F-008 | Unsupported diagnostic requests shall expose stable error details including a UDS negative response code. | Implemented in V-1 |
| DG-F-009 | The platform shall maintain an ECU-scoped typed DID catalogue with boolean, integer, decimal, and string values. | Implemented in V-2 |
| DG-F-010 | UDS `0x22` shall read one to sixteen unique DIDs authorized for the active session. | Implemented in V-2 |
| DG-F-011 | UDS `0x2E` shall write only writable DIDs authorized for the active session. | Implemented in V-2 |
| DG-F-012 | DID writes shall validate declared type, numeric bounds, string length, session version, and DID version. | Implemented in V-2 |
| DG-F-013 | DID read and write commands shall provide exact replay and stable changed-reuse conflicts. | Implemented in V-2 |
| DG-F-014 | The platform shall maintain at most 64 typed routine definitions and one versioned execution state per routine and ECU. | Implemented in V-3 |
| DG-F-015 | UDS `0x31` shall support startRoutine, stopRoutine, and requestRoutineResults with active-session authorization. | Implemented in V-3 |
| DG-F-016 | Routine completion shall be deterministic from ECU logical time and return the configured bounded result. | Implemented in V-3 |
| DG-F-017 | Routine control shall reject stale versions and provide exact replay for repeated command identities. | Implemented in V-3 |
| DG-F-018 | UDS `0x27` shall support level-1 requestSeed and sendKey in programming and extended sessions. | Implemented in V-4 |
| DG-F-019 | A seed shall expire after 30,000 ECU logical milliseconds and an accepted key shall unlock diagnostic security level 1. | Implemented in V-4 |
| DG-F-020 | Three invalid keys shall activate a 10,000 logical-millisecond delay and reject access until it expires. | Implemented in V-4 |
| DG-F-021 | Positive and negative Security Access command identities shall replay exactly without repeating state changes or attempt increments. | Implemented in V-4 |
| DG-F-022 | UDS `0x11` shall support hard reset, key-off/on reset, and soft reset through the existing ECU lifecycle. | Implemented in V-5 |
| DG-F-023 | Every accepted diagnostic ECU reset shall restore the default session, security level zero, and an empty Security Access challenge/lockout state. | Implemented in V-5 |
| DG-F-024 | Hard and key-off/on resets shall require security level 1; every reset type shall require a non-default diagnostic session. | Implemented in V-5 |
| DG-F-025 | Diagnostic ECU reset commands shall provide exact replay and stable changed-reuse conflicts. | Implemented in V-5 |
| DG-F-026 | UDS `0x34` shall negotiate one bounded ECU firmware download in programming session with security level 1. | Implemented in V-6 |
| DG-F-027 | UDS `0x36` shall accept ordered blocks no larger than 256 bytes and reject stale versions, wrong sequence counters, and image overflow. | Implemented in V-6 |
| DG-F-028 | UDS `0x37` shall activate a firmware version only after the declared image size and SHA-256 digest match. | Implemented in V-6 |
| DG-F-029 | Flash commands shall provide exact replay and stable changed-reuse conflicts without repeating blocks or activation. | Implemented in V-6 |
| DG-F-030 | OBD-II Mode 01 shall expose supported current-data PIDs through typed ECU DID definitions. | Implemented in V-7 |
| DG-F-031 | OBD-II Mode 03 shall expose the ECU stored-DTC catalogue without duplicating DTC persistence. | Implemented in V-7 |
| DG-F-032 | A diagnostic campaign shall combine one to 32 bounded OBD-II or UDS read steps and persist ordered results. | Implemented in V-7 |
| DG-F-033 | A campaign shall support local execution or a validated DoIP logical-address envelope. | Implemented in V-7 |
| DG-F-034 | Campaign command identities shall provide exact replay and stable changed-reuse conflicts. | Implemented in V-7 |

## Non-Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| DG-NF-001 | Diagnostic logical time shall derive from the ECU simulation clock, never host elapsed time. | Implemented in V-1 |
| DG-NF-002 | State, command evidence, audit, and outbox records shall commit atomically. | Implemented in V-1 |
| DG-NF-003 | Read and mutation operations shall require independent `diagnostics:read` and `diagnostics:manage` permissions. | Implemented in V-1 |
| DG-NF-004 | DTC snapshots shall contain at most 32 scalar values and shall not be copied into audit or outbox payloads. | Implemented in V-1 |
| DG-NF-005 | DTC listing shall be limited to 200 records per request and one million offset. | Implemented in V-1 |
| DG-NF-006 | Public diagnostic contracts shall be represented in OpenAPI and use the platform-wide error envelope. | Implemented in V-1 |
| DG-NF-007 | PostgreSQL schema changes shall be reversible through Alembic. | Implemented in V-1 |
| DG-NF-008 | An ECU shall define at most 128 DIDs; catalogue pages shall return at most 128 entries. | Implemented in V-2 |
| DG-NF-009 | DID values shall remain in command/catalogue storage and responses but shall not be copied into audit or outbox evidence. | Implemented in V-2 |
| DG-NF-010 | DID catalogue changes, reads, and writes shall commit atomically with audit and outbox evidence. | Implemented in V-2 |
| DG-NF-011 | Routine definitions shall contain at most 16 scalar result fields and accept at most 16 scalar start parameters. | Implemented in V-3 |
| DG-NF-012 | Routine execution time shall be bounded from zero through 600,000 logical milliseconds. | Implemented in V-3 |
| DG-NF-013 | Routine input parameters and result values shall not be copied into audit or outbox evidence. | Implemented in V-3 |
| DG-NF-014 | Routine definitions, state transitions, command evidence, audit, and outbox writes shall be atomic. | Implemented in V-3 |
| DG-NF-015 | Raw Security Access keys shall be accepted through a masked secret field and never stored, logged, audited, evented, or returned. | Implemented in V-4 |
| DG-NF-016 | Seeds and key digests shall remain protected command/state evidence and shall never be copied into audit or outbox payloads. | Implemented in V-4 |
| DG-NF-017 | Failed-attempt state, negative command evidence, audit, and outbox records shall commit atomically before the stable error response. | Implemented in V-4 |
| DG-NF-018 | Security Access shall depend only on ECU logical time and local deterministic computation, without timers, GPU, cloud, or paid APIs. | Implemented in V-4 |
| DG-NF-019 | ECU lifecycle mutation, diagnostic state reset, command evidence, audit, and outbox writes shall commit atomically. | Implemented in V-5 |
| DG-NF-020 | ECU Reset shall validate ECU, session, and security optimistic versions and expose UDS-aware stable errors. | Implemented in V-5 |
| DG-NF-021 | Reset duration and post-reset diagnostic time shall derive only from the deterministic ECU simulation clock. | Implemented in V-5 |
| DG-NF-022 | A firmware image shall be limited to 65,536 bytes and each transfer block to 256 bytes. | Implemented in V-6 |
| DG-NF-023 | Raw firmware bytes shall remain in protected transient persistence and shall never enter command requests, logs, audit, or outbox payloads. | Implemented in V-6 |
| DG-NF-024 | Flash state, command evidence, ECU firmware/version mutation, audit, and outbox writes shall commit atomically. | Implemented in V-6 |
| DG-NF-025 | Completed transfers shall purge raw image bytes and retain only size, version, and SHA-256 evidence. | Implemented in V-6 |
| DG-NF-026 | OBD-II PID lists shall contain at most 16 unique supported PIDs and reuse typed DID constraints. | Implemented in V-7 |
| DG-NF-027 | The DoIP boundary shall validate protocol and logical addresses without opening network sockets in the domain layer. | Implemented in V-7 |
| DG-NF-028 | Campaign result persistence, audit, and outbox evidence shall commit atomically. | Implemented in V-7 |
| DG-NF-029 | Shared campaign evidence shall expose step types and counts without copying DID values or DTC snapshots. | Implemented in V-7 |
| DG-NF-030 | The V-7 baseline shall run locally without GPU, cloud services, paid APIs, or vehicle hardware. | Implemented in V-7 |

## Traceability

V-1 through V-7 evidence is provided by `src/atep/diagnostics`, migrations
`0031_diagnostics_foundation`, `0032_diagnostic_data_identifiers`, and
`0033_diagnostic_routines`, `0034_diagnostic_security_access`, `0035_diagnostic_flash`, and
`0036_diagnostic_campaigns`, the
existing Volume III ECU reset lifecycle,
`tests/test_diagnostics.py`, API contract tests, and the separate Volume V engineering workbook.
