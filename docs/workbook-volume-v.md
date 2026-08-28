# ATEP Volume V - Diagnostics Engineering Workbook

**Document status:** Increments V-1 through V-4 implemented
**Language:** English  
**Last updated:** 2026-08-28
**Repository:** `paulacristinaqa/automotive_test_engineering_platform`

## 1. Document Purpose

This workbook records the architecture, requirements, engineering decisions, implementation
evidence, verification strategy, risks, and study exercises for the Diagnostics volume.

## 2. Document Control

| Field | Value |
|---|---|
| Volume | V - Diagnostics |
| Baseline | Increments V-1 through V-4 |
| Architecture style | ECU-scoped diagnostic aggregate and transactional domain service |
| Primary runtime | Python 3.12, FastAPI, SQLAlchemy, PostgreSQL |
| Quality gates | pytest, Ruff, strict mypy, Alembic, integration CI, DOCX render and accessibility audit |

## 3. Revision History

| Release | Date | Change |
|---|---|---|
| 0.1.0 | 2026-08-25 | Added versioned UDS sessions, DTC storage, services `0x10`, `0x19`, and `0x14`, stable NRC evidence, RBAC, audit, outbox, migration, APIs, and deterministic tests. |
| 0.2.0 | 2026-08-25 | Added a typed DID catalogue, UDS `0x22`/`0x2E`, session authorization, value/version constraints, minimized evidence, migration, APIs, and tests. |
| 0.3.0 | 2026-08-25 | Added a bounded routine catalogue, UDS Routine Control `0x31`, deterministic logical-time execution, start/stop/result subfunctions, versioned replay, minimized evidence, migration, APIs, and tests. |
| 0.4.0 | 2026-08-28 | Added UDS Security Access `0x27`, deterministic level-1 seed/key exchange, logical-time expiry and lockout, idempotent negative evidence, secret minimization, migration, APIs, and tests. |

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
- ECU-scoped typed DID catalogue with boolean, integer, decimal, and string values.
- Session-authorized UDS Read/Write Data by Identifier (`0x22` and `0x2E`).
- DID type, range, length, catalogue-size, request-size, and optimistic-version bounds.
- ECU-scoped routine definitions and independent versioned execution state.
- UDS Routine Control (`0x31`) start, stop, and request-results subfunctions.
- Active-session authorization and deterministic completion from ECU logical time.
- Bounded parameters, results, duration, catalogue size, and optimistic versions.
- Level-1 requestSeed/sendKey Security Access in programming and extended sessions.
- Three-attempt lockout, seed expiry, and required delay based on ECU logical time.
- Masked raw-key input, digest-only protected state, and seed/key-minimized shared evidence.
- Exact replay for accepted and denied Security Access commands.

### 4.2 Deferred

- ISO-TP segmentation, CAN transport binding, DoIP, and physical adapters.
- ECU Reset and flash transfer services.
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
and ECU logical time. It started at zero in V-1; V-4 can raise it to level 1 after a
successful Security Access exchange, while every session change resets it to zero.

`DiagnosticCommand` stores ECU-scoped command identity, UDS service ID, canonical request, result,
session versions, actor, and timestamps. It supports exact replay for mutating services.

`DiagnosticTroubleCode` stores ECU ownership, six-digit hexadecimal code, ISO-style status mask,
severity, description, occurrence count, first/last ECU logical time, bounded snapshot, and version.

`DiagnosticDataIdentifier` stores an ECU-local 16-bit identifier, engineering metadata, declared
type, unit, readable/writable sessions, constrained scalar value, and optimistic version. The
catalogue is capped at 128 entries per ECU; this is a semantic data surface, not raw memory access.

`DiagnosticRoutine` stores an ECU-local 16-bit identifier, engineering metadata, allowed sessions,
bounded execution duration, stop capability, bounded scalar result template, and definition
version. `DiagnosticRoutineState` independently stores idle/running/completed/stopped status,
invocation count, logical timestamps, protected input/result values, and an optimistic version.
The catalogue is capped at 64 routines per ECU.

`DiagnosticSecurityState` stores one ECU-local challenge counter, expected-key digest, seed expiry,
invalid-attempt count, logical lockout deadline, target level, and optimistic version. It never
stores a raw key. The current unlocked security level remains on `DiagnosticSessionState`, so a
session change can reset authorization without rewriting challenge history.

