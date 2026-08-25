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
| DG-F-009 | Security Access, Read/Write Data by Identifier, Routine Control, ECU reset, and flashing shall be implemented incrementally. | Planned |

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

## Traceability

V-1 evidence is provided by `src/atep/diagnostics`, migration
`0031_diagnostics_foundation`, `tests/test_diagnostics.py`, API contract tests, and the separate
Volume V engineering workbook.
