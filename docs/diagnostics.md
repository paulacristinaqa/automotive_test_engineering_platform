# Diagnostics Architecture

Volume V owns diagnostic protocol semantics. Volume III continues to own ECU execution, memory,
signals, and internal fault lifecycle; Volume V converts selected fault evidence into persisted
Diagnostic Trouble Codes without making the two representations identical.

## V-1 Request Flow

Authenticated client -> FastAPI diagnostic route -> diagnostic RBAC -> vehicle and ECU lookup ->
UDS domain service -> PostgreSQL diagnostic state/evidence + audit + transactional outbox -> stable
response or platform error envelope with a UDS negative response code.

## Supported UDS Baseline

- `0x10` Diagnostic Session Control: default, programming, and extended sessions.
- `0x19` Read DTC Information boundary: paginated DTC list/detail and status-mask filtering.
- `0x14` Clear Diagnostic Information: all-DTC group `FFFFFF`.

Positive response service IDs are calculated as request service ID plus `0x40`. V-1 reports NRC
`0x22` for session-version conditions and `0x31` for unsupported DTC groups. Wire-level PDU framing,
ISO-TP, CAN transport, and DoIP remain adapter responsibilities rather than HTTP API concerns.

## Consistency and Evidence

Each ECU has one versioned current diagnostic session. Mutating UDS commands use ECU-scoped command
IDs. Exact retry returns persisted evidence; a changed reuse returns
`diagnostic_command_conflict`. DTC clocks use the ECU logical simulation time. Snapshots are stored
as bounded diagnostic evidence but excluded from audit and outbox payloads.

The current POST DTC endpoint is a controlled simulator/test-fixture ingestion boundary. A later
bridge will translate confirmed Volume III fault candidates or received UDS responses into this
same persistence model.