## 7. Public API and Security

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/session` | `diagnostics:read` | Retrieve or initialize the default session. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/session-control` | `diagnostics:manage` | Execute UDS service `0x10`. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/dtcs` | `diagnostics:manage` | Report or update a simulated DTC. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/dtcs` | `diagnostics:read` | Execute the `0x19` query boundary with safe pagination. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/dtcs/{code}` | `diagnostics:read` | Retrieve one DTC. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/dtcs/clear` | `diagnostics:manage` | Execute `0x14` for group `FFFFFF`. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/dids` | `diagnostics:manage` | Define one typed DID. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/dids` | `diagnostics:read` | List the bounded ECU DID catalogue. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/dids/{identifier}` | `diagnostics:read` | Retrieve one DID definition and value. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/dids/read` | `diagnostics:read` | Execute UDS `0x22` for up to 16 DIDs. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/dids/{identifier}/write` | `diagnostics:manage` | Execute session-authorized UDS `0x2E`. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/routines` | `diagnostics:manage` | Define one bounded routine. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/routines` | `diagnostics:read` | List the bounded routine catalogue. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/routines/{identifier}` | `diagnostics:read` | Retrieve one routine and its state. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/routines/{identifier}/control` | `diagnostics:manage` | Execute UDS `0x31` start, stop, or result request. |
| GET | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/security-access/state` | `diagnostics:read` | Retrieve non-secret version, attempt, lockout, and challenge status. |
| POST | `/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics/security-access` | `diagnostics:manage` | Execute UDS `0x27` requestSeed or sendKey. |

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

### 8.4 Read Data by Identifier (`0x22`)

One command reads one to sixteen unique 16-bit identifiers. Every DID must exist and authorize the
active diagnostic session. The result preserves typed values for the client and exact replay; the
positive response identity is `0x62`. Audit and outbox records contain identifiers and versions,
not values.

### 8.5 Write Data by Identifier (`0x2E`)

A write requires `diagnostics:manage`, a writable DID, an allowed active session, matching session
and DID versions, and a value satisfying the declared type and constraints. It increments only the
DID version and returns `0x6E` identity. Exact retry returns the persisted result without a second
mutation.

### 8.6 Routine Control (`0x31`)

Subfunctions `0x01`, `0x02`, and `0x03` represent startRoutine, stopRoutine, and
requestRoutineResults. Every request requires an allowed active session plus matching session and
routine-state versions. Start records the ECU logical start/completion timestamps and bounded
parameters. Stop is accepted only for a running routine that declares stop support. A result
request deterministically promotes a running routine to completed when ECU logical time reaches
the target and returns the protected result template. Exact retries replay persisted command
evidence without another transition; the positive response identity is `0x71`.

### 8.7 Security Access (`0x27`)

V-4 supports level-1 requestSeed (`0x01`) and sendKey (`0x02`) in programming and extended
sessions. A seed is deterministically generated from ECU identity, challenge counter, logical
time, and state version; it expires after 30,000 logical milliseconds. The raw key is accepted as
a masked 16-character secret and immediately reduced to SHA-256 for constant-time comparison.
Three invalid keys produce NRC `0x36` and a 10,000 logical-millisecond delay; attempts during that
delay return NRC `0x37`. sendKey without a current challenge returns NRC `0x24`, and an ordinary
invalid key returns NRC `0x35`. Successful access raises the session security level to 1 and uses
positive response identity `0x67`. The key derivation helper is intentionally a transparent,
deterministic simulator fixture and must not be treated as production ECU cryptography.

## 9. Error and Consistency Contract

| Condition | Stable code | HTTP | UDS evidence |
|---|---|---|---|
| Changed reuse of a diagnostic command ID | `diagnostic_command_conflict` | 409 | Command identity conflict before PDU execution |
| Stale session version | `diagnostic_contract_invalid` | 422 | NRC `0x22` conditions not correct |
| Unsupported DTC group | `diagnostic_contract_invalid` | 422 | NRC `0x31` request out of range |
| DID type/range violation | `diagnostic_contract_invalid` | 422 | NRC `0x31` request out of range |
| Stale DID or session version | `diagnostic_contract_invalid` | 422 | NRC `0x22` conditions not correct |
| DID forbidden in active session | `diagnostic_contract_invalid` | 422 | NRC `0x7F` service not supported in active session |
| Routine forbidden in active session | `diagnostic_contract_invalid` | 422 | NRC `0x7F` service not supported in active session |
| Stale routine or session version | `diagnostic_contract_invalid` | 422 | NRC `0x22` conditions not correct |
| Unsupported stop or unknown routine identifier | `diagnostic_contract_invalid` | 422 | NRC `0x31` request out of range |
| sendKey without a valid seed | `diagnostic_contract_invalid` | 422 | NRC `0x24` request sequence error |
| Invalid Security Access key | `diagnostic_contract_invalid` | 422 | NRC `0x35` invalid key |
| Third invalid key | `diagnostic_contract_invalid` | 422 | NRC `0x36` exceed number of attempts |
| Access during logical lockout | `diagnostic_contract_invalid` | 422 | NRC `0x37` required time delay not expired |
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

