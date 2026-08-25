# Diagnostics Architecture

Volume V owns diagnostic protocol semantics. Volume III continues to own ECU execution, memory,
signals, and internal fault lifecycle; Volume V converts selected fault evidence into persisted
Diagnostic Trouble Codes without making the two representations identical.

## V-1/V-2/V-3 Request Flow

Authenticated client -> FastAPI diagnostic route -> diagnostic RBAC -> vehicle and ECU lookup ->
UDS domain service -> PostgreSQL diagnostic state/evidence + audit + transactional outbox -> stable
response or platform error envelope with a UDS negative response code.

## Supported UDS Baseline

- `0x10` Diagnostic Session Control: default, programming, and extended sessions.
- `0x19` Read DTC Information boundary: paginated DTC list/detail and status-mask filtering.
- `0x14` Clear Diagnostic Information: all-DTC group `FFFFFF`.
- `0x22` Read Data by Identifier: one to sixteen typed DIDs per command.
- `0x2E` Write Data by Identifier: session-authorized, versioned DID mutation.
- `0x31` Routine Control: session-authorized start, stop, and result retrieval.

Positive response service IDs are calculated as request service ID plus `0x40`. The domain reports
NRC `0x22` for stale versions, `0x31` for invalid values/ranges, and `0x7F` when a DID service is not
supported in the active session. Wire-level PDU framing,
ISO-TP, CAN transport, and DoIP remain adapter responsibilities rather than HTTP API concerns.

## Consistency and Evidence

Each ECU has one versioned current diagnostic session. Mutating UDS commands use ECU-scoped command
IDs. Exact retry returns persisted evidence; a changed reuse returns
`diagnostic_command_conflict`. DTC clocks use the ECU logical simulation time. Snapshots are stored
as bounded diagnostic evidence but excluded from audit and outbox payloads.

V-2 adds an ECU-scoped catalogue capped at 128 DIDs. Boolean, integer, decimal, and string values
have explicit constraints. Reads and writes persist exact command results for idempotent replay,
while audit and outbox evidence contains only identifiers, counts, service IDs, and versions—never
the DID values themselves.

V-3 adds an ECU-scoped catalogue capped at 64 routines. Each routine declares its allowed
sessions, bounded logical execution duration, stop capability, and a bounded scalar result
template. Start, stop, and result requests check session and routine versions. Running routines
complete only when ECU logical time reaches their completion timestamp, so tests never sleep.
Protected command evidence preserves parameters and results for exact replay, while audit and
outbox records expose only identifiers, statuses, service/subfunction identities, counters, and
versions.

The current POST DTC endpoint is a controlled simulator/test-fixture ingestion boundary. A later
bridge will translate confirmed Volume III fault candidates or received UDS responses into this
same persistence model.
