# ATEP Volume V - Diagnostics Engineering Workbook

**Document status:** Increment V-1 implemented  
**Language:** English  
**Last updated:** 2026-08-25  
**Repository:** `paulacristinaqa/automotive_test_engineering_platform`

## 1. Document Purpose

This workbook records the architecture, requirements, engineering decisions, implementation
evidence, verification strategy, risks, and study exercises for the Diagnostics volume.

## 2. Document Control

| Field | Value |
|---|---|
| Volume | V - Diagnostics |
| Baseline | Increment V-1 |
| Architecture style | ECU-scoped diagnostic aggregate and transactional domain service |
| Primary runtime | Python 3.12, FastAPI, SQLAlchemy, PostgreSQL |
| Quality gates | pytest, Ruff, strict mypy, Alembic, integration CI, DOCX render and accessibility audit |

## 3. Revision History

| Release | Date | Change |
|---|---|---|
| 0.1.0 | 2026-08-25 | Added versioned UDS sessions, DTC storage, services `0x10`, `0x19`, and `0x14`, stable NRC evidence, RBAC, audit, outbox, migration, APIs, and deterministic tests. |

## 4. Scope and Boundaries

### 4.1 Included

- One current diagnostic session per ECU.
- Default, programming, and extended session types.
- Explicit UDS request and positive-response service identities.
- Stable negative response codes within the global ATEP error contract.
- Six-hex-digit DTC storage, status masks, severity, occurrence tracking, and logical timestamps.
- Bounded snapshot evidence and safe DTC pagination/filtering.
- Exact command replay and stable changed-reuse conflict behavior.
- Independent diagnostic read/manage permissions.
- Atomic state, evidence, audit, and transactional outbox writes.

### 4.2 Deferred

- ISO-TP segmentation, CAN transport binding, DoIP, and physical adapters.
- DID catalogue and services `0x22` and `0x2E`.
- Routine Control, Security Access, ECU Reset, and flash transfer services.
- OBD-II mode/PID compatibility and fleet-scale remote diagnostics.

## 5. Architecture

The `atep.diagnostics` module sits above the ECU aggregate and below future CAN/DoIP transport
adapters. It stores diagnostic protocol state without taking ownership of ECU memory, signals, or
fault generation. This preserves a clean distinction between a simulated internal fault and a DTC
that an external tester can query.

Request flow: authenticated client -> FastAPI router -> diagnostic RBAC -> vehicle/ECU lookup ->
diagnostic service -> PostgreSQL state and evidence + audit + transactional outbox -> typed response.

## 6. Domain Model

`DiagnosticSessionState` stores ECU ownership, current session, security level, optimistic version,
and ECU logical time. Security level is zero in V-1 and is reserved for V-4.

`DiagnosticCommand` stores ECU-scoped command identity, UDS service ID, canonical request, result,
session versions, actor, and timestamps. It supports exact replay for mutating services.

`DiagnosticTroubleCode` stores ECU ownership, six-digit hexadecimal code, ISO-style status mask,
severity, description, occurrence count, first/last ECU logical time, bounded snapshot, and version.

## 7. Public API and Security

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/session` | `diagnostics:read` | Retrieve or initialize the default session. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/session-control` | `diagnostics:manage` | Execute UDS service `0x10`. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/dtcs` | `diagnostics:manage` | Report or update a simulated DTC. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/dtcs` | `diagnostics:read` | Execute the `0x19` query boundary with safe pagination. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/dtcs/{code}` | `diagnostics:read` | Retrieve one DTC. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/dtcs/clear` | `diagnostics:manage` | Execute `0x14` for group `FFFFFF`. |

## 8. UDS Semantics

### 8.1 Diagnostic Session Control (`0x10`)

The service locks or initializes the ECU session state, verifies expected version, applies the new
session, resets security level, copies ECU logical time, increments version, and persists command
evidence. The positive response service ID is `0x50`.

### 8.2 Read DTC Information (`0x19`)

The HTTP query is a transport-neutral representation of the read-DTC boundary. It orders by code,
limits each page to 200 records, supports a non-zero status-mask intersection filter, and emits
typed DTC records. A future wire adapter will encode the appropriate UDS subfunction and PDU.

### 8.3 Clear Diagnostic Information (`0x14`)

V-1 supports only the all-DTC group `FFFFFF`. The service removes matching ECU DTC records within
the same transaction as versioned command, audit, and outbox evidence. The positive response
service ID is `0x54`; unsupported groups return NRC `0x31`.

## 9. Error and Consistency Contract

| Condition | Stable code | HTTP | UDS evidence |
|---|---|---|---|
| Changed reuse of a diagnostic command ID | `diagnostic_command_conflict` | 409 | Command identity conflict before PDU execution |
| Stale session version | `diagnostic_contract_invalid` | 422 | NRC `0x22` conditions not correct |
| Unsupported DTC group | `diagnostic_contract_invalid` | 422 | NRC `0x31` request out of range |
| Unknown ECU or DTC | Platform resource-not-found code | 404 | Adapter maps transport response later |
| Invalid body or pagination | `request_validation_error` | 422 | Rejected at the public contract boundary |

## 10. Engineering Decisions

### ADR-DG-001 - Separate ECU Faults from Diagnostic Trouble Codes