### ADR-DG-005 - Model DIDs as Typed Semantic Data

DIDs describe automotive information explicitly instead of exposing arbitrary ECU memory. This
supports stable validation, session policy, OpenAPI contracts, and future VHAL/CAN mappings.

### ADR-DG-006 - Preserve Values for Replay but Minimize Shared Evidence

Command results retain DID values so an exact retry is truthful. Audit and outbox records exclude
those values and share only identifiers, counts, service identities, and versions.

### ADR-DG-007 - Separate Routine Definition from Execution State

Routine engineering metadata changes independently from each execution lifecycle. A one-to-one
state record makes concurrency and lifecycle transitions explicit without rewriting definitions.

### ADR-DG-008 - Complete Routines from ECU Logical Time

Routine completion is evaluated against simulation time when the state is observed. No sleeping,
host timer, worker loop, GPU, or cloud service is required, which keeps simulation and tests
deterministic and inexpensive.

### ADR-DG-009 - Protect Routine Values in Shared Evidence

Parameters and results remain in protected state and command records for faithful replay. Audit
and outbox payloads contain only identifiers, subfunctions, status, counters, timestamps, and
versions to avoid distributing engineering measurements or sensitive routine inputs.

### ADR-DG-010 - Separate Security Challenge State from Session Authorization

Challenge lifecycle and invalid-attempt policy need their own optimistic version, while the
unlocked level belongs to the current diagnostic session. This separation makes concurrency,
session reset, and lockout behavior explicit.

### ADR-DG-011 - Persist Negative Attempts Before Returning an Error

Invalid-key attempts are security state changes, not validation-only failures. The service writes
versioned command, audit, and outbox evidence atomically, and the endpoint commits that evidence
before returning the stable UDS-aware error. Exact retries replay the same denial without another
attempt increment.

### ADR-DG-012 - Use Transparent Simulator Cryptography with Strict Secret Hygiene

A deterministic public derivation supports reproducible study and black-box tests without paid
services or secret provisioning. It is explicitly non-production. Raw keys are masked and never
persisted; seeds and digests stay in protected state/command storage and never enter shared audit
or outbox evidence.

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
| Migration lifecycle | Upgrade and downgrade all diagnostic tables. | Integration |
| Regression | Preserve ECU, CAN, identity, audit, and platform behavior. | Full suite |
| DID definition | Accept valid scalar types and reject mismatched initial values. | Schema/service |
| DID catalogue bound | Reject a 129th DID and enforce page limit 128. | Service/OpenAPI |
| Multi-DID read | Read one to sixteen unique DIDs in request order. | Service/API |
| Read session denial | Return NRC `0x7F` when any DID disallows the active session. | Service/API |
| DID write authorization | Require writable metadata, permitted session, and manage RBAC. | Service/API |
| DID version concurrency | Reject stale session or DID versions with NRC `0x22`. | Service/integration |
| DID value constraints | Reject type, numeric range, and string-length violations with NRC `0x31`. | Schema/service |
| DID replay | Return persisted `0x22`/`0x2E` evidence without repeated mutation. | Service/integration |
| DID evidence minimization | Prove audit and outbox never contain DID values. | Service |
| Routine schema bounds | Reject identifiers, durations, parameters, and result templates outside fixed limits. | Schema/OpenAPI |
| Routine catalogue bound | Reject a 65th routine and enforce page limit 64. | Service/OpenAPI |
| Routine start | Move idle state to running with ECU logical timestamps and incremented version. | Service/integration |
| Routine session policy | Return NRC `0x7F` when the active session is not allowed. | Service/API |
| Routine stop capability | Return NRC `0x31` when stop is unsupported; otherwise stop at logical time. | Service/API |
| Routine stale version | Return NRC `0x22` without mutation when the state version does not match. | Service/API |
| Routine completion | Complete exactly at the declared ECU logical timestamp without sleeping. | Service/integration |
| Routine result | Return the bounded protected result only through the authorized response. | Service/API |
| Routine replay | Return persisted `0x31` evidence without repeated execution or version change. | Service/integration |
| Routine evidence minimization | Prove audit and outbox contain neither parameters nor result values. | Service |
| Routine atomicity | Commit definition/state/control, command, audit, and outbox evidence together. | Integration |
| Security command shape | Require a 16-character masked key only for sendKey and reject extra fields. | Schema/OpenAPI |
| Security session policy | Reject Security Access in default session with NRC `0x7F`. | Service/API |
| Seed generation | Return a deterministic 16-character seed and 30,000-ms logical expiry. | Service/integration |
| Seed replay | Return the same protected seed without incrementing challenge or version twice. | Service/integration |
| Valid key | Unlock level 1, clear challenge state, and increment session/security versions. | Service/integration |
| Missing/expired seed | Reject sendKey with NRC `0x24` without unlocking. | Service/API |
| Invalid key | Persist a failed attempt and return NRC `0x35`. | Service/API |
| Attempt ceiling | Third invalid key returns NRC `0x36` and starts a 10,000-ms logical delay. | Service/integration |
| Lockout delay | Return NRC `0x37` before the deadline and permit a new seed exactly at expiry. | Service/integration |
| Negative replay | Repeat a persisted denial without another failed-attempt increment. | Service/integration |
| Secret minimization | Prove raw key, seed, and key digest never enter audit or outbox evidence. | Service/security |
| Safe state query | Expose versions, attempt count, lockout, and challenge presence without secret material. | API/OpenAPI |
| Security atomicity | Commit failed attempt, command, audit, and outbox before returning the negative response. | Integration |

