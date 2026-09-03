# Diagnostics Architecture

Volume V owns diagnostic protocol semantics. Volume III continues to own ECU execution, memory,
signals, and internal fault lifecycle; Volume V converts selected fault evidence into persisted
Diagnostic Trouble Codes without making the two representations identical.

## V-1 through V-7 Request Flow

Authenticated client -> FastAPI diagnostic route -> diagnostic RBAC -> vehicle and ECU lookup ->
diagnostic domain service -> PostgreSQL state/evidence + audit + transactional outbox -> stable
response or platform error envelope with a UDS negative response code.

## Supported UDS Baseline

- `0x10` Diagnostic Session Control: default, programming, and extended sessions.
- `0x19` Read DTC Information boundary: paginated DTC list/detail and status-mask filtering.
- `0x14` Clear Diagnostic Information: all-DTC group `FFFFFF`.
- `0x22` Read Data by Identifier: one to sixteen typed DIDs per command.
- `0x2E` Write Data by Identifier: session-authorized, versioned DID mutation.
- `0x31` Routine Control: session-authorized start, stop, and result retrieval.
- `0x27` Security Access: deterministic level-1 seed/key exchange with bounded lockout.
- `0x11` ECU Reset: hard, key-off/on, and soft reset through the Volume III ECU lifecycle.
- `0x34`, `0x36`, `0x37` ECU flash: bounded download negotiation, ordered blocks, and digest-verified activation.

Positive response service IDs are calculated as request service ID plus `0x40`. The domain reports
NRC `0x22` for stale versions, `0x31` for invalid values/ranges, and `0x7F` when a DID service is not
supported in the active session. Wire-level PDU framing,
ISO-TP and CAN transport remain adapter responsibilities rather than HTTP API concerns. V-7 adds
the validated logical DoIP boundary, but deliberately leaves TCP/UDP framing and discovery outside
the domain service.

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

V-4 adds one protected Security Access state per ECU. Level-1 requestSeed (`0x01`) is available in
programming and extended sessions and expires after 30,000 ECU logical milliseconds. sendKey
(`0x02`) unlocks diagnostic security level 1. Three invalid keys activate a 10,000 logical-
millisecond delay. Raw keys use a masked input field and are immediately reduced to a digest;
seeds, keys, and key digests are excluded from logs, audit, and outbox. The deliberately simple
deterministic key derivation is a simulator fixture for test engineering, not production ECU
cryptography.

V-5 adds an orchestration boundary rather than a second reset implementation. An accepted UDS
ECU Reset invokes the existing Volume III lifecycle, including boot count, reset duration, memory
policy, logical time, ECU version, audit, and outbox evidence. In the same PostgreSQL transaction it
restores the diagnostic session to default, clears security level and protected challenge/lockout
state, increments their versions, and records UDS `0x11` evidence. Soft reset is allowed in extended
or programming session; hard and key-off/on resets additionally require security level 1. Exact
retry returns the stored result without resetting or incrementing the ECU twice.

V-6 adds one protected firmware-transfer state per ECU. Request Download requires programming
session, security level 1, matching ECU/session/security versions, a 16-bit address range, and an
image no larger than 65,536 bytes. Transfer Data accepts blocks of at most 256 bytes in sequence
and stores only block size and SHA-256 in command/shared evidence. Request Transfer Exit requires
the exact declared byte count and image digest before atomically updating the ECU profile/version.
The completed state purges raw bytes and retains only bounded metadata and the digest. No cloud,
GPU, paid API, or real flashing hardware is required.

V-7 projects four supported OBD-II Mode 01 PIDs through typed DIDs: coolant temperature (`0x05`),
vehicle speed (`0x0D`), control-module voltage (`0x42`), and hybrid-battery remaining life (`0x5B`).
Mode 03 reuses stored DTCs. A DoIP envelope validates protocol version, routing activation type,
and distinct 16-bit source/target logical addresses without creating a socket. Persistent campaigns
run one to 32 ordered OBD Mode 01, OBD Mode 03, or UDS `0x22` read steps. Exact replay returns the
stored result; changed reuse returns the existing stable diagnostic command conflict. Campaign,
audit, and `atep.diagnostics.campaign.completed.v1` outbox evidence share one transaction, while
shared evidence contains only step types/counts rather than diagnostic values or snapshots.

The current POST DTC endpoint is a controlled simulator/test-fixture ingestion boundary. A later
bridge will translate confirmed Volume III fault candidates or received UDS responses into this
same persistence model.
