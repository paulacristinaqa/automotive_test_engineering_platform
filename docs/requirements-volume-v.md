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
| DG-F-022 | ECU reset and flashing shall be implemented incrementally. | Planned |

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

## Traceability

V-1 through V-4 evidence is provided by `src/atep/diagnostics`, migrations
`0031_diagnostics_foundation`, `0032_diagnostic_data_identifiers`, and
`0033_diagnostic_routines`, `0034_diagnostic_security_access`,
`tests/test_diagnostics.py`, API contract tests, and the separate Volume V engineering workbook.