## 12. Implemented Evidence

- `src/atep/diagnostics/` contains models, schemas, service, and router.
- Migration `0031_diagnostics_foundation` owns session, command, and DTC persistence.
- Migration `0032_diagnostic_data_identifiers` owns typed DID persistence and versioning.
- Migration `0033_diagnostic_routines` owns routine definitions and execution states.
- Migration `0034_diagnostic_security_access` owns the ECU Security Access challenge state.
- Events are `atep.diagnostics.session.changed.v1`, `atep.diagnostics.dtc.reported.v1`, and `atep.diagnostics.dtc.cleared.v1`.
- Permissions are `diagnostics:read` and `diagnostics:manage`.
- `tests/test_diagnostics.py` verifies contracts, logical time, versioning, replay, conflicts, evidence minimization, and permissions.
- API contract tests verify routes and safe pagination in generated OpenAPI.
- DID events are `atep.diagnostics.did.created.v1`, `atep.diagnostics.did.read.v1`, and `atep.diagnostics.did.written.v1`.
- Routine events are `atep.diagnostics.routine.created.v1` and `atep.diagnostics.routine.controlled.v1`.
- Security Access events use `atep.diagnostics.security.accessed.v1` without seed/key material.

## 13. Risks and Technical Debt

- V-1 through V-4 expose semantic UDS operations but do not yet encode wire PDUs.
- Status-mask meaning is retained as a byte; named bit helpers should be added with richer DTC queries.
- DTC creation is a controlled simulator boundary; automatic fault-to-DTC mapping is future work.
- The current clear operation loads at most 200 DTCs, matching the per-ECU V-1 storage bound.
- Security level 1 is implemented; additional OEM levels and protected production algorithms remain future work.
- Exact replay stores DID values in protected command evidence; retention and field-level access controls should be revisited before production telemetry use.
- Routine result templates are deterministic fixtures; future routines may require pluggable ECU behavior and explicit failure results.
- V-4 key derivation is transparent and deterministic for simulation; production security requires OEM algorithms, protected key material, hardware-backed execution, and threat analysis.

## 14. Roadmap

V-1 through V-4 are implemented. The recommended next development is V-5: ECU Reset (`0x11`)
integrated with the ECU lifecycle, diagnostic-session/security reset, deterministic logical time,
exact replay, RBAC, audit, outbox, and failure-safe evidence.

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
16. Calculate the positive response identities for `0x22` and `0x2E`.
17. Explain why a DID version changes without changing the diagnostic-session version.
18. Design a string DID with a maximum length and its negative tests.
19. Compare NRC `0x31` for an invalid value with NRC `0x7F` for the active session.
20. Trace an exact `0x2E` retry and prove the DID version increments only once.
21. Calculate the positive response identity for Routine Control `0x31`.
22. Trace startRoutine from RBAC through session authorization, version checks, state, audit, and outbox.
23. Explain why routine completion uses ECU logical time instead of a background timer.
24. Design tests for stopRoutine when stop is supported, unsupported, or the routine is not running.
25. Prove that a repeated start command does not increment invocation count twice.
26. Compare definition version and execution-state version for an ECU routine.
27. Explain why parameters/results are protected while status/version evidence may be shared.
28. Design a battery-balancing routine and its allowed diagnostic sessions.
29. Calculate the positive response identity for Security Access `0x27`.
30. Trace requestSeed and identify where the seed may and may not appear.
31. Derive the simulator key for a sample seed and explain why the algorithm is not production-safe.
32. Design a test proving raw keys never enter command results, audit, outbox, or logs.
33. Compare NRC `0x24`, `0x35`, `0x36`, and `0x37` in the implemented flow.
34. Prove an exact invalid-key retry does not increment failed attempts twice.
35. Advance ECU logical time to one millisecond before and exactly at lockout expiry.
36. Explain why Security Access state and diagnostic-session security level use separate versions.