Internal ECU faults drive simulated behavior. DTCs are externally observable diagnostic evidence.
The platform may bridge them, but neither representation silently overwrites the other.

### ADR-DG-002 - Preserve UDS Identity Without Premature Wire Coupling

Services, positive response IDs, and NRCs are explicit, while HTTP carries typed domain commands.
ISO-TP and DoIP adapters can be added without rewriting persistence or business rules.

### ADR-DG-003 - Use ECU Logical Time

DTC first/last-seen time and session transitions use simulation time. Tests remain deterministic
and do not sleep or depend on host clock speed.

### ADR-DG-004 - Minimize Observable Evidence

Snapshots may contain engineering measurements. They remain in protected DTC storage and are not
copied into audit or outbox messages; those contain identifiers, status, counters, and versions.

## 11. Verification Catalogue

| Test | Objective | Level |
|---|---|---|
| DTC code shape | Reject anything other than six uppercase hexadecimal digits. | Schema |
| Status-mask bounds | Accept only values from zero through 255. | Schema |
| Snapshot bound | Reject more than 32 scalar snapshot entries. | Schema |
| Session types | Accept only default, programming, and extended. | Schema/OpenAPI |
| Initial session | Create one default session for an ECU without diagnostic state. | Service/integration |
| Session version | Reject a stale expected version with NRC `0x22`. | Service/API |
| Session response | Expose request `0x10` and positive response `0x50`. | Service/API |
| Exact replay | Return persisted command evidence without a second state change. | Service/integration |
| Changed reuse | Return stable `diagnostic_command_conflict`. | Service/API |
| DTC creation | Persist code, status, severity, description, snapshot, and logical time. | Service/integration |
| DTC recurrence | Increment occurrence count and version while preserving first-seen time. | Service |
| DTC ordering | Return DTCs in deterministic code order. | Service/API |
| Status filtering | Return records whose status mask intersects the requested mask. | Service/integration |
| Safe pagination | Enforce limit 200 and offset one million. | OpenAPI/API |
| DTC detail | Return stable not-found behavior for an unknown code. | API |
| Clear all | Remove all ECU DTCs for group `FFFFFF`. | Service/integration |
| Unsupported group | Return NRC `0x31` without deleting DTCs. | Service/API |
| Atomic evidence | Commit state, command, DTC mutation, audit, and outbox together. | Integration |
| Evidence minimization | Exclude snapshot measurements from audit and outbox payloads. | Service |
| RBAC read denial | Return 403 without `diagnostics:read`. | API/integration |
| RBAC write denial | Return 403 without `diagnostics:manage`. | API/integration |
| OpenAPI contract | Publish typed commands, results, bounds, and paths. | Contract |
| Migration lifecycle | Upgrade and downgrade all three diagnostic tables. | Integration |
| Regression | Preserve ECU, CAN, identity, audit, and platform behavior. | Full suite |

## 12. Implemented Evidence

- `src/atep/diagnostics/` contains models, schemas, service, and router.
- Migration `0031_diagnostics_foundation` owns session, command, and DTC persistence.
- Events are `atep.diagnostics.session.changed.v1`, `atep.diagnostics.dtc.reported.v1`, and `atep.diagnostics.dtc.cleared.v1`.
- Permissions are `diagnostics:read` and `diagnostics:manage`.
- `tests/test_diagnostics.py` verifies contracts, logical time, versioning, replay, conflicts, evidence minimization, and permissions.
- API contract tests verify routes and safe pagination in generated OpenAPI.

## 13. Risks and Technical Debt

- V-1 exposes semantic UDS operations but does not yet encode wire PDUs.
- Status-mask meaning is retained as a byte; named bit helpers should be added with richer DTC queries.
- DTC creation is a controlled simulator boundary; automatic fault-to-DTC mapping is future work.
- The current clear operation loads at most 200 DTCs, matching the per-ECU V-1 storage bound.
- Security level is reserved but remains zero until Security Access is implemented.

## 14. Roadmap

V-1 is implemented. The recommended next development is V-2: a typed Data Identifier catalogue
with Read Data by Identifier (`0x22`) and session-authorized Write Data by Identifier (`0x2E`).

## 15. Study Exercises

1. Explain why an ECU fault and a DTC are related but not identical.
2. Calculate positive response service IDs for `0x10`, `0x14`, and `0x19`.
3. Compare NRC `0x22` and NRC `0x31` in the implemented operations.
4. Trace a session-control request through RBAC, locking, versioning, audit, and outbox.
5. Explain why exact command replay must not increment the session twice.
6. Design a test for changed command-ID reuse.
7. Decode status mask `0x09` into the UDS status-bit concepts you would expose next.
8. Explain why DTC snapshot values are excluded from audit events.
9. Design an automatic mapping from a confirmed BMS fault candidate to DTC `0A80FF`.
10. Propose a DID catalogue for battery SOC, SOH, temperature, and pack voltage.
11. Define which DIDs may be written only in extended or programming session.
12. Describe where ISO-TP segmentation belongs relative to the diagnostic service.
13. Compare CAN/ISO-TP and Ethernet/DoIP as transport adapters for the same UDS domain.
14. Design a negative test that proves an unsupported DTC group deletes nothing.
15. Explain why simulation time produces more reproducible diagnostic tests than host time.
