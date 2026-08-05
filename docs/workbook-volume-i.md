# ATEP Volume I — Core Platform Engineering Workbook

**Subtitle:** Architecture, implementation record, verification strategy, and engineering evidence  
**Project:** Automotive Test Engineering Platform (ATEP)  
**Document version:** 0.26.0

**Baseline date:** 4 August 2026

**Status:** Living engineering document — software supply-chain security baseline implemented
**Language:** English

## Document Purpose

This workbook records how Volume I of ATEP was conceived, designed, implemented, and verified. It is intended to serve simultaneously as an engineering specification, onboarding guide, verification catalogue, decision log, and portfolio evidence pack. It should be updated whenever an architectural decision, requirement, implementation, test, risk, or operational procedure changes.

The document distinguishes three types of statements:

- **Implemented:** present in the repository and validated to the extent recorded in the verification section.
- **Planned:** accepted as part of the Volume I roadmap but not yet implemented.
- **Target:** a measurable production objective that requires a deployed environment and operational evidence.

## Document Control

| Field | Value |
|---|---|
| Owner | ATEP Core Platform Engineering |
| Review audience | Software architects, backend engineers, QA engineers, DevOps engineers, and technical recruiters |
| Review cadence | At the end of every development increment |
| Source of truth | Repository code, migrations, automated tests, and this workbook |
| Classification | Portfolio / Engineering documentation |

### Revision History

| Version | Date | Change | Verification status |
|---|---|---|---|
| 0.1.0 | 13 July 2026 | Initial Volume I workbook covering Increment 1 | Unit tests, lint, typing, migration and OpenAPI checks recorded |
| 0.2.0 | 14 July 2026 | Added user administration, role assignment, global errors, immutable audit, and atomic user-created event | 16 tests, lint, strict typing, migration DDL and OpenAPI checks recorded |
| 0.2.1 | 15 July 2026 | Executed the Docker topology, removed the migration/worker startup race, fixed async user serialization, and validated bootstrap email configuration | 17 tests, lint, strict typing, container health, and end-to-end administration evidence recorded |
| 0.3.0 | 15 July 2026 | Added a disposable integration topology, black-box PostgreSQL/RabbitMQ/API verification, ephemeral credentials, automatic cleanup, and CI workflow | 17 fast tests and one clean-stack integration scenario passed locally; Ruff and strict typing passed |
| 0.4.0 | 15 July 2026 | Added opaque refresh tokens, atomic rotation, reuse-family revocation, session logout, global logout, security audit evidence, and migration `0003` | 19 fast tests and one expanded clean-stack integration scenario passed; migration DDL, Ruff, and strict typing passed |
| 0.5.0 | 15 July 2026 | Added role and permission catalogue APIs, protected-role invariants, auditable permission management, and API-only RBAC integration | 28 fast tests and one expanded disposable Docker integration scenario passed; Ruff and strict typing passed |
| 0.6.0 | 15 July 2026 | Added permission-separated audit search, record inspection, bounded CSV export, query indexes, export evidence, and the retention-policy baseline | 32 fast tests and one expanded disposable Docker integration scenario passed; migration DDL, Ruff, and strict typing passed |
| 0.7.0 | 15 July 2026 | Added atomic Redis-backed authentication/account and versioned-API rate limiting, hashed limiter identities, stable retry metadata, and fail-closed dependency behavior | 35 fast tests and one expanded disposable Docker integration scenario passed; Ruff and strict typing passed |
| 0.8.0 | 15 July 2026 | Added the persistent ATEP module registry, versioned capability catalogue, independent RBAC permissions, migration `0005`, audit evidence, and transactional module events | 41 fast tests and one expanded disposable Docker integration scenario passed; Ruff and strict typing passed |
| 0.9.0 | 15 July 2026 | Added one-time module workload credentials, authenticated heartbeats, bounded availability leases, automatic expiry reconciliation, migration `0006`, system audit evidence, and availability events | 44 fast tests and one expanded disposable Docker integration scenario passed; Ruff and strict typing passed |
| 0.10.0 | 4 August 2026 | Defined ATEP and CarSystemUI as one coordinated platform; added the vehicle catalogue, gateway workload authorization, idempotent telemetry ingestion, migration `0007`, and automotive integration requirements | 50 fast tests and one expanded disposable Docker integration scenario passed; Ruff and strict typing passed |
| 0.11.0 | 4 August 2026 | Connected the CarSystemUI showcase to the ATEP telemetry contract with changed-property mapping, a persistent store-before-send queue, stable retry identifiers, bounded rejection storage, configuration-safe disablement, and gateway status UI | Android debug APK assembled and five gateway unit tests passed; live Android-to-ATEP execution remains the manual `CT-SHOW-006` evidence step |
| 0.12.0 | 4 August 2026 | Introduced `VehiclePropertySource`, retained the deterministic simulator, and added a read-only AAOS CarPropertyManager/VHAL compatibility source with explicit provenance, safe partial availability, unit conversion, and no silent simulation fallback | Android APK, lint, and nine unit tests passed; live VHAL execution remains the manual `CT-SHOW-007` evidence step |
| 0.13.0 | 4 August 2026 | Added one unique connectivity-constrained WorkManager retry job per vehicle, 30-second exponential backoff, an eight-attempt bound, disabled-mode suppression, queue reconciliation, and process-death scenario `CT-SHOW-008` | Four retry-policy tests were added; final dependency download, Android execution, and live process-death evidence remain pending |
| 0.14.0 | 4 August 2026 | Added persistent rejected-event inspection, unchanged-identity retry, selective discard, observable background-attempt exhaustion, explicit recovery, and operator scenario `CT-SHOW-009` | Android dependency resolution, debug APK assembly, 18 tests, and lint completed; live operator evidence remains pending |
| 0.15.0 | 4 August 2026 | Added idempotent vehicle-command requests, capability-targeted claim, hash-only lease tokens, terminal acknowledgements, safe Android property execution, and scenario `CT-SHOW-010` | 55 Python tests and 24 Android tests passed; APK and lint completed; live emulator-to-ATEP command evidence remains pending |
| 0.16.0 | 4 August 2026 | Executed `CT-SHOW-010` against a live Android Automotive emulator and disposable ATEP stack, including safe mutation, validation and safety rejection, capability denial, lease recovery, telemetry, audit, outbox, and explicit AAOS read-only behavior | All ten scenario steps passed; seven commands reached terminal state (four succeeded and three rejected), the recovery command completed on attempt two, and 25 telemetry observations were retained |
| 0.17.0 | 4 August 2026 | Added persistent vehicle-scoped test runs, idempotent creation, row-locked optimistic transitions, audit/outbox evidence, Redis Pub/Sub, authenticated WebSocket snapshots and updates, and a reconnecting CarSystemUI live-status card | 60 Python tests and 27 Android tests passed; Ruff, strict mypy, Android lint and debug APK passed; the disposable PostgreSQL/Redis/RabbitMQ/WebSocket scenario passed |
| 0.18.0 | 5 August 2026 | Added immutable environment profiles for electric, hybrid, and autonomous test contexts, independent read/manage RBAC, bounded configuration, auditable lifecycle events, migration `0010`, and versioned TestRun snapshots | 64 Python tests passed; Ruff and strict mypy passed; the monitored suite peaked at 163.9 MiB Python working memory with no Gradle, Docker, emulator, or LibreOffice workload |
| 0.19.0 | 5 August 2026 | Added persistent scheduled test jobs, independent read/manage RBAC, idempotent creation, optimistic cancellation, bounded multi-instance-safe due selection, atomic TestRun dispatch, migration `0011`, audit, and outbox evidence | 69 fast Python tests, Ruff, and strict mypy passed locally; the monitored suite completed in 1.77 seconds with 2.72 CPU-seconds and 169.6 MiB peak Python memory; disposable Docker integration is delegated to CI |
| 0.20.0 | 5 August 2026 | Added immutable TestRun artifacts, a replaceable object-store protocol, atomic filesystem promotion, bounded multipart upload, SHA-256 integrity, independent read/write RBAC, protected download, migration `0012`, audit, and outbox evidence | 74 fast Python tests, Ruff, and strict mypy passed locally; the monitored suite completed in 1.79 seconds with 2.91 CPU-seconds and 171.1 MiB peak Python memory; disposable upload/download integration is delegated to CI |
| 0.21.0 | 5 August 2026 | Added bounded Prometheus HTTP metrics, OpenTelemetry server spans, W3C trace propagation, correlated log/response identifiers, configurable parent-based sampling and OTLP/HTTP export, an optional pinned Collector/Prometheus/Grafana topology, and a provisioned overview dashboard | 80 fast Python tests, Ruff, strict mypy, focused propagation/cardinality tests, and Compose validation passed locally; the monitored suite completed in 1.96 seconds with 2.98 CPU-seconds and 178.0 MiB peak Python memory; Docker scrape evidence is delegated to CI |
| 0.22.0 | 5 August 2026 | Added permission-protected aggregate module health, bounded registry metrics, API availability/latency recording rules, multi-window error-budget alerts, module-state/lease alerts, runbook response procedures, and CI `promtool` validation | 86 fast Python tests, Ruff, strict mypy, focused health/metric/rule tests, Compose validation, and remote Prometheus rule validation |
| 0.23.0 | 5 August 2026 | Added internal outbox-worker metrics, aggregate outbox/scheduler backlog age, scheduler throughput/failure metrics, bounded WebSocket connection/message/live-publish metrics, six domain alerts, dashboard panels, controlled worker retry, and expanded Docker scrape evidence | 89 fast Python tests plus the expanded disposable integration scenario, Ruff, strict mypy, Compose validation, and `promtool` validation |
| 0.24.0 | 5 August 2026 | Added pinned Alertmanager routing, critical/warning grouping intervals, same-service inhibition, firing/resolved delivery, a loopback-only aggregate webhook receiver, bounded delivery metrics, configuration tests, `amtool` validation, and synthetic end-to-end CI delivery | 92 fast Python tests plus the expanded Docker and live alert-delivery scenarios, Ruff, strict mypy, Compose validation, `promtool`, and `amtool` |
| 0.25.0 | 5 August 2026 | Added bounded PostgreSQL/Redis/RabbitMQ readiness metrics, a replaceable artifact-store instrumentation decorator, operation latency/outcomes, transferred bytes, optional filesystem capacity, three runbook-linked alerts, and expanded Docker scrape evidence | 94 fast Python tests plus the expanded disposable integration scenario, Ruff, strict mypy, cardinality/privacy checks, and `promtool` validation |
| 0.26.0 | 5 August 2026 | Added hash-locked runtime/development dependencies, digest/SHA-pinned build inputs, weekly update automation, history/secret scanning, Python dependency and CodeQL analysis, CycloneDX SBOMs, and a high/critical image vulnerability gate | 97 fast Python tests, Ruff, strict mypy, and lock-policy tests passed locally; deterministic lock regeneration, dependency audit, image scan, and CodeQL are enforced by remote CI |

## How to Use This Workbook

1. Read the executive summary and system context before changing platform boundaries.
2. Consult the requirements and architecture sections before implementation.
3. Add or update an architecture decision whenever a choice has long-term consequences.
4. Select tests from the verification catalogue and record evidence after execution.
5. Update risks, technical debt, and lessons learned during increment reviews.
6. Preserve the distinction between verified facts, planned work, and production targets.

## 1. Executive Summary

Volume I establishes the control-plane foundation for all later ATEP volumes. Its responsibility is not to simulate a vehicle directly. It provides the trusted platform capabilities through which vehicle models, ECUs, networks, diagnostics, test automation, AI services, and dashboards will authenticate, exchange events, persist configuration, and expose operational health.

Increment 1 implements a modular FastAPI service and an independently deployable outbox worker. PostgreSQL is the system of record, Redis is reserved for ephemeral and coordination workloads, and RabbitMQ is the asynchronous integration backbone. Identity uses short-lived JWT access tokens, Argon2 password hashing, and deny-by-default role-based access control. Domain events use a transactional outbox to avoid losing messages between database commits and broker publication.

The first Increment 2 slice adds the administrator workflow: create a user, retrieve or page through users, activate or deactivate an account, and assign or remove roles. Every operation is permission protected. User creation adds `atep.identity.user.created.v1` to the outbox before the same commit, while security-relevant changes append an audit record that PostgreSQL protects from update and deletion. API and validation failures now use one correlation-aware error envelope.

The authentication hardening slice adds longer-lived opaque refresh tokens whose SHA-256 hashes are the only persisted representation. Every refresh rotates the secret in one database transaction. Reuse of an older token is treated as possible credential theft and revokes the complete token family. Session logout and user-wide logout revoke future renewal and append non-sensitive audit evidence.

The role-catalogue slice removes the need for database queries during normal RBAC administration. Administrators can list the permission catalogue; create, page, inspect, and update roles; grant or revoke permissions; and safely delete unused roles through versioned APIs. Canonical names and stable conflicts protect client behavior. The `platform-admin` role cannot be renamed, stripped of permissions, or deleted, and any assigned role must be detached before deletion. Every effective mutation appends correlated audit evidence.

The audit-query slice makes that evidence usable without weakening immutability. Investigators can search by actor, action, resource, outcome, correlation ID, and timezone-aware date range; inspect one record; or export a bounded CSV under a separate permission. Results are indexed and ordered newest first. Export creates its own non-sensitive audit record and neutralizes formula-like spreadsheet cells. The approved retention baseline keeps at least 365 days online and seven years in a future immutable archive, while the current implementation conservatively retains all records in PostgreSQL until archive automation is delivered.

The rate-limiting slice turns Redis from a readiness-only dependency into an active distributed protection control. Token requests consume independent atomic counters for the normalized-account and network-client fingerprints; other versioned APIs use a credential or network-client fingerprint. Redis keys contain only SHA-256-derived identifiers and expire with their fixed window. Successful requests expose limit, remaining, and reset metadata; excess traffic receives the global error envelope with HTTP 429 and `Retry-After`. Redis failures return a controlled HTTP 503 rather than silently bypassing the policy.

The first Increment 3 slice establishes an authoritative catalogue for the modules delivered by later ATEP volumes. Administrators can register, inspect, page, filter, and update modules, while separately declaring or removing semantic-versioned capabilities such as `can.frames.publish`. Canonical names and uniqueness constraints keep discovery deterministic. Independent `modules:read` and `modules:manage` permissions enforce least privilege, and every effective catalogue mutation appends correlated audit evidence and a versioned outbox event in the same transaction.

The operational-registry hardening slice separates human administration from workload identity. An administrator issues or rotates a high-entropy module credential whose raw value is returned once and whose SHA-256 digest is the only persisted form. The authenticated module reports `active` or `degraded` and renews a bounded 5–3,600-second lease through heartbeat. A background reconciler marks expired modules `inactive`, appends system audit evidence, and enqueues an availability event. Routine heartbeats deliberately create neither audit records nor events unless status or version changes, preventing high-volume evidence noise.

The initial automotive-integration slice connects the Volume I control plane to the separately deployed CarSystemUI Android Automotive project. ATEP and CarSystemUI are treated as one coordinated testing platform for electric, hybrid, and autonomous vehicles while preserving independent repositories and release histories. Administrators manage canonical vehicle records with JWT/RBAC. An unattended Vehicle Gateway authenticates with a hash-only module credential, declares `vehicle.telemetry.publish`, and sends timezone-aware observations only through the public API. Each client event ID is idempotent: an exact retry returns the original receipt, while reuse for different data returns a stable conflict. The observation and `atep.vehicle.telemetry.received.v1` outbox event are committed atomically.

The Android-side integration now implements the first executable Vehicle Gateway in the CarSystemUI showcase. A mapper emits only changed simulated properties with client-generated identifiers and UTC timestamps. A SharedPreferences-backed store persists events before synchronous HTTP delivery, retains temporary failures for retry with the same identity, and moves permanent client rejection into a bounded local rejected-event set. The screen reports disabled, synchronized, pending, and rejected states without displaying credentials. The debug APK and five focused unit tests passed locally; a live emulator-to-ATEP execution is deliberately recorded as pending rather than inferred from separate component tests.

The next Android slice removes the gateway's dependency on a simulated origin. `VehiclePropertySource` now supplies the same immutable state from either a deterministic mutable simulator or a read-only AAOS source. The AAOS compatibility bridge uses runtime CarPropertyManager callbacks for speed, gear, ignition, battery energy/capacity, and charging-port state; converts speed from metres per second to kilometres per hour; and calculates state of charge from watt-hour values. The screen labels the evidence origin and removes local controls in AAOS mode. Unsupported or unauthorized properties are reported without silently substituting simulator data. Four source-focused tests raise the Android total to nine; a live AAOS/VHAL run remains explicitly pending.

The background-delivery slice replaces activity-dependent retry with WorkManager orchestration. Any pending queue reconciles to one uniquely named job per vehicle under `ExistingWorkPolicy.KEEP`. Network connectivity is mandatory; failure returns retry with a 30-second exponential backoff, and the policy stops after eight worker attempts while retaining the source events. Manual or successful delivery cancels redundant work, and disabled gateway configuration schedules nothing even if an older queue exists. Six policy tests and `CT-SHOW-008` document success, retry, exhaustion, disabled mode, process termination, reconnection, and idempotent backend evidence. WorkManager `2.11.2` resolved successfully and the complete Android unit suite, debug APK assembly, and lint task executed on Windows; live process-death evidence remains pending.

The operator-evidence slice makes permanent rejection and retry exhaustion actionable. A persistent rejected-event view shows canonical property, value, unit, timestamp, original identifier, and a non-sensitive reason without exposing credentials. Retrying one record atomically restores that exact event to the pending queue; discarding removes only the selected rejected record. WorkManager attempt count and exhaustion are persisted and observed by the `ViewModel`, and exhausted work cannot schedule itself again until the operator explicitly resumes delivery. Five additional focused tests and `CT-SHOW-009` cover inspection, unchanged identity, selective disposition, persistent exhaustion, and manual recovery. All 18 Android tests passed; live operator execution remains pending.

The command-delivery slice closes the first authorized control loop from ATEP to the Android simulator. An operator with `vehicle_commands:write` creates an idempotent `set_property` request for one vehicle and a module declaring `vehicle.commands.consume`. The gateway atomically claims the oldest available request under a bounded lease; the raw claim token is returned only to that claim and only its SHA-256 digest is stored. Success, validation rejection, and unsafe-state rejection become terminal acknowledgements and versioned outbox evidence. CarSystemUI polls while workload configuration is enabled, accepts a reviewed property allowlist, enforces value and vehicle-state invariants, and refuses to mutate an explicit read-only AAOS source. Six focused Android tests raise that suite to 24; 55 Python tests cover the backend contract. Live `CT-SHOW-010` execution on the `ATEP_AAOS_API35` emulator passed all ten steps: four commands succeeded, three were safely rejected, capability denial returned the stable error, and an abandoned lease recovered on attempt two without creating a duplicate logical command.

The live test-run slice adds an authoritative execution record around that control loop. An operator with `test_runs:write` creates a vehicle-scoped run whose external identifier is idempotent. The lifecycle accepts only queued-to-running-to-terminal transitions. Each mutation locks the row, checks the expected version, and commits status, immutable audit evidence, and a versioned outbox event together. After commit, Redis Pub/Sub projects the update to authenticated WebSocket subscribers; PostgreSQL and the outbox remain authoritative if that projection fails. CarSystemUI uses a separately injected development operator token, receives a snapshot, ignores non-increasing versions, reconnects with bounded exponential delay, and presents connection, suite, status, progress, summary, and version without displaying credentials.

The environment-profile slice makes test setup a named, controlled input instead of an informal collection of variables. A profile declares electric, hybrid, or autonomous vehicle context; simulator or AAOS property source; and a JSON-compatible configuration bounded to 16 KiB. Profiles are immutable after creation and move only from draft to active to archived under independent RBAC, optimistic version checks, audit, and outbox evidence. TestRun creation accepts only an active profile and copies its identifier, version, vehicle kind, property source, and configuration. Archiving the source profile therefore cannot alter the evidence required to reproduce an earlier run.

The initial design deliberately starts as a modular monolith rather than a collection of empty microservices. Clear package boundaries and versioned event contracts allow later extraction when scaling, ownership, availability, or release cadence provides a concrete reason. This reduces operational complexity while protecting the intended distributed architecture.

### Current Increment at a Glance

| Capability | Status | Evidence |
|---|---|---|
| FastAPI control-plane API | Implemented | Versioned authentication and health routes load in OpenAPI |
| Authentication | Implemented | Short-lived JWT access tokens, opaque refresh rotation/revocation, generic failures, and Argon2 hashing |
| RBAC data model | Implemented | User, role, permission, and association tables |
| User administration | Implemented | Create, list, inspect, status, role assignment, and role removal routes |
| Role catalogue administration | Implemented | Permission listing; role create, page, inspect, update, grant, revoke, and safe delete routes |
| PostgreSQL persistence | Implemented | SQLAlchemy models and Alembic revisions `0001` through `0012` |
| Module registry | Implemented | Persistent metadata, capability catalogue, hash-only workload credentials, heartbeat leases, and automatic reconciliation |
| Vehicle integration boundary | Implemented initial slice | Vehicle catalogue, lifecycle state, gateway capability authorization, idempotent telemetry, and outbox contract |
| Android Vehicle Gateway | Implemented initial slice | Changed-property mapping, persistent queue, stable retry identity, bounded rejection storage, HTTP transport, and status UI in the CarSystemUI showcase |
| Android vehicle property sources | Implemented initial AAOS slice | Replaceable simulator/AAOS source, provenance status, read-only AAOS UI, safe partial availability, and canonical conversions |
| Android background telemetry retry | Implemented and build verified | Unique per-vehicle WorkManager job, connected-network constraint, bounded exponential retry, lifecycle-independent queue flush, six policy tests, and manual process-death scenario |
| Android telemetry operator evidence | Implemented and build verified | Persistent rejected-event details, unchanged-identity retry, selective discard, attempt/exhaustion state, explicit recovery, five focused tests, and `CT-SHOW-009` |
| Vehicle command delivery | Implemented initial REST slice | RBAC request, target capability, atomic claim, bounded lease, hash-only claim token, idempotent acknowledgement, safe Android executor, and `CT-SHOW-010` |
| Test-run orchestration and live status | Implemented initial slice | Persistent lifecycle, independent RBAC, idempotency, optimistic locking, audit/outbox evidence, Redis Pub/Sub, authenticated WebSocket, and CarSystemUI live card |
| Environment profiles | Implemented initial slice | Immutable EV/hybrid/autonomous context, simulator/AAOS source, bounded configuration, lifecycle RBAC, audit/outbox, and TestRun snapshot |
| Test-job scheduler | Implemented initial slice | Persistent idempotent schedule, bounded queries, optimistic cancellation, `SKIP LOCKED` due selection, atomic TestRun dispatch, audit, and outbox |
| Test-artifact storage | Implemented initial slice | Immutable metadata, replaceable object-store interface, streaming filesystem adapter, SHA-256, bounded multipart upload, independent RBAC, audit, outbox, and protected download |
| Platform observability | Implemented initial slice | Route-template HTTP metrics, W3C trace context, trace/correlation response and log context, OTLP/HTTP export, optional Collector/Prometheus/Grafana stack, and versioned dashboard |
| Administrative audit | Implemented | Immutable evidence, indexed bounded search, individual inspection, audited CSV export, and retention baseline |
| API error contract | Implemented | Application, HTTP, validation, and unexpected-error handlers |
| Reliable event publication | Implemented | Transactional outbox, resilient RabbitMQ startup, and publisher worker |
| Redis integration | Implemented | Readiness plus atomic expiring authentication and versioned-API rate-limit counters |
| Structured logging | Implemented | JSON logs with request correlation context |
| Container environment | Implemented and locally executed | One-shot migration, API, worker, PostgreSQL, Redis, and RabbitMQ services verified with Docker Compose |
| Software supply-chain security | Implemented baseline | Hash locks, immutable build inputs, Gitleaks, pip-audit, CodeQL, CycloneDX SBOMs, Grype image gate, and Dependabot |
| Automated verification | Implemented | 97 fast tests plus expanded disposable black-box and live alert-delivery scenarios, 27 Android tests, Ruff, strict mypy, Android lint/build, and integration/security CI workflows |

## 2. Scope and Boundaries

### 2.1 In Scope for Volume I

- platform architecture and module boundaries;
- API conventions and service configuration;
- authentication, users, roles, and permissions;
- relational persistence and schema migration;
- caching and coordination infrastructure;
- message broker and event contracts;
- transactional event publication;
- structured logs and correlation identifiers;
- bounded Prometheus metrics, W3C trace propagation, configurable OTLP export, and versioned dashboards;
- liveness and readiness probes;
- local container orchestration;
- engineering quality gates and verification evidence.

### 2.2 Outside the Current Increment

- automated immutable audit archival, restore verification, legal-hold workflow, and disposition tooling;
- proxy-aware client attribution and production rate-limit tuning;
- production trace retention, authenticated telemetry transport, calibrated alert routing, and additional domain-specific metrics;
- Kubernetes deployment and workload identity;
- secret-manager integration and service-to-service mTLS;
- vehicle, ECU, CAN, diagnostics, test execution, AI, and dashboard domain behavior.

These items remain within the broader ATEP roadmap, but they must not be represented as implemented until code and evidence exist.

### 2.3 Volume I Exit Criterion

Volume I is complete when ATEP can be deployed repeatably and support the first end-to-end BMS temperature / CAN message / DTC / automated test event flow without redesigning its security, persistence, configuration, observability, or event-delivery foundations.

## 3. System Context and Architecture

### 3.1 Context

External dashboards, test automation clients, and future ATEP modules call the Core API. The API owns synchronous control-plane operations and writes authoritative state to PostgreSQL. Redis provides low-latency ephemeral state. Business changes that require asynchronous integration create outbox records in the same database transaction. A dedicated worker publishes those records to a durable RabbitMQ topic exchange, where future modules can subscribe independently.

### 3.2 Logical Components

| Component | Responsibility | Primary dependency |
|---|---|---|
| Core API | HTTP boundary, authentication, health, request context | FastAPI |
| Identity context | Users, credentials, roles, permissions, bootstrap administration | PostgreSQL |
| Registry context | ATEP module metadata, administrative status, and versioned capability declarations | PostgreSQL |
| Audit context | Append-only evidence for security-relevant administrative actions | PostgreSQL |
| Persistence layer | Async sessions, mappings, constraints, schema evolution | SQLAlchemy, asyncpg, Alembic |
| Event outbox | Atomic recording of integration events | PostgreSQL |
| Outbox worker | Ordered batch selection and durable broker publication | RabbitMQ, aio-pika |
| Ephemeral services | Atomic rate limits plus future cache, locks, and coordination | Redis |
| Observability foundation | Structured logs, W3C trace propagation, OTLP export, bounded metrics, and dashboards | structlog + OpenTelemetry + Prometheus + Grafana |
| Local platform | Repeatable service topology and dependency health | Docker Compose |

### 3.3 Request and Event Flow

1. A client sends an HTTP request and may provide an `X-Correlation-ID` header.
2. Middleware validates the identifier or generates a UUID, binds it to logging context, and returns it in the response.
3. The Redis-backed dependency consumes the applicable expiring API and authentication counters before protected work executes.
4. Authentication validates a bearer token and loads the active user.
5. Authorization compares required permissions against the permissions granted through roles.
6. An application operation changes PostgreSQL state, appends its audit evidence, and records any integration event in the outbox inside the same transaction.
7. The outbox worker locks unpublished rows with `SKIP LOCKED`, publishes persistent messages to `atep.events`, and marks confirmed messages as published.
8. Consumers use `event_id` for idempotency because delivery is at least once.

### 3.4 Bounded Context Rules

- A context owns its persistence models and application rules.
- Other contexts must not query or import those models directly.
- Cross-context integration uses application interfaces or versioned events.
- External APIs are versioned under `/api/v1`.
- Events use the routing-key convention `atep.<context>.<entity>.<past-tense-action>.v1`.
- Identifiers are UUIDs and timestamps are UTC ISO 8601 values.
- Authorization is deny-by-default; permissions use namespaced verbs such as `users:read`.

## 4. Architecture Decision Record

### ADR-001 — Start with a Modular Monolith

**Decision.** Implement the first control plane as one modular API plus independently deployable workers. Extract services only when justified by load, availability, ownership, security isolation, or release cadence.

**Rationale.** The platform currently has one development team and no measured scaling boundaries. Premature microservices would multiply deployments, networking, tracing, security, and data-consistency problems before delivering domain value.

**Consequences.** Package boundaries must be enforced carefully. Extraction remains possible, but shared-database shortcuts across contexts are prohibited.

### ADR-002 — PostgreSQL as the System of Record

**Decision.** Store authoritative identity, configuration, and outbox data in PostgreSQL. Use Redis only for ephemeral data.

**Rationale.** Relational constraints, transactional semantics, migration support, and operational maturity fit control-plane data and traceability requirements.

**Consequences.** Schema changes require migrations and compatibility review. Redis loss must not destroy authoritative business state.

### ADR-003 — Transactional Outbox for Integration Events

**Decision.** Persist business state and pending events in one database transaction, then publish asynchronously.

**Rationale.** Direct database-then-broker publication creates a failure window in which committed state has no corresponding event.

**Consequences.** Delivery is at least once, so consumers must be idempotent. Operational monitoring must detect old or repeatedly failing outbox rows.

### ADR-004 — Short-Lived JWT Access Tokens

**Decision.** Issue signed access tokens with subject, issuer, type, issued-at, and expiry claims. Hash passwords with Argon2.

**Rationale.** Short-lived tokens support stateless API authorization while limiting exposure. Argon2 is designed for password hashing and raises the cost of offline attacks.

**Consequences.** Refresh-token rotation and revocation are implemented in Increment 2. Signing secrets must still be injected and rotated outside source control.

### ADR-005 — Separate Liveness from Readiness

**Decision.** Liveness reports only whether the process responds. Readiness verifies PostgreSQL, Redis, and RabbitMQ with bounded timeouts.

**Rationale.** An orchestrator should restart a dead process but remove an otherwise healthy process from traffic when a critical dependency is unavailable.

**Consequences.** Dependency checks must remain fast and must not create excessive connection load.

### ADR-006 — Environment-Based Configuration

**Decision.** Load deploy-time configuration from environment variables with the `ATEP_` prefix and validate it through typed settings.

**Rationale.** The same artifact can be promoted across environments while secrets remain outside the repository.

**Consequences.** Deployment pipelines must provide required secrets, especially a JWT secret of at least 32 characters.

### ADR-007 — Opaque Refresh Tokens with Strict Rotation

**Decision.** Return a high-entropy opaque refresh token once, persist only its SHA-256 hash, rotate it under a row lock, and revoke the complete token family when an already-used token is presented.

**Rationale.** Opaque tokens keep session state revocable without placing durable credentials in the database. Strict single-use rotation detects replay and limits an exposed token chain.

**Consequences.** Concurrent refresh attempts are intentionally treated as reuse; clients must serialize renewal. Logout prevents future renewal, but already-issued stateless access tokens remain valid until expiration. High-risk deployments may later add Redis-backed access-token deny-listing.

### ADR-008 — Immutable Audit Evidence with Permission-Separated Access

**Decision.** Keep audit records append-only, expose bounded search and individual inspection through `audit:read`, and protect bounded CSV export separately through `audit:export`. Every export appends its own audit evidence. No public update or delete endpoint exists.

**Rationale.** Investigators need usable evidence, but search convenience must not create a mutation path or grant bulk extraction implicitly. Stable ordering, indexed filters, bounded result sizes, and separate permissions reduce operational and disclosure risk.

**Consequences.** The current database retains all evidence indefinitely. Production hardening must implement verified immutable archival, legal holds, restore exercises, and controlled disposition before online records can be removed.

### ADR-009 — Redis Atomic Counters for Distributed Abuse Control

**Decision.** Enforce fixed-window limits through one Redis Lua operation that increments the counter, establishes expiry on first use, and returns the counter and remaining lifetime atomically. Authentication uses separate normalized-account and network-client fingerprints; other `/api/v1` requests use a credential fingerprint when present or a network-client fingerprint otherwise. Only SHA-256-derived identifiers appear in Redis keys.

**Rationale.** Process-local counters diverge across replicas and disappear on restart. Atomic Redis state gives every API replica the same short-lived view without making Redis authoritative for business data. Separate authentication dimensions reduce both targeted password guessing and broad source-based spraying.

**Consequences.** Exceeded limits return HTTP 429 with stable retry metadata. Redis failure returns HTTP 503 so an outage cannot disable the security control silently. The current network identity is the direct peer address; production deployment behind trusted proxies must define and test a non-spoofable forwarding policy. Fixed-window burst behavior and thresholds require load evidence before production approval.

### ADR-010 — Persistent Module and Capability Catalogue

**Decision.** Store ATEP module registrations and their versioned capability declarations in PostgreSQL. Require canonical module and dot-separated capability names, semantic versions, independent read/manage permissions, bounded discovery queries, immutable audit evidence, and versioned transactional outbox events for effective mutations.

**Rationale.** Later volumes require a stable way to discover what a deployed module claims to provide without importing its persistence model or encoding deployment topology in clients. An authoritative catalogue makes capabilities queryable and eventable while preserving the existing control-plane security and transaction model.

**Consequences.** Consumers must treat capability versions as contracts and remain compatible during migration. Operational availability is hardened by ADR-011; instance-level registration and independent per-replica leases remain future scale work.

### ADR-011 — Authenticated Heartbeat Leases and Reconciliation

**Decision.** Separate administrator identity from module workload identity. An authorized administrator issues or rotates a high-entropy credential; the raw value is returned once and only its SHA-256 digest is persisted. An authenticated heartbeat may assert only `active` or `degraded`, optionally update semantic version, and renew a bounded lease. A periodic reconciler locks expired rows using `FOR UPDATE SKIP LOCKED`, marks them `inactive`, writes system audit evidence, and enqueues `atep.platform.module.availability-changed.v1` in the same transaction.

**Rationale.** Human JWTs are inappropriate for unattended workloads, manual status declarations become stale, and emitting evidence for every heartbeat would create noise and unnecessary storage. Hash-only storage reduces disclosure impact, bounded leases turn silence into an observable state transition, and row locking permits safe concurrent reconciliation.

**Consequences.** Credential distribution must be protected because possession authorizes heartbeat. Production hardening should replace or reinforce the shared secret with mTLS or managed workload identity, add lease/reconciliation metrics, and define multi-replica scheduling ownership. Instance-level registration remains necessary when one logical module has independently routable replicas.

### ADR-012 — Separate Control-Plane and In-Vehicle Communication Boundaries

**Decision.** Treat ATEP and CarSystemUI as one product architecture with two deployment and repository boundaries. Human Android operations use versioned REST/HTTPS and JWT/RBAC. The unattended Vehicle Gateway uses module workload identity and must declare `vehicle.telemetry.publish`. CarSystemUI and the gateway never connect directly to PostgreSQL, Redis, or RabbitMQ. Vehicle-local property access remains CarPropertyManager to CarService to VHAL; the gateway maps selected observations into the ATEP contract.

**Rationale.** Android UI concerns, AOSP build cadence, and VHAL permissions differ fundamentally from control-plane persistence and orchestration. A stable public contract permits simulated, emulated, and physical vehicle sources without coupling Android code to backend infrastructure. It also creates a reusable testing boundary for electric, hybrid, and autonomous-vehicle scenarios.

**Consequences.** The current shared module secret and injected development operator token must be protected on the Android side; managed OAuth2 workload tokens or mTLS remain production follow-ups. REST telemetry, command delivery, offline buffering, CarPropertyManager integration, and authenticated WebSocket test-run updates now establish the baseline. Durable command-acknowledgement buffering remains a subsequent slice.

### ADR-013 — Leased and Allowlisted Vehicle Commands

**Decision.** Model remote simulator control as an idempotent command addressed to one vehicle and one module declaring `vehicle.commands.consume`. Human creation uses `vehicle_commands:write`; workload claim and acknowledgement use the module credential. Claim selects and locks one available row, increments its attempt, grants a 10–300-second lease, returns a high-entropy token, and stores only its SHA-256 digest. Android executes only the `set_property` allowlist and acknowledges success or a stable rejection.

**Rationale.** A command must not be delivered to an unintended gateway, applied concurrently by multiple workers, or disappear when a process or network fails between execution and acknowledgement. A lease provides recovery, a claim token binds acknowledgement to the current delivery attempt, and idempotent property assignment makes replay after lease expiry predictable. The allowlist and state invariants prevent the generic JSON contract from becoming an unrestricted vehicle-control channel.

**Consequences.** The initial Android client polls every five seconds and has no separate durable acknowledgement queue; an interrupted acknowledgement therefore relies on lease expiry and safe replay. Explicit AAOS mode remains read-only. Future test-run orchestration may reference the existing optional `test_run_id`, add cancellation and priority, and publish live WebSocket status without changing the command ownership or security model.

### ADR-014 — PostgreSQL-Owned Scheduled Test Dispatch

**Decision.** Persist scheduled test jobs and treat PostgreSQL as the timing and ownership authority. Each scheduler replica selects a bounded oldest-first due batch with `FOR UPDATE SKIP LOCKED`. Dispatch creates the queued TestRun, links it to the job, changes the job state, and records audit/outbox evidence in one transaction. Pre-dispatch cancellation locks the row and requires an expected version.

**Rationale.** In-memory timers disappear on restart and can execute twice when the API scales horizontally. Durable state plus non-blocking row ownership permits safe recovery and concurrent replicas while retaining the existing transaction and evidence model.

**Consequences.** Polling introduces bounded dispatch latency configured from one to 300 seconds. Clock synchronization, scheduler lag metrics, concurrent multi-replica stress evidence, priority, recurrence, and misfire policies remain production-hardening work. The current lifecycle intentionally supports one-shot jobs only.

### ADR-015 — Separate Artifact Metadata from Binary Object Storage

**Decision.** Keep artifact identity, TestRun ownership, media metadata, size, and SHA-256 in PostgreSQL while storing binary content through an `ArtifactObjectStore` protocol. The development adapter streams to a temporary filesystem object and atomically promotes it under an internally generated key. The public API treats the client filename only as validated metadata and never discloses the object key.

**Rationale.** Database large objects would couple evidence volume to transactional storage, while direct filesystem or S3 access from clients would bypass RBAC and audit. A narrow adapter preserves the API and domain when the local implementation is replaced by S3/MinIO or managed cloud object storage.

**Consequences.** The metadata/audit/outbox transaction starts only after object creation succeeds and removes the new object on a detected database failure. A process crash inside that small boundary can leave an unreferenced object, so production requires orphan reconciliation. Multi-replica deployment also requires shared durable object storage, encryption, retention/lifecycle rules, malware scanning, quotas, and proxy-level request bounds; the local filesystem adapter is a development and disposable-integration implementation.

### ADR-016 — Correlated Signals with Bounded Metric Cardinality

**Decision.** Instrument HTTP centrally with OpenTelemetry server spans and a dedicated Prometheus registry. Accept valid W3C `traceparent`, return `X-Trace-ID`, and bind trace/span IDs alongside the existing correlation ID. Metric labels use only HTTP method, FastAPI route template, status, and bounded exception type. Tracing uses parent-based ratio sampling and exports through configurable OTLP/HTTP; the normal Compose topology does not start observability services.

**Rationale.** Logs alone do not quantify latency, traffic, saturation, or error rates, while raw paths and domain identifiers in metric labels create unbounded series and privacy risk. Standard propagation and export keep the backend replaceable and allow CarSystemUI, gateways, API, workers, and future simulators to share one trace model.

**Consequences.** `/metrics` and the local Grafana/Prometheus/Collector ports must be isolated as management-plane surfaces. The development Collector debug exporter is non-durable. Later increments added local Alertmanager and bounded dependency/storage metrics, but production still requires authenticated TLS, a trace backend, retention/access policy, accountable notification ownership/escalation, SLO calibration/evidence, capacity tests, and provider-specific saturation signals.

### ADR-017 — Reliability Policy as Code over an Authoritative Registry Aggregate

**Decision.** Keep authoritative module status in PostgreSQL and compute a constant-size health summary only for modules that have received workload credentials. Refresh bounded Prometheus status gauges from the reconciler and protected summary query. Version API availability/latency recording rules and multi-window burn-rate, latency, module-state, and lease-risk alerts in the repository; validate them with `promtool` in CI.

**Rationale.** A second health database would create consistency ambiguity, while raw module identifiers in Prometheus labels would create uncontrolled cardinality and disclosure risk. Multi-window burn rates detect both acute and persistent reliability loss with less noise than one instantaneous threshold. Policy-as-code makes review and rollback possible alongside application changes.

**Consequences.** The module ratio is a current snapshot rather than historical uptime. A later increment added local Alertmanager routing and disposable delivery tests, but production still requires accountable ownership, escalation, provider integration, threshold calibration, and retained SLO evidence. The initial 500 ms latency alert is an operational guardrail and does not replace the formal 250 ms workload target.

### ADR-018 — Process-Owned Domain Metrics with Aggregate-Only Backlog Signals

**Decision.** Keep scheduler and test-run WebSocket metrics in the API process registry. Give the independently deployed outbox worker a dedicated internal Prometheus registry and HTTP endpoint on port 9101. Measure outbox and due-job backlog through SQL count/minimum-time aggregates, expose only fixed outcome/message-kind labels, and retry a failed outbox batch after rollback without deleting or mutating unpublished evidence.

**Rationale.** Metrics must follow the process that owns the work. Exporting worker state through the API would couple independent lifecycles and hide worker failure. Individual event, job, run, vehicle, or user labels would leak operational identifiers and create unbounded cardinality. Aggregate count and oldest age directly reveal whether asynchronous work is making progress.

**Consequences.** Prometheus must scrape two internal targets. Worker metrics reset on process restart and are operational telemetry rather than authoritative evidence. Initial 60-second backlog thresholds require capacity/load calibration. RabbitMQ and Redis outages remain safe for PostgreSQL state, but production requires notification routing and explicit recovery exercises.

### ADR-019 — Local Aggregate-Only Alert Routing before External Providers

**Decision.** Route Prometheus alerts through pinned Alertmanager `v0.33.1`. Group by alert name, service, and severity; give critical alerts zero group wait; deliver firing and resolved states; and inhibit warnings while a critical alert for the same service is firing. Use only a loopback-published internal FastAPI webhook in development. Validate at most 50 alerts and reduce every notification to bounded severity/status counters without persisting its labels or annotations.

**Rationale.** Grouping, inhibition, and resolution are operational behaviors that must be tested before adding external channels. A local aggregate receiver proves end-to-end delivery without requiring email/chat credentials, contacting people, or retaining potentially sensitive alert context. Loopback host binding limits accidental exposure while Docker DNS supports internal delivery.

**Consequences.** The local receiver is not an incident-management system and its counters reset on restart. Production adapters require secret-manager integration, TLS/workload authentication, owned escalation schedules, provider retry/dead-letter monitoring, audited configuration, silence governance, and delivery exercises. Receiver payload bounds may intentionally reject oversized or malformed notification groups.

### ADR-020 — Instrument Dependencies and Storage at Existing Boundaries

**Decision.** Record readiness duration, bounded outcome, and current state for PostgreSQL, Redis, and RabbitMQ. Decorate the replaceable artifact-store protocol to record fixed operation/outcome labels, latency, bytes transferred, and optional adapter capacity. Do not expose connection URLs, object keys, filenames, exception messages, or domain identifiers. Capacity refresh failure remains diagnostic and cannot reverse a successful object operation.

**Rationale.** Readiness already performs the authoritative dependency probes, and the object-store protocol already owns evidence I/O. Instrumenting those boundaries avoids duplicate traffic and preserves the domain model. Fixed vocabularies make series count predictable, while a decorator allows filesystem, S3, MinIO, or managed adapters to share the same operational contract.

**Consequences.** Readiness traffic contributes to dependency history and must be rate-calibrated. The filesystem capacity gauge describes the backing volume visible to that adapter, not a production quota guarantee. Production still requires database-pool saturation, broker/provider internals, durable object-store quota/retention metrics, load calibration, and outage exercises.

### ADR-021 — Immutable Supply-Chain Inputs with Independent Evidence

**Decision.** Use Linux x86-64/Python 3.14 as the canonical lock platform because it matches the digest-pinned official Python 3.14.6/Alpine 3.24 runtime container; retain Python 3.12 as the tested minimum. Commit separate runtime and development dependency graphs, including build requirements, with SHA-256 hashes. Retain the canonical regenerated pair before enforcing byte-for-byte drift. Install the application without dependency re-resolution. Pin the runtime base image by manifest digest and every third-party workflow action by full commit SHA. Run history/secret, dependency, source, and image analysis in a dedicated least-privilege workflow; retain CycloneDX Python and image SBOMs; fail the image job for high or critical known vulnerabilities; and use Dependabot only to propose reviewed updates.

**Rationale.** Version ranges and mutable tags make two nominally identical builds capable of consuming different code. Immutable inputs reduce that ambiguity, while multiple scanners and machine-readable inventories provide complementary evidence at repository, package, source, and image boundaries. Separating security analysis from application integration keeps evidence and permissions explicit.

**Consequences.** Every dependency change must regenerate and review both locks. Digest and SHA pins trade automatic mutation for explicit update pull requests. Advisory databases may produce false positives or newly disclose findings in unchanged inputs, so exceptions require a documented owner, reachability assessment, compensating control, review date, and expiry. Release signing, provenance attestation, long-term SBOM retention, and managed build credentials remain production work.

## 5. Technology Stack and Rationale

| Technology | Role | Why it was selected | Engineering consideration |
|---|---|---|---|
| Python 3.12+ | Implementation language | Strong test ecosystem, rapid API development, typing support, and broad automotive tooling integration | Strict typing and linting compensate for dynamic-language risks |
| FastAPI | HTTP API framework | Async support, dependency injection, validation, and automatic OpenAPI generation | Route contracts must remain backward compatible within an API version |
| Pydantic Settings | Configuration validation | Typed environment parsing and secret-aware fields | Required configuration fails early during startup |
| PostgreSQL 17 | System of record | ACID transactions, constraints, indexing, JSON support, and mature operations | Backups, retention, and migration discipline are mandatory |
| SQLAlchemy 2 | Persistence mapping | Typed declarative mappings and async session support | Domain behavior should not become coupled to query details |
| asyncpg | PostgreSQL driver | Native asynchronous PostgreSQL access | Connection-pool sizing must be tested under deployment load |
| Alembic | Schema migration | Reproducible upgrade/downgrade history | Destructive migrations require expand-and-contract planning |
| Redis 7.4 | Ephemeral data | Low-latency atomic counters and coordination primitives | Limiter state is disposable; outage behavior and capacity must be controlled |
| RabbitMQ 4 | Event broker | Durable routing, acknowledgements, topic exchanges, and operational visibility | At-least-once delivery requires idempotent consumers and dead-letter strategy |
| aio-pika | RabbitMQ client | Async API and robust connection support | Confirmed publication and reconnect behavior require integration tests |
| PyJWT | Token implementation | Standards-based JWT encode/decode support | Algorithms must be allow-listed; claims and secrets require rotation strategy |
| pwdlib / Argon2 | Credential hashing | Modern password-hashing defaults and safe verification API | Parameters should be benchmarked and rehashed as policy evolves |
| structlog | Structured logging | Machine-readable JSON and context binding | Sensitive values must never be logged |
| OpenTelemetry | Distributed tracing | Standard W3C context, sampling, resource identity, and replaceable OTLP export | Export must be authenticated, sampled, and failure-isolated in production |
| Prometheus client | Bounded service metrics | Standard counters, gauges, histograms, and scrape format | Labels must remain low-cardinality and free of domain identifiers |
| Grafana | Versioned operational views | Provisioned dashboards and PromQL visualization | Anonymous local access is forbidden in deployed environments |
| Docker / Compose | Local topology | Repeatable development services and dependency health ordering | Production hardening requires image scanning and orchestration policies |
| pytest | Automated tests | Concise unit/integration testing and fixture ecosystem | Integration suites should use disposable infrastructure |
| Ruff | Static quality gate | Fast linting and consistent formatting | The rule set should evolve without disabling meaningful findings globally |
| mypy | Static type analysis | Detects interface and async/type errors before runtime | Strict mode is the baseline for application code |

## 6. Repository and Implementation Guide

### 6.1 Repository Structure

| Path | Purpose |
|---|---|
| `src/atep/main.py` | Application assembly, lifespan bootstrap, and correlation middleware |
| `src/atep/core/` | Settings, security primitives, rate limiting, errors, and logging configuration |
| `src/atep/db/` | SQLAlchemy base types, engine, session factory, and dependency |
| `src/atep/identity/` | Identity models, schemas, authentication, RBAC dependencies, and bootstrap logic |
| `src/atep/audit/` | Append-only administrative audit model and recording service |
| `src/atep/events/` | Outbox model, enqueue helper, and RabbitMQ publisher worker |
| `src/atep/registry/` | Persistent module registry, capability catalogue, schemas, services, and APIs |
| `src/atep/vehicles/` | Vehicle catalogue, lifecycle state, gateway authorization, and idempotent telemetry ingestion |
| `src/atep/api/health.py` | Liveness and readiness endpoints |
| `migrations/` | Alembic environment and revision history |
| `tests/` | Automated unit tests |
| `docs/` | Architecture, requirements, roadmap, and this workbook |
| `compose.yaml` | Local service topology |
| `Dockerfile` | Unprivileged runtime image for API and worker |
| `pyproject.toml` | Package metadata, dependencies, and tool configuration |

### 6.2 Configuration Contract

| Variable | Required | Default / example | Purpose |
|---|---|---|---|
| `ATEP_ENVIRONMENT` | No | `development` | Deployment environment label |
| `ATEP_DATABASE_URL` | No for local code; required operationally | PostgreSQL async URL | SQLAlchemy database connection |
| `ATEP_REDIS_URL` | No for local code; required operationally | `redis://.../0` | Redis connection |
| `ATEP_RABBITMQ_URL` | No for local code; required operationally | `amqp://.../` | Broker connection |
| `ATEP_JWT_SECRET` | Yes | No committed default | JWT signing secret, minimum 32 characters |
| `ATEP_ACCESS_TOKEN_MINUTES` | No | `30` | Access-token lifetime, constrained to 5–1440 minutes |
| `ATEP_REFRESH_TOKEN_DAYS` | No | `30` | Refresh-token lifetime, constrained to 1–365 days |
| `ATEP_RATE_LIMIT_ENABLED` | No | `true` | Enable distributed request protection; disabling requires an explicit environment decision |
| `ATEP_AUTH_RATE_LIMIT_REQUESTS` | No | `5` | Authentication attempts per normalized account in one window |
| `ATEP_AUTH_RATE_LIMIT_IP_REQUESTS` | No | `20` | Authentication attempts per direct network client in one window |
| `ATEP_AUTH_RATE_LIMIT_WINDOW_SECONDS` | No | `60` | Authentication counter lifetime |
| `ATEP_API_RATE_LIMIT_REQUESTS` | No | `300` | Requests per versioned-API credential or network client in one window |
| `ATEP_API_RATE_LIMIT_WINDOW_SECONDS` | No | `60` | Versioned-API counter lifetime |
| `ATEP_BOOTSTRAP_ADMIN_EMAIL` | No | Empty | Explicit first-administrator email |
| `ATEP_BOOTSTRAP_ADMIN_PASSWORD` | No | Empty | Explicit first-administrator password |

Bootstrap variables must either both be absent or both be supplied. The bootstrap operation is idempotent for an existing email and does not expose default credentials.

### 6.3 Authentication Flow

1. A client submits credentials to `POST /api/v1/auth/token` using the OAuth2 password form.
2. Atomic Redis counters enforce the versioned-API limit plus independent normalized-account and direct-network-client authentication limits.
3. The service normalizes the email with trim and case folding.
4. Unknown emails still trigger a dummy Argon2 verification to reduce account-enumeration timing differences.
5. The service rejects missing, inactive, or password-mismatched users using one generic response.
6. A successful request receives an access token plus an opaque refresh token; only the refresh-token hash is stored.
7. Protected endpoints decode the access token using an explicit algorithm allow-list, verify the issuer and token type, load the active user, and reject invalid principals.
8. `POST /auth/refresh` locks the stored token, marks it used, creates its replacement, and commits the rotation atomically.
9. Reuse of an older token revokes the active family; logout revokes one family and logout-all revokes every renewable session for the active user.

### 6.4 RBAC Model

Users receive roles through the `user_roles` association. Roles receive permissions through `role_permissions`. Effective permissions are the union of all permissions granted by all roles. The current permission catalogue is:

- `users:read` - inspect user information;
- `users:write` - create or modify users;
- `roles:manage` - manage role definitions and grants;
- `audit:read` - search and inspect immutable audit evidence;
- `audit:export` - export bounded audit evidence independently of search access;
- `platform:admin` - perform platform-level administration.

The `require_permissions` dependency computes missing permissions and returns HTTP 403 without revealing authorization internals. Future endpoints should declare the minimum permissions needed rather than checking role names.

### 6.5 Database Model

| Entity | Key fields | Important constraints |
|---|---|---|
| User | UUID, email, display name, password hash, active flag | Unique and indexed email |
| Role | UUID, name, description | Unique role name |
| Permission | UUID, name, description | Unique permission name |
| UserRole | user ID, role ID | Composite primary key and cascade foreign keys |
| RolePermission | role ID, permission ID | Composite primary key and cascade foreign keys |
| OutboxEvent | UUID, type, aggregate, payload, correlation ID, publication state | Indexed event type; unpublished state represented by null `published_at` |
| AuditRecord | UUID, actor, action, resource, outcome, correlation ID, safe details | PostgreSQL trigger rejects update and delete operations |
| RefreshToken | UUID, user, family, SHA-256 hash, expiry, usage/revocation state, replacement | Unique token hash; indexed user and family; cascade on user deletion |

UUID primary keys avoid coordination between future services. Timestamp columns are timezone-aware and generated by the database. Association-table constraints prevent duplicate grants.

### 6.6 Transactional Outbox Behavior

The application adds an `OutboxEvent` to the same SQLAlchemy session as the domain change. Once committed, the worker selects up to 100 unpublished events ordered by creation time and locks them using `FOR UPDATE SKIP LOCKED`. This permits multiple workers without publishing the same locked row concurrently.

Each RabbitMQ message is persistent and includes the outbox UUID as `message_id`. The envelope contains event identity, type, occurrence time, aggregate type and ID, optional correlation ID, and payload. After broker confirmation, the worker records `published_at` and increments the attempt counter.

Important limitation: robust production behavior still requires a retry/backoff policy, maximum-attempt handling, a dead-letter or quarantine process, outbox-age metrics, and a reconciliation procedure.

### 6.7 API Surface

| Method and route | Purpose | Authentication |
|---|---|---|
| `POST /api/v1/auth/token` | Authenticate and issue an access/refresh token pair | Public credential exchange |
| `POST /api/v1/auth/refresh` | Rotate a single-use refresh token and issue a replacement pair | Public possession check |
| `POST /api/v1/auth/logout` | Revoke the presented refresh-token family | Public possession check; idempotent |
| `POST /api/v1/auth/logout-all` | Revoke all renewable sessions for the active user | Bearer token |
| `GET /api/v1/auth/me` | Return the current user, roles, and permissions | Bearer token |
| `POST /api/v1/users` | Create an active user and atomically record event and audit evidence | `users:write` |
| `GET /api/v1/users` | List users with limit/offset pagination | `users:read` |
| `GET /api/v1/users/{user_id}` | Return one user without credential material | `users:read` |
| `PATCH /api/v1/users/{user_id}/status` | Activate or deactivate a user | `users:write` |
| `PUT /api/v1/users/{user_id}/roles/{role_id}` | Assign a role idempotently | `roles:manage` |
| `DELETE /api/v1/users/{user_id}/roles/{role_id}` | Remove an assigned role | `roles:manage` |
| `GET /api/v1/permissions` | List the controlled permission catalogue | `roles:manage` |
| `POST /api/v1/roles` | Create a canonical role with declared permissions | `roles:manage` |
| `GET /api/v1/roles` | List roles with bounded limit/offset pagination | `roles:manage` |
| `GET /api/v1/roles/{role_id}` | Inspect one role and its effective permissions | `roles:manage` |
| `PATCH /api/v1/roles/{role_id}` | Update a role name or description subject to protected-role rules | `roles:manage` |
| `PUT /api/v1/roles/{role_id}/permissions/{permission_name}` | Grant a declared permission idempotently | `roles:manage` |
| `DELETE /api/v1/roles/{role_id}/permissions/{permission_name}` | Revoke a permission subject to protected-role rules | `roles:manage` |
| `DELETE /api/v1/roles/{role_id}` | Delete an unused non-system role | `roles:manage` |
| `GET /api/v1/audit-records` | Search immutable evidence with bounded pagination and indexed filters | `audit:read` |
| `GET /api/v1/audit-records/export` | Export up to 10,000 matching rows as formula-safe CSV and record the export | `audit:export` |
| `GET /api/v1/audit-records/{record_id}` | Inspect one immutable audit record | `audit:read` |
| `POST /api/v1/modules` | Register a canonical module with initial versioned capabilities | `modules:manage` |
| `GET /api/v1/modules` | Discover modules using bounded status and capability filters | `modules:read` |
| `GET /api/v1/modules/{module_id}` | Inspect one module and its capability catalogue | `modules:read` |
| `PATCH /api/v1/modules/{module_id}` | Update module metadata, semantic version, endpoint, or administrative status | `modules:manage` |
| `POST /api/v1/modules/{module_id}/credentials` | Issue or rotate a raw-once module workload credential and reset the existing lease | `modules:manage` |
| `POST /api/v1/modules/{module_id}/heartbeat` | Assert `active` or `degraded`, optionally update semantic version, and renew the bounded lease | `X-ATEP-Module-Token` |
| `PUT /api/v1/modules/{module_id}/capabilities/{capability_name}` | Declare or update one versioned capability | `modules:manage` |
| `DELETE /api/v1/modules/{module_id}/capabilities/{capability_name}` | Remove one declared capability | `modules:manage` |
| `GET /health/live` | Report process liveness | Public / internal probe |
| `GET /health/ready` | Verify PostgreSQL, Redis, and RabbitMQ | Public in development; network-restricted in production |
| `GET /docs` | Interactive OpenAPI documentation | Development only or protected in production |
| `GET /openapi.json` | Machine-readable API contract | Policy-dependent |

### 6.8 Error and Observability Conventions

Authentication and authorization failures return stable machine-readable codes such as `invalid_credentials` and `permission_denied`. Readiness failures return `not_ready` with individual dependency states. Error details should remain safe for clients while logs retain diagnostic context.

Rate-limit violations return `rate_limit_exceeded` with HTTP 429, `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`. If Redis cannot evaluate the policy within two seconds, `rate_limit_unavailable` returns HTTP 503 and `Retry-After: 1`. Successful limited responses include the three `X-RateLimit-*` fields.

All application, HTTP, request-validation, and unexpected failures use `{error: {code, message, details}, correlation_id}`. Validation details include only location, message, and type; the rejected input value is deliberately omitted. Duplicate normalized email creation uses HTTP 409 with `email_already_exists`, and missing resources use stable resource-specific codes.

Every request receives a correlation UUID. A valid caller-provided UUID is retained; an invalid or absent value is replaced. The identifier is bound to structured logs and returned as `X-Correlation-ID`. Future service calls and events must propagate the same identifier.

### 6.9 Administrator User Lifecycle

1. The administrator authenticates and is reloaded as an active user for the request.
2. The endpoint enforces `users:write`, `users:read`, or `roles:manage` according to the operation.
3. Creation normalizes the email, rejects duplicates with a stable conflict, hashes the secret, and never serializes the password or hash.
4. The service flushes the user, adds `atep.identity.user.created.v1`, and appends correlated audit evidence to the same SQLAlchemy session.
5. One commit makes state, event, and audit evidence visible together; an exception before commit rolls the unit of work back.
6. Authentication reloads account state on every protected request, so deactivation invalidates access even when the presented JWT has not expired.

### 6.10 Role Catalogue Lifecycle and Invariants

1. Every catalogue endpoint reloads an active principal and requires `roles:manage`.
2. Role commands normalize names to lower-case hyphenated identifiers, deduplicate permission names, and reject unsafe or empty updates.
3. Creation resolves every permission against the controlled catalogue and returns stable conflicts for duplicate role names.
4. Permission grants are idempotent; effective grants and revocations append actor, role, permission, and correlation evidence to the audit ledger.
5. The `platform-admin` role may receive newly declared permissions during bootstrap reconciliation but cannot be renamed, stripped of permissions, or deleted through the API.
6. Deletion returns `role_in_use` while any user assignment exists, preventing silent privilege loss. An unused non-system role is deleted together with its permission associations while retaining immutable audit evidence.
7. The bootstrap process reconciles declared permissions and missing `platform-admin` grants on each startup, even when administrator creation is no longer required.

### 6.11 Audit Search, Export, and Retention

1. Search and individual inspection require `audit:read`; bulk export requires the independent `audit:export` permission.
2. Filters cover actor, exact action, resource type and ID, outcome, correlation ID, and timezone-aware inclusive date boundaries.
3. Results use deterministic newest-first ordering by `created_at` and UUID, with list pages capped at 100 rows and exports capped at 10,000 rows.
4. Migration `0004` adds indexes for chronological, actor, resource, and correlation access paths.
5. CSV output includes a UTF-8 byte-order marker for spreadsheet interoperability and neutralizes cells beginning with formula characters.
6. Export appends `audit.records.exported` after selecting the requested evidence and records only non-sensitive filters, range, and row count.
7. No API mutates or deletes audit evidence. The retention baseline requires 365 days online and seven years in a future immutable archive; legal hold overrides disposition. Until archival automation is implemented, PostgreSQL retains records indefinitely.

### 6.12 Distributed Rate Limiting

1. Every `/api/v1` route consumes an API counter; health probes remain outside this limiter so orchestrators can still observe dependency state.
2. A bearer credential is SHA-256 fingerprinted for the API key. Requests without a bearer credential use a hash of the direct network peer address.
3. Token issuance additionally consumes an account counter derived from the trimmed, case-folded email and a separate network-client counter.
4. A Lua operation performs `INCR`, first-use `PEXPIRE`, and `PTTL` retrieval atomically, so concurrent replicas share one decision and counters cannot persist indefinitely by accident.
5. Raw emails, addresses, passwords, tokens, and authorization values never appear in Redis keys.
6. Fixed windows default to five authentication attempts per account, twenty per client, and 300 versioned-API requests per minute. Typed settings bound every limit and window.
7. Excess requests fail with HTTP 429 and deterministic retry metadata. Redis errors fail closed with HTTP 503; authoritative PostgreSQL state is unchanged.
8. Production ingress must not trust arbitrary forwarding headers. A reviewed trusted-proxy policy and load-based threshold calibration remain required before internet exposure.

### 6.13 Module Registry and Capability Catalogue

1. `modules:read` permits bounded discovery and inspection; `modules:manage` independently protects every catalogue mutation.
2. Module names are canonical lower-case hyphenated identifiers. Capability names use lower-case dot-separated namespaces, and versions use semantic-version syntax.
3. Registration may include up to 100 unique initial capabilities and returns HTTP 409 with `module_name_already_exists` for a canonical duplicate.
4. Discovery pages are capped at 100 records and may filter by administrative status or exact capability name without exposing persistence details to clients.
5. PostgreSQL uniquely constrains module names and capability names within a module. Capability rows cascade only when their owning module is removed at the database layer.
6. Registration appends `atep.platform.module.registered.v1`; metadata/status changes append `atep.platform.module.updated.v1`; capability declarations, updates, and removals use their own versioned event types.
7. Every effective mutation appends correlated, non-sensitive audit evidence to the same SQLAlchemy unit of work as the catalogue state and outbox event.
8. The administrative update API cannot set `active` or `degraded`; these operational states can be asserted only by an authenticated module heartbeat.
9. Credential issuance or rotation returns a high-entropy raw token exactly once, persists only its SHA-256 digest, resets the current lease, and records a non-sensitive audit action and `atep.platform.module.credential-rotated.v1` outbox event atomically.
10. Heartbeats accept only `active` or `degraded`, may update semantic version, and renew a lease bounded to 5–3,600 seconds. Invalid credentials return stable HTTP 401 `invalid_module_credential`.
11. Routine heartbeats do not create audit or event volume. A status or version transition enqueues `atep.platform.module.availability-changed.v1` in the same transaction.
12. The periodic reconciler locks expired `active` or `degraded` rows with skip-locked semantics, marks them `inactive`, appends `platform.module.lease_expired` with a system actor, and enqueues the availability event atomically.

### 6.14 Vehicle Catalogue and Android Automotive Telemetry

1. `vehicles:read` and `vehicles:manage` protect human catalogue operations; `telemetry:read` separately protects observation retrieval.
2. Vehicle identifiers are canonical lower-case slugs such as `vehicle-001`; internal primary and relationship identifiers remain UUIDs.
3. The gateway supplies `X-ATEP-Module-ID` and the raw-once `X-ATEP-Module-Token`. The corresponding registered module must declare `vehicle.telemetry.publish`.
4. Telemetry contains a URL-safe client `event_id`, canonical property name, scalar JSON value, optional unit, timezone-aware observation timestamp, and source label.
5. New observations return HTTP 202 because downstream processing continues through the outbox. An exact retry returns HTTP 200 with `duplicate: true` and does not create another outbox event.
6. Reusing an event ID for different vehicle, module, source, property, value, unit, or timestamp returns HTTP 409 `telemetry_event_conflict`.
7. Observation persistence and `atep.vehicle.telemetry.received.v1` creation use one SQLAlchemy unit of work. RabbitMQ remains an internal integration mechanism and is never exposed to Android clients.

## 7. Software Engineering Practices Applied

### 7.1 Separation of Concerns

HTTP adapters, application/security services, persistence infrastructure, identity models, and event publication are kept in separate modules. Application assembly occurs in one composition root. This makes dependencies visible and supports targeted tests.

### 7.2 Dependency Inversion and Injection

FastAPI dependencies provide settings, sessions, authentication, and permission enforcement. Endpoint functions depend on abstractions delivered at runtime rather than creating connections directly. Future work should introduce repository and publisher protocols where domain tests need stronger isolation.

### 7.3 Secure-by-Default Design

- no committed account or JWT secret;
- minimum secret length validation;
- minimum password length at creation;
- Argon2 password hashing;
- generic authentication errors;
- algorithm allow-list and issuer/type validation;
- inactive-user rejection;
- deny-by-default permissions;
- distributed, hashed-identity rate limiting with fail-closed dependency behavior;
- unprivileged application container.

### 7.4 Database Engineering

The schema is explicit, versioned, reversible, and constrained. Naming conventions reduce migration drift. Database-generated timestamps improve consistency. Transactions define the unit of atomicity between business data and events.

### 7.5 Reliability Engineering

Readiness uses bounded dependency checks. RabbitMQ messages are persistent and publisher confirms are enabled. The worker uses row locking suitable for horizontal scaling. At-least-once semantics are documented rather than implying exactly-once delivery.

### 7.6 Twelve-Factor Alignment

Configuration is externalized, logs are emitted as event streams, processes are stateless except through backing services, the same image can run the API or worker, and local dependencies are declared explicitly. Production build/release/run separation remains a DevOps increment.

### 7.7 Quality Gates

The project configures tests, formatting and linting, strict static typing, package metadata, and deterministic database migration. A change should not merge unless unit tests, Ruff, mypy, migration checks, and contract checks pass.

### 7.8 Traceability

Requirements use stable identifiers. Tests should reference requirement IDs, and evidence should record command, environment, date, result, and artifact location. This practice prepares the project for more formal ASPICE and ISO 26262-style evidence without claiming certification.

## 8. Requirements and Traceability

### 8.1 Functional Requirements

| ID | Requirement | Implementation | Verification |
|---|---|---|---|
| CORE-F-001 | The platform shall authenticate an active user and issue a time-limited access token. | Identity service and token route | SEC-001, SEC-003, API-001, API-002 |
| CORE-F-002 | The platform shall authorize operations using role permissions. | RBAC relationships and permission dependency | RBAC-001 through RBAC-005 |
| CORE-F-003 | The platform shall persist identity and outbox state in PostgreSQL. | SQLAlchemy models and migration | DB-001 through DB-008 |
| CORE-F-004 | The platform shall publish versioned domain events to RabbitMQ. | Outbox worker and topic exchange | EVT-001 through EVT-010 |
| CORE-F-005 | The platform shall expose process liveness and dependency readiness. | Health router | API-008 through API-012 |
| CORE-F-006 | The platform shall attach a correlation ID to requests and responses. | HTTP middleware | API-013 through API-015 |
| CORE-F-007 | The platform shall create the first administrator only from explicit bootstrap configuration. | Bootstrap service and typed settings | DB-009 through DB-012 |
| CORE-F-008 | Authorized administrators shall create, list, inspect, activate, and deactivate users and manage role assignments. | User administration router and service | RBAC-003, RBAC-004, RBAC-010 through RBAC-012, API-016 |
| CORE-F-009 | Identity changes shall append immutable, correlated audit records without secrets. | Audit model/service and PostgreSQL trigger | AUD-001 through AUD-004 |
| CORE-F-010 | User creation shall persist its versioned outbox event atomically. | Identity service and transactional outbox | EVT-001, EVT-011 |
| CORE-F-011 | API failures shall follow one stable, correlation-aware envelope. | Global exception handlers | API-003, API-017 |
| CORE-F-012 | Successful authentication shall issue a short-lived access token and a longer-lived opaque refresh token. | Identity router and refresh-session service | SEC-013, SEC-014 |
| CORE-F-013 | Refresh-token use shall atomically invalidate the presented token and issue a new token pair. | Locked refresh-token rotation transaction | SEC-015 |
| CORE-F-014 | Reuse of a rotated refresh token shall revoke every active token in the same family. | Refresh-token replay detection and family revocation | SEC-016 |
| CORE-F-015 | A user shall revoke one refresh-token family or all renewable sessions. | Logout and logout-all operations | SEC-017, SEC-018 |
| CORE-F-016 | Administrators shall manage the role catalogue and permission grants through versioned APIs. | Role catalogue router, schemas, and service | RBAC-013 through RBAC-020, API-018 |
| CORE-F-017 | Protected and assigned roles shall resist unsafe mutation or deletion. | Role service invariants and stable domain errors | RBAC-016, RBAC-018, RBAC-019 |
| CORE-F-018 | Authorized investigators shall search and inspect immutable audit evidence, while separately authorized users may perform bounded audited CSV export. | Audit router, query service, CSV serializer, and migration `0004` | AUD-006 through AUD-010, API-019 |
| CORE-F-019 | The platform shall enforce distributed Redis-backed limits for authentication and versioned API requests. | Rate-limit dependency, token flow, atomic Redis script, and typed settings | RATE-001 through RATE-008, API-020 |
| CORE-F-020 | Authorized administrators shall register, inspect, page, filter, and update ATEP modules and manage their versioned capabilities. | Registry router, schemas, service, models, and migration `0005` | MOD-001 through MOD-008, API-021 |
| CORE-F-021 | Effective module-catalogue mutations shall append correlated immutable audit evidence and versioned outbox events. | Registry service, audit recorder, and transactional outbox | MOD-009, MOD-010, EVT-012 |
| CORE-F-022 | Administrators shall issue or rotate a module workload credential whose raw value is returned once and whose digest is the only persisted form. | Registry credential service and protected API | MOD-012, MOD-013 |
| CORE-F-023 | Authenticated modules shall renew bounded availability leases, and automatic reconciliation shall mark expired modules inactive. | Heartbeat API, registry service, reconciler, and migration `0006` | MOD-011 through MOD-014 |
| CORE-F-024 | Authorized administrators shall register, list, inspect, activate, and deactivate vehicle records. | Vehicle router, schemas, service, models, and migration `0007` | VEH-001 through VEH-003 |
| CORE-F-025 | A capability-authorized Vehicle Gateway shall submit timezone-aware observations only through the public API. | Module authentication and telemetry endpoint | VEH-004 through VEH-006 |
| CORE-F-026 | Observation persistence and the versioned telemetry outbox event shall be atomic. | Vehicle service and transactional outbox | VEH-007 |
| CORE-F-027 | Telemetry retries shall be idempotent and conflicting reuse of an event ID shall be rejected. | Unique constraint and payload comparison | VEH-008, VEH-009 |
| CORE-F-028 | The Android gateway shall persist changed properties before delivery and retain event identity across retry. | CarSystemUI mapper, persistent store, and gateway coordinator | VEH-011 |
| CORE-F-029 | The Android showcase shall expose safe gateway operational states without credential disclosure. | CarSystemUI gateway status card and disabled configuration behavior | VEH-013 |
| CORE-F-030 | The Android showcase shall consume canonical state through replaceable simulator and AAOS property sources. | `VehiclePropertySource`, simulator source, and AAOS source | VEH-012, VEH-014 |
| CORE-F-031 | Explicit AAOS mode shall expose inaccessible VHAL properties without substituting simulator observations. | AAOS source status and read-only provenance UI | VEH-014, `CT-SHOW-007` |
| CORE-F-032 | Pending Android telemetry shall reconcile to one persistent, connectivity-constrained, bounded background job per vehicle. | WorkManager scheduler, retry worker, and persistent gateway store | VEH-015, `CT-SHOW-008` |
| CORE-F-033 | Rejected telemetry and exhausted background work shall remain inspectable and require an explicit, item-scoped retry or discard decision. | Persistent rejected-event model, queue observer, gateway operations, and Compose evidence card | VEH-016, `CT-SHOW-009` |
| CORE-F-034 | An operator with `vehicle_commands:write` shall idempotently request a bounded `set_property` command for one vehicle and one capability-authorized target module. | Command API, stable conflict, audit, and requested event | VEH-017 through VEH-019 |
| CORE-F-035 | A module declaring `vehicle.commands.consume` shall atomically claim one available command under a bounded lease and acknowledge it with a hash-only claim token. | Locked claim query, attempt/lease state, digest verification, and completion event | VEH-020 through VEH-022 |
| CORE-F-036 | The Android gateway shall execute only allowlisted simulator properties, reject invalid or unsafe transitions, and refuse mutation of a read-only AAOS source. | Android executor, coordinator, terminal acknowledgement, and event history | VEH-023, `CT-SHOW-010` |
| CORE-F-037 | Authorized operators shall idempotently create and query bounded vehicle-scoped test runs. | Test-run router, service, model, schemas, and migration `0009` | VEH-024, VEH-025 |
| CORE-F-038 | Test-run creation and effective transitions shall atomically append audit and outbox evidence. | SQLAlchemy unit of work, audit service, and transactional outbox | VEH-026 |
| CORE-F-039 | Test runs shall enforce reviewed transitions and expected-version concurrency. | Row lock, transition map, stable version/state conflicts | VEH-027, VEH-028 |
| CORE-F-040 | Authorized active users shall receive a snapshot and live versioned test-run updates over WebSocket. | Bearer revalidation, Redis Pub/Sub, snapshot/update envelope | VEH-029 |
| CORE-F-041 | CarSystemUI shall display and safely reconcile live test-run state. | OkHttp client, version reducer, reconnect policy, and Compose card | VEH-030 |
| CORE-F-042 | Authorized operators shall idempotently create and independently discover bounded environment profiles. | Profile router, schemas, service, model, and RBAC permissions | ENV-001, ENV-002 |
| CORE-F-043 | Environment profiles shall enforce immutable draft-to-active-to-archived lifecycle transitions and expected versions. | Locked status route, transition map, and stable conflicts | ENV-003, ENV-004 |
| CORE-F-044 | Profile creation and effective transitions shall atomically append audit and outbox evidence. | SQLAlchemy unit of work, audit service, and transactional outbox | ENV-005 |
| CORE-F-045 | Profile-backed TestRuns shall use only active profiles and preserve their reproducibility snapshot. | Active-profile resolver and TestRun snapshot columns | ENV-006 |
| CORE-F-046 | Authorized operators shall idempotently schedule timezone-aware vehicle-scoped test jobs and independently discover them. | Test-job router, schema, service, model, and RBAC | JOB-001, JOB-002 |
| CORE-F-047 | Scheduled jobs shall support optimistic, idempotent pre-dispatch cancellation and reject terminal changes. | Locked cancellation route and stable state/version conflicts | JOB-003, JOB-004 |
| CORE-F-048 | Scheduler replicas shall claim bounded due work without duplicate dispatch and atomically create one queued TestRun. | Oldest-first `FOR UPDATE SKIP LOCKED` selection and shared transaction | JOB-005, JOB-006 |
| CORE-F-049 | Effective job lifecycle changes shall append immutable audit and versioned outbox evidence atomically. | Audit recorder, transactional outbox, and scheduler unit of work | JOB-002, JOB-006 |
| CORE-F-050 | Authorized operators shall upload bounded immutable evidence to an existing TestRun and independently retrieve metadata/content. | Artifact router, object-store boundary, model, and RBAC | ART-001, ART-005 |
| CORE-F-051 | Exact artifact retries shall be idempotent and changed reuse of an identifier shall fail stably. | SHA-256/metadata comparison and scoped uniqueness | ART-002 |
| CORE-F-052 | Stored artifact metadata shall atomically append audit and outbox evidence after object creation. | SQLAlchemy unit of work and best-effort object rollback | ART-003, ART-007 |
| CORE-F-053 | Downloads shall retain safe filename/media metadata and expose integrity without leaking object keys. | Protected streaming response, ETag, SHA-256 header, and response schema | ART-004, ART-006 |
| CORE-F-054 | Enabled deployments shall expose bounded Prometheus HTTP, process, and build metrics. | Dedicated registry, middleware, and internal scrape endpoint | OBS-006, OBS-009 |
| CORE-F-055 | HTTP tracing shall honor W3C parents and return the effective trace ID. | OpenTelemetry server span and propagation middleware | OBS-007 |
| CORE-F-056 | Logs, spans, and responses shall share safe correlation, trace, and span identifiers. | Structlog context binding and span attributes | OBS-002, OBS-003, OBS-007 |
| CORE-F-057 | Trace recording, sampling, service identity, and OTLP/HTTP export shall be environment-configured. | Typed settings, parent-based sampler, and batch exporter | OBS-008 |
| CORE-F-058 | A pinned optional Collector/Prometheus/Grafana topology and dashboard shall be versioned and validated. | Compose overlay, provisioning, dashboard JSON, and CI config gate | OBS-009, OBS-010 |
| CORE-F-059 | Authorized operators shall retrieve a constant-size aggregate health summary for credentialed modules. | Registry aggregate, `modules:read`, and response schema | OBS-011 |
| CORE-F-060 | Registry monitoring shall expose bounded heartbeat, state, availability, lease, expiry, and reconciliation metrics. | Reconciler and dedicated Prometheus registry | OBS-012 |
| CORE-F-061 | API availability/error and latency SLIs shall be versioned as Prometheus recording rules. | `deploy/observability/alerts.yml` | OBS-013 |
| CORE-F-062 | Error-budget, latency, module-state, and lease-risk alerts shall have severity, persistence, and runbook metadata. | Versioned alert rules and runbook | OBS-013, OBS-014 |
| CORE-F-063 | The outbox worker shall expose bounded publication, duration, backlog-age, process, and worker metrics on an internal endpoint. | Dedicated registry and worker HTTP server | OBS-015, OBS-018 |
| CORE-F-064 | The scheduler shall expose dispatch, failure, duration, due-count, and oldest-due-age metrics. | Scheduler aggregate and API registry | OBS-016 |
| CORE-F-065 | Test-run live delivery shall expose bounded connection, message-kind, and Redis publication metrics. | WebSocket/Redis instrumentation | OBS-017, OBS-018 |
| CORE-F-066 | Missing workers, old asynchronous backlog, and domain processing failures shall raise runbook-linked alerts. | Six Prometheus domain alerts | OBS-019 |
| CORE-F-067 | Prometheus shall deliver firing and resolved alerts to pinned Alertmanager with reviewed grouping intervals. | Prometheus/Compose configuration and CI delivery | OBS-020, OBS-023 |
| CORE-F-068 | Critical alerts shall inhibit warnings for the same service and both reviewed severities shall route internally. | Alertmanager route/inhibition policy | OBS-021 |
| CORE-F-069 | The local webhook shall validate bounded payloads and expose only aggregate delivery evidence. | Receiver schemas, metrics, and no-retention implementation | OBS-022 through OBS-024 |
| CORE-F-070 | Readiness shall publish bounded PostgreSQL, Redis, and RabbitMQ duration/result/current-state metrics. | Health boundary and API Prometheus registry | OBS-025, OBS-027 |
| CORE-F-071 | The replaceable artifact-store boundary shall publish operation, latency, byte, and optional capacity metrics without identifiers. | Instrumentation decorator and filesystem capacity provider | OBS-026, OBS-027 |
| CORE-F-072 | Dependency unavailability, artifact-store errors, and low capacity shall raise runbook-linked alerts. | Three Prometheus alert rules | OBS-028 |
| CORE-F-073 | Runtime and development dependency graphs, including build requirements, shall be committed with SHA-256 hashes. | `requirements.lock`, `requirements-dev.lock`, and lock drift gate | SECOPS-009 |
| CORE-F-074 | Security CI shall scan history, Python dependencies, Python source, and the built image and retain CycloneDX SBOM evidence. | `.github/workflows/security.yml` | SECOPS-001 through SECOPS-004 |
| CORE-F-075 | CI actions and the runtime base image shall use immutable identifiers with reviewed automated update proposals. | workflow/Docker policy and Dependabot | SECOPS-009 |

### 8.2 Non-Functional Requirements

| ID | Requirement | Target / rule | Verification |
|---|---|---|---|
| CORE-NF-001 | Availability | 99.9% after production deployment | OPS-008, operational SLO evidence |
| CORE-NF-002 | API latency | p95 below 250 ms excluding long-running test operations | PERF-001 through PERF-003 |
| CORE-NF-003 | Event delivery | At least once with retry and idempotent consumers | EVT-005 through EVT-010 |
| CORE-NF-004 | Security | Argon2 credentials, least privilege, and no committed secrets | SEC suite and SECOPS suite |
| CORE-NF-005 | Observability | Structured logs and end-to-end correlation IDs | API-013 through API-015, OBS-001 through OBS-005 |
| CORE-NF-006 | Maintainability | Typed modules and automated quality gates | QLT-001 through QLT-008 |
| CORE-NF-007 | Data protection | No credentials or hashes in responses, events, audit details, or logs | SEC-001, SEC-012, RBAC-011 |
| CORE-NF-010 | Role-catalogue integrity | Canonical names, bounded pages, auditable changes, and enforced system-role invariants | RBAC-013 through RBAC-020, AUD-005 |
| CORE-NF-011 | Audit evidence lifecycle | Immutable records, 365-day online minimum, seven-year archive minimum, legal-hold override, and no public disposition path | AUD-004, AUD-006 through AUD-010, retention-policy review |
| CORE-NF-012 | Abuse-control consistency | Atomic expiring counters, hashed limiter identities, stable retry metadata, and fail-closed Redis behavior | RATE-001 through RATE-008 |
| CORE-NF-013 | Module-catalogue integrity | Canonical scoped names, semantic versions, bounded pages, independent read/manage permissions, and database uniqueness | MOD-001 through MOD-010 |
| CORE-NF-014 | Operational-registry integrity | Hash-only workload credentials, heartbeat-controlled operational states, bounded leases, and atomic expiry evidence | MOD-011 through MOD-014 |
| CORE-NF-015 | Automotive integration isolation | CarSystemUI and the gateway access only public ATEP APIs; infrastructure services remain private | VEH-004, architecture review |
| CORE-NF-016 | Telemetry interoperability | Canonical property/event identifiers, timezone-aware timestamps, OpenAPI contracts, and idempotent retry behavior | VEH-005 through VEH-010 |
| CORE-NF-017 | Gateway resilience | Store-before-send queue, stable retry identity, bounded permanent-rejection storage, and no delivery without configured credentials | VEH-011, VEH-013 |
| CORE-NF-018 | Evidence provenance | Visible source identity, read-only AAOS mode, no silent fallback, and canonical unit conversion | VEH-012, VEH-014 |
| CORE-NF-019 | Background delivery control | Unique work per vehicle, network constraint, queue-order retention, disabled-mode suppression, exponential backoff, and eight-attempt bound | VEH-015, `CT-SHOW-008` |
| CORE-NF-020 | Telemetry disposition safety | No silent restart after exhaustion, unchanged identity on retry, item-scoped discard, persistent evidence, and no credential display | VEH-016, `CT-SHOW-009` |
| CORE-NF-021 | Command-delivery safety | Target scope, capability check, atomic claim, bounded lease, hash-only token, idempotent terminal state, allowlist, and vehicle-state invariants | VEH-017 through VEH-023, `CT-SHOW-010` |
| CORE-NF-022 | Live test-run consistency | PostgreSQL/outbox authority, row-locked optimistic transitions, best-effort Redis projection, authenticated subscription, monotonic client deduplication | VEH-024 through VEH-030 |
| CORE-NF-023 | Test reproducibility | Immutable profile identity, 16 KiB JSON bound, active-only use, and versioned TestRun snapshot independent of archival | ENV-001 through ENV-006 |
| CORE-NF-024 | Scheduler consistency | Bounded oldest-first batches, row ownership with `SKIP LOCKED`, and atomic job/run/evidence state | JOB-005, JOB-006 |
| CORE-NF-025 | Artifact integrity | Configurable size bound, streaming SHA-256, immutable identifiers, and verified download metadata | ART-001 through ART-004 |
| CORE-NF-026 | Storage isolation | Generated object keys, root-escape rejection, no public key disclosure, and independent RBAC | ART-004 through ART-006 |
| CORE-NF-027 | Metric cardinality | Route templates and bounded protocol labels; no raw paths, domain IDs, email, filename, query, body, or credential labels | OBS-006 |
| CORE-NF-028 | Observability isolation | Metrics, dashboards, scrape and OTLP surfaces remain on authenticated internal management networks | Architecture/security review and OBS-009 |
| CORE-NF-029 | Telemetry overhead | Disabled/non-recording mode, parent-based ratio sampling, batch export, Collector memory bound, and no business-state dependency | OBS-008, performance hardening |
| CORE-NF-030 | SLO policy as code | 99.9% API availability target, configurable module snapshot target, and versioned CI-validated rules | OBS-013 |
| CORE-NF-031 | Alert safety | Bounded labels, reviewed severity/persistence, runbook metadata, and no credentials or domain identifiers | OBS-012 through OBS-014 |
| CORE-NF-032 | Health aggregation | Constant-size PostgreSQL aggregate limited to credentialed modules | OBS-011 |
| CORE-NF-033 | Domain metric cardinality | Fixed outcomes/message kinds or no labels; no event, run, user, vehicle, or job identifiers | OBS-015 through OBS-017 |
| CORE-NF-034 | Worker telemetry isolation | Dedicated internal registry/port with no dependency from transaction success to metric delivery | OBS-015, architecture review |
| CORE-NF-035 | Backlog measurement | Constant-size count/minimum-time queries without loading or labelling records | OBS-015, OBS-016 |
| CORE-NF-036 | Alert delivery isolation | Loopback host ports, internal Docker destination, and no external provider or credential | OBS-020, architecture review |
| CORE-NF-037 | Notification cardinality | Fixed severity/status labels; arbitrary values map to `unknown` | OBS-022 |
| CORE-NF-038 | Alert lifecycle | Firing/resolved delivery, bounded repeat/group intervals, and same-service inhibition | OBS-021, OBS-023 |
| CORE-NF-039 | Dependency metric cardinality | Three fixed dependency labels and two fixed outcomes | OBS-025 |
| CORE-NF-040 | Storage metric privacy | Fixed operation/outcome/direction values; no object or domain identifiers | OBS-026 |
| CORE-NF-041 | Observability non-interference | Capacity refresh and metric recording cannot alter storage or readiness semantics | OBS-026, architecture review |
| CORE-NF-042 | Build reproducibility | Canonical Linux x86-64/Python 3.14 locks, tested Python 3.12 minimum, hash verification, and no dependency re-resolution from reviewed manifests | SECOPS-002, SECOPS-009 |
| CORE-NF-043 | CI least privilege | Read-only default permissions, job-scoped CodeQL publication permission, and full-SHA actions | SECOPS-003, SECOPS-009 |
| CORE-NF-044 | Vulnerability evidence | Fourteen-day SBOM retention and a high/critical image gate with reviewed exceptions only | SECOPS-002, SECOPS-004 |

### 8.3 Definition of Done for an Increment

- requirements and acceptance criteria are updated;
- architecture decisions with lasting impact are recorded;
- implementation contains no committed credentials;
- migrations support a fresh database and an upgrade path;
- automated tests cover new behavior and relevant failure paths;
- Ruff and strict mypy pass;
- OpenAPI changes are reviewed for compatibility;
- logs and error responses contain no sensitive data;
- operational procedures and rollback considerations are documented;
- the workbook records verification evidence, risks, and remaining limitations.

## 9. Verification Record — Increments 1 through 3

### 9.1 Executed Checks

| Check | Result | Evidence summary |
|---|---|---|
| Python syntax compilation | Passed | Application, tests, and migrations compiled successfully |
| Unit and API contract suite | Passed | 50 tests passed |
| Ruff lint | Passed | No findings after corrections |
| mypy strict analysis | Passed | Strict analysis passed for application and test modules |
| Alembic migration chain | Passed | Revisions `0001` through `0009` applied successfully to a clean PostgreSQL database in the disposable Docker topology |
| Project metadata | Passed | `pyproject.toml` parsed successfully |
| Compose syntax | Passed | YAML loaded successfully |
| Application contract load | Passed | Authentication, health, identity, audit, registry, vehicle, telemetry, command request/claim/acknowledgement, bounded pagination, and gateway headers are present in OpenAPI |
| Docker Compose startup | Passed | PostgreSQL, Redis, and RabbitMQ became healthy; migration exited `0`; API and outbox worker remained active |
| API health integration | Passed | `/health/live` returned `alive` and `/health/ready` returned `ready` against the container stack |
| Administration end-to-end flow | Passed | Create/list, duplicate conflict, role assignment/removal, RBAC revocation, and account deactivation were exercised through HTTP |
| Event and audit integration | Passed | The user-created outbox row was committed and published; five expected audit records were persisted for the exercised workflow |
| Disposable integration runner | Passed | A fresh isolated stack used generated credentials and was removed with all volumes after the test |
| Automated black-box integration | Passed | One pytest scenario verified API, PostgreSQL, RabbitMQ, RBAC revocation, inactive-user rejection, outbox publication, and audit immutability |
| Refresh-session integration | Passed | The disposable scenario verified issuance, hash-only storage, rotation, old-token reuse detection, family revocation, logout, and logout-all |
| Role-catalogue integration | Passed | The disposable scenario used only APIs to create, discover, update, assign, authorize, detach, and delete a role; protected-role, duplicate, in-use, RBAC, and audit behavior were verified |
| Audit query/export integration | Passed | The disposable scenario verified permission denial, indexed resource filtering, deterministic newest-first ordering, individual inspection, bounded CSV export, and export-compatible response headers |
| Redis rate-limit integration | Passed | The disposable scenario verified successful quota headers and HTTP 429 with `Retry-After` after the sixth same-account login attempt |
| Module-registry integration | Passed | The disposable scenario verified migration `0005`, registration, duplicate conflict, capability filter, status/version update, capability declaration/removal, negative RBAC, four audit actions, and four outbox events |
| Operational-registry integration | Passed | The disposable scenario verified migration `0006`, raw-once credential issuance, hash-only storage, invalid and valid heartbeat, lease renewal, background expiry, system audit, and availability outbox events |
| Vehicle-gateway integration | Passed | The disposable scenario verified migration `0007`, vehicle registration/status, workload capability authorization, accepted telemetry, exact retry deduplication, conflicting retry rejection, bounded query, PostgreSQL state, audit, and outbox atomicity |
| Vehicle-command integration | Passed | Disposable HTTP/PostgreSQL execution verified idempotent request/conflict, target capability, hash-only claim token, bounded lease, attempt count, authenticated terminal acknowledgement, duplicate acknowledgement, list query, and three outbox transitions; the current Python suite contains 60 tests |
| Test-run live integration | Passed | Disposable HTTP/PostgreSQL/Redis execution verified migration `0009`, RBAC catalogue, idempotent creation/conflict, authenticated snapshot, live running/passed updates, exact retry, stale-version conflict, illegal terminal transition, bounded filtering, audit, and outbox publication |
| Environment-profile focused verification | Passed | Four service/schema tests verified bounded validation, idempotent creation/conflict, audit/outbox evidence, version/state conflicts, and the immutable TestRun configuration snapshot; the full 64-test suite peaked at 163.9 MiB Python working memory |
| Android Vehicle Gateway build | Passed | CarSystemUI `showcase` produced a debug APK with the ATEP transport, persistent queue, status UI, and debug-only cleartext emulator policy |
| Android Vehicle Gateway and property-source unit suite | Passed | Nine tests verified gateway mapping/delivery plus simulator mutation, AAOS conversion, battery percentage, and unavailable-VHAL behavior |
| Android AAOS source build and lint | Passed | The standalone APK compiled its runtime CarPropertyManager compatibility bridge, required permission declarations, source provenance UI, and read-only AAOS mode without lint findings |
| Android WorkManager retry build and tests | Passed | WorkManager `2.11.2` resolved; scheduler, worker, unique-work policy, connectivity constraint, exponential backoff, eight-attempt bound, disabled-mode suppression, and six policy tests compiled and passed |
| Android rejected-event and exhaustion build and tests | Passed | Persistent inspection, atomic requeue, selective discard, attempt/exhaustion state, queue observation, explicit recovery, and five focused tests compiled and passed |
| Android vehicle-command build and tests | Passed | REST claim/acknowledgement transport, property allowlist, type/range checks, safety invariants, read-only AAOS rejection, and acknowledgement deferral compiled and six focused tests passed within the 24-test Android suite |
| Live Android vehicle-command scenario `CT-SHOW-010` | Passed | A headless Android Automotive API 35 emulator connected to an isolated ATEP stack. Exact retry remained idempotent, changed retry returned `vehicle_command_conflict`, valid values succeeded, out-of-range and unsafe values were rejected, a capability-less module received HTTP 403, an expired lease recovered on attempt two, and explicit AAOS mode returned `read_only_vehicle_source`. The run retained 25 telemetry observations, seven requested events, eight claimed events, seven completed events, and hash-only claim-token evidence. |
| Android lint | Passed with warnings | `lintDebug` completed with zero errors and 14 non-blocking warnings covering the AAOS reflection bridge, KTX suggestions, dependency updates, target level, backup rules, and application icon |
| GitHub Actions workflow | Defined, not remotely executed | Fast gates and disposable integration execution are configured for pull requests and `main` pushes |

### 9.2 Existing Automated Tests

| Test | Objective | Result |
|---|---|---|
| Password hash and verification | Confirm plaintext is not stored and valid/invalid comparisons behave correctly | Passed |
| Short-password rejection | Confirm passwords below the 12-character policy are rejected | Passed |
| Bootstrap-email validation | Reject non-deliverable bootstrap addresses such as reserved `.local` domains before startup | Passed |
| Access-token round trip | Confirm a generated token resolves to the original user UUID | Passed |
| Tampered-token rejection | Confirm signature changes invalidate the token | Passed |
| Email normalization | Confirm whitespace and case do not create duplicate identities | Passed |
| Administrator permission catalogue | Confirm the administrator set contains every declared permission | Passed |
| Global application-error contract | Confirm domain failures produce a stable code/message/details/correlation envelope | Passed |
| Global validation-error contract | Confirm invalid input is mapped without echoing sensitive input | Passed |
| User creation security and evidence | Confirm normalized email, password hashing, safe response, outbox event, and audit record | Passed |
| Duplicate-email behavior | Confirm a stable `email_already_exists` conflict and no pending writes | Passed |
| RBAC denial | Confirm a missing permission produces HTTP 403 and `permission_denied` | Passed |
| RBAC allowance | Confirm the exact required permission authorizes the operation | Passed |
| Immediate account deactivation | Confirm a valid unexpired token cannot authenticate an inactive user | Passed |
| Status-change audit | Confirm account state changes immediately and actor/change details are recorded | Passed |
| Role-assignment audit | Confirm effective assignment and removal update membership and append the corresponding audit actions | Passed |
| Pagination contract | Confirm safe defaults and upper/lower limits are published in OpenAPI | Passed |
| Refresh-token hashing | Confirm tokens are high entropy and deterministic only through their SHA-256 digest | Passed |
| Refresh API contracts | Confirm refresh, logout, and logout-all paths plus token-pair fields are present in OpenAPI | Passed |
| Refresh-session lifecycle | Confirm real-database rotation, replay-family revocation, logout, global logout, safe persistence, and auditing | Passed |
| Disposable identity integration | Confirm migrations, bootstrap, HTTP contracts, persistence, broker publication, immediate authorization changes, and immutable audit against fresh infrastructure | Passed |
| Role command normalization | Confirm canonical role names, trimmed descriptions, deduplicated permissions, and unsafe-name rejection | Passed |
| Protected platform role | Confirm `platform-admin` cannot be renamed, stripped of a permission, or deleted | Passed |
| Role catalogue API contract | Confirm catalogue paths and bounded pagination are published in OpenAPI | Passed |
| Role catalogue end-to-end | Confirm API-only creation, duplicate conflict, update, permission grant/revoke, assignment, positive/negative authorization, in-use conflict, deletion, and audit evidence | Passed |
| Audit search validation | Confirm timezone-aware ordered date ranges and trimmed bounded text filters | Passed |
| Audit CSV security | Confirm stable headers, UTF-8 spreadsheet compatibility, deterministic JSON details, and formula neutralization | Passed |
| Audit API contract | Confirm search, export, and detail paths plus safe page/export limits in OpenAPI | Passed |
| Audit query/export end-to-end | Confirm negative RBAC, resource filtering, newest-first order, detail retrieval, CSV output, validation errors, and export evidence against PostgreSQL | Passed |
| Atomic rate-limit counter | Confirm one Redis operation increments, sets first-use expiry, and returns remaining lifetime without a race window | Passed |
| Rate-limit rejection metadata | Confirm excess traffic raises the stable HTTP 429 error contract with limit, remaining, reset, and retry fields | Passed |
| Rate-limit dependency failure | Confirm Redis failure returns controlled HTTP 503 rather than silently bypassing protection | Passed |
| Authentication rate limit end-to-end | Confirm five invalid attempts retain the generic credential response and the sixth receives HTTP 429 from the disposable Redis stack | Passed |
| Module command validation | Confirm canonical module/capability names, semantic versions, trimmed text, and duplicate capability rejection | Passed |
| Module registration atomicity | Confirm registration stages one module, initial capabilities, one audit record, and `atep.platform.module.registered.v1` in one unit of work | Passed |
| Capability catalogue lifecycle | Confirm declaration and removal update the module and append the corresponding audit and outbox evidence | Passed |
| Module registry RBAC and API contract | Confirm independent read/manage denial and bounded discovery contracts in OpenAPI | Passed |
| HTTP metric cardinality | Confirm concrete resource identifiers never appear in labels and route templates remain bounded | Passed |
| W3C trace propagation | Confirm valid parent trace/span linkage and `X-Trace-ID` response correlation | Passed |
| Exception observability | Confirm an unhandled exception increments its counter and marks the server span as error | Passed |
| Observability assets | Confirm dashboard JSON, PromQL signals, internal targets, and Collector memory limiter are versioned | Passed |
| Optional topology validation | Confirm the merged Compose model is valid without starting or pulling observability containers | Passed with a non-blocking local Docker-config access warning |

### 9.3 Evidence Limitations

The fast local suite and repeated remote disposable CI runs prove clean-database repeatability and the happy-path interaction among PostgreSQL, Redis, RabbitMQ, migrations, API, publisher worker, metrics scrape, artifact storage, and trace propagation. The optional Prometheus/Grafana/Collector images were configuration-validated but deliberately not started on the resource-constrained workstation. Live dashboard inspection, durable trace storage, telemetry failure injection, sustained load/cardinality, broker/database outage recovery, multi-replica concurrency, production availability, SLOs, security certification, and safety compliance remain unproven.

## 10. Test Strategy

### 10.1 Test Levels

| Level | Purpose | Typical execution |
|---|---|---|
| Unit | Verify deterministic rules without external services | Every commit |
| Component | Verify API or worker behavior with controlled adapters | Every pull request |
| Integration | Verify real PostgreSQL, Redis, or RabbitMQ behavior | Pull request and nightly |
| Contract | Detect breaking API or event changes | Pull request and release |
| End-to-end | Verify the deployed multi-process platform | Release candidate |
| Performance | Establish latency, throughput, and saturation limits | Scheduled and before release |
| Resilience | Verify recovery under dependency and process failures | Scheduled chaos exercises |
| Security | Detect design, implementation, dependency, and configuration weaknesses | Every pull request plus periodic assessment |

### 10.2 Test Environment Principles

- use disposable databases and broker namespaces;
- create data through supported interfaces or explicit fixtures;
- make tests independent and safe to repeat;
- control time for token-expiry, rate-window, and retry tests;
- avoid relying on test order;
- collect logs, metrics, request IDs, broker messages, and database state as evidence;
- clean up resources even after failures;
- tag slow, integration, performance, and destructive tests explicitly.

## 11. Detailed Test Catalogue

### 11.1 Authentication and Token Security

| ID | Test and objective | Expected result | Status / priority |
|---|---|---|---|
| SEC-001 | Verify password hashing and comparison to ensure plaintext is never retained. | Hash differs from plaintext; correct password passes and incorrect password fails. | Implemented / P0 |
| SEC-002 | Reject passwords shorter than policy to enforce the minimum credential baseline. | Creation helper raises a controlled validation error. | Implemented / P0 |
| SEC-003 | Round-trip a valid access token to validate subject and signing configuration. | Decoded UUID equals the issuing user UUID. | Implemented / P0 |
| SEC-004 | Modify a signed token to verify tamper detection. | Token is rejected as invalid. | Implemented / P0 |
| SEC-005 | Decode an expired token to validate time-based enforcement. | Token is rejected with no principal created. | Planned / P0 |
| SEC-006 | Present a token signed with another secret to verify trust-boundary isolation. | Token is rejected. | Planned / P0 |
| SEC-007 | Present a token using an unapproved algorithm to prevent algorithm confusion. | Token is rejected before user lookup. | Planned / P0 |
| SEC-008 | Present a token with the wrong issuer or token type to verify claim validation. | Token is rejected. | Planned / P0 |
| SEC-009 | Present malformed or missing `sub` claims to verify defensive parsing. | Token is rejected with the stable authentication error. | Planned / P0 |
| SEC-010 | Authenticate an inactive user to verify account-state enforcement. | Generic invalid-credentials response; no token issued. | Planned / P0 |
| SEC-011 | Compare known- and unknown-email authentication timing to reduce enumeration risk. | Timing distributions show no practically exploitable difference within an agreed threshold. | Planned / P1 |
| SEC-012 | Inspect logs from successful and failed authentication to prevent secret leakage. | No password, JWT secret, token, or password hash appears in logs. | Planned / P0 |
| SEC-013 | Issue a token pair after successful authentication. | Response contains a short-lived access token and a higher-entropy, longer-lived opaque refresh token. | Implemented integration evidence / P0 |
| SEC-014 | Inspect refresh-token persistence. | Only the 64-character SHA-256 digest is stored; raw token material is absent. | Implemented unit/integration evidence / P0 |
| SEC-015 | Rotate a valid refresh token. | Presented token becomes used and a replacement token pair is committed atomically. | Implemented integration evidence / P0 |
| SEC-016 | Reuse an already rotated token. | Replay is rejected and every active replacement in the token family is revoked. | Implemented integration evidence / P0 |
| SEC-017 | Log out with a refresh token. | The token family can no longer renew, and no raw token is written to audit data. | Implemented integration evidence / P0 |
| SEC-018 | Log out all sessions for an authenticated user. | Every renewable token is revoked while existing access tokens retain their bounded lifetime. | Implemented integration evidence / P0 |

### 11.2 RBAC and Identity

| ID | Test and objective | Expected result | Status / priority |
|---|---|---|---|
| RBAC-001 | Normalize email before lookup to prevent case/whitespace duplicate identities. | Canonical lower-case trimmed identity is used. | Implemented / P0 |
| RBAC-002 | Verify the administrator permission catalogue is complete. | Administrator set equals the declared permission enumeration. | Implemented / P0 |
| RBAC-003 | Access an operation with the exact required permission. | Authorization dependency returns the principal. | Implemented / P0 |
| RBAC-004 | Access an operation while missing its required permission. | HTTP 403 with `permission_denied`; no operation occurs. | Implemented / P0 |
| RBAC-005 | Combine permissions from multiple roles to validate effective-permission union. | User receives the union without duplicate entries. | Planned / P1 |
| RBAC-006 | Assign the same role twice to verify database uniqueness. | Second association is rejected by the composite key. | Planned / P1 |
| RBAC-007 | Delete a role and verify association cleanup. | Association rows cascade; users remain intact. | Planned / P1 |
| RBAC-008 | Request `/auth/me` for an active user. | Response contains the correct user, sorted role names, and sorted permissions. | Planned / P0 |
| RBAC-009 | Request `/auth/me` without credentials. | HTTP 401 with `WWW-Authenticate: Bearer`. | Planned / P0 |
| RBAC-010 | Disable a user after token issue to verify live account-state checks. | Previously issued token no longer grants access. | Implemented / P0 |
| RBAC-011 | Create a user and inspect response, event, and audit data for secret leakage. | Password and hash are absent; one event and one correlated audit record are added. | Implemented / P0 |
| RBAC-012 | Create a canonical duplicate email. | HTTP/domain conflict uses stable `email_already_exists`; no write is staged. | Implemented / P0 |
| RBAC-013 | Create a canonical role with declared permissions. | HTTP 201 returns the role and its sorted effective permission names. | Implemented unit/integration evidence / P0 |
| RBAC-014 | Create a duplicate canonical role name. | HTTP 409 returns stable `role_name_already_exists`. | Implemented integration evidence / P0 |
| RBAC-015 | List and inspect roles and permissions. | Bounded, ordered role pages and the controlled permission catalogue are returned without database access by the client. | Implemented contract/integration evidence / P0 |
| RBAC-016 | Rename, revoke from, or delete `platform-admin`. | HTTP 409 returns `protected_role`; the invariant remains intact. | Implemented unit/integration evidence / P0 |
| RBAC-017 | Grant and revoke a role permission. | Effective permission state changes immediately and each change is audited. | Implemented integration evidence / P0 |
| RBAC-018 | Delete a role assigned to a user. | HTTP 409 returns `role_in_use`; no association or role is removed. | Implemented integration evidence / P0 |
| RBAC-019 | Delete an unused non-system role. | HTTP 204 removes the role and its permission associations while preserving audit evidence. | Implemented integration evidence / P0 |
| RBAC-020 | Page roles beyond accepted limits. | Validation rejects unsafe bounds using the global error contract. | Implemented OpenAPI contract evidence / P0 |

### 11.3 API and Middleware

| ID | Test and objective | Expected result | Status / priority |
|---|---|---|---|
| API-001 | Authenticate with valid credentials. | HTTP 200 with bearer token and configured expiry. | Planned / P0 |
| API-002 | Authenticate with invalid email or password. | HTTP 401 with one generic error contract. | Planned / P0 |
| API-003 | Submit missing or malformed JSON fields. | HTTP 422 with a stable validation response that omits raw input. | Implemented / P1 |
| API-004 | Verify OpenAPI contains all intended routes and security schemes. | Contract contains authentication, health, and user-administration operations. | Executed / P0 |
| API-005 | Snapshot the OpenAPI schema to detect accidental breaking changes. | Review fails when an unapproved incompatible change is introduced. | Planned / P1 |
| API-006 | Send an unsupported method to a route. | HTTP 405 without internal details. | Planned / P2 |
| API-007 | Send malformed JSON or oversized input once JSON endpoints exist. | Controlled 4xx response; process remains healthy. | Planned / P1 |
| API-008 | Call liveness while the process is healthy. | HTTP 200 with `status=alive`, independent of backing services. | Planned / P0 |
| API-009 | Call readiness with all dependencies healthy. | HTTP 200 with every dependency marked ready. | Planned / P0 |
| API-010 | Make PostgreSQL unavailable during readiness. | HTTP 503; PostgreSQL unavailable; other results still reported. | Planned / P0 |
| API-011 | Make Redis unavailable during readiness. | HTTP 503 with bounded response time. | Planned / P0 |
| API-012 | Make RabbitMQ unavailable during readiness. | HTTP 503 with bounded response time. | Planned / P0 |
| API-013 | Supply a valid correlation UUID. | Same value appears in response header and structured log context. | Planned / P0 |
| API-014 | Omit the correlation ID. | Server generates a UUID and returns it. | Planned / P0 |
| API-015 | Supply a malformed correlation ID. | Server replaces it safely; no header injection or exception occurs. | Planned / P0 |
| API-016 | Inspect user-list pagination constraints. | OpenAPI declares limit 1–100, offset 0–1,000,000, and safe defaults. | Executed / P0 |
| API-017 | Raise a domain error through the API boundary. | Stable error envelope and correlation field are returned. | Implemented / P0 |
| API-018 | Inspect role-catalogue routes and pagination constraints. | OpenAPI contains permission and role lifecycle operations with bounded list parameters. | Implemented contract evidence / P0 |
| API-019 | Inspect audit search, export, and detail routes plus their independent limits. | OpenAPI exposes all three operations; list limit is at most 100 and export limit is at most 10,000. | Implemented contract evidence / P0 |
| API-020 | Exceed a configured authentication limit. | HTTP 429 uses the global error envelope and includes `Retry-After` plus limit, remaining, and reset headers. | Implemented Docker integration evidence / P0 |
| API-021 | Inspect module-registry routes, filters, and pagination constraints. | OpenAPI exposes registration, discovery, update, and capability lifecycle operations with list limit 1–100. | Implemented contract/integration evidence / P0 |

### 11.4 Database, Migration, and Bootstrap

| ID | Test and objective | Expected result | Status / priority |
|---|---|---|---|
| DB-001 | Apply all migrations to an empty PostgreSQL database. | Upgrade succeeds and expected tables, keys, indexes, and constraints exist. | Offline DDL checked / P0 |
| DB-002 | Downgrade the initial revision in a disposable database. | Objects are removed in dependency-safe order. | Planned / P1 |
| DB-003 | Upgrade from the previous released revision. | Existing data remains valid and the service starts. | Planned for future revisions / P0 |
| DB-004 | Run migration upgrade twice to verify idempotent deployment behavior. | Second execution reports the database at head without error. | Planned / P0 |
| DB-005 | Insert duplicate user emails. | Unique constraint rejects the second row. | Planned / P0 |
| DB-006 | Insert duplicate role or permission names. | Unique constraints reject duplicates. | Planned / P1 |
| DB-007 | Verify UUID and timezone-aware timestamp generation. | Persisted rows receive valid UUIDs and UTC-capable timestamps. | Planned / P1 |
| DB-008 | Roll back a transaction containing state and an outbox event. | Neither business row nor event remains. | Planned / P0 |
| DB-009 | Start without bootstrap variables. | No administrator is created and startup continues. | Pending / P0 |
| DB-010 | Start with only one bootstrap variable. | Startup fails fast with a clear configuration error. | Planned / P0 |
| DB-011 | Start with both valid bootstrap variables. | Administrator, role, permissions, and creation event commit atomically. | Planned / P0 |
| DB-012 | Restart after bootstrap creation. | No duplicate administrator, role, permission, or event is created. | Planned / P0 |
| DB-013 | Attempt to update or delete an audit record in PostgreSQL. | Database trigger rejects both mutations. | Implemented runtime integration evidence / P0 |
| DB-014 | Apply audit-query indexes on a clean PostgreSQL database. | Migration `0004` creates chronological, actor, resource, and correlation indexes and the API starts successfully. | Implemented offline and Docker integration evidence / P0 |
| DB-015 | Apply the module-registry migration on a clean PostgreSQL database. | Migration `0005` creates module and capability tables, indexes, scoped uniqueness, cascade ownership, and the API starts successfully. | Implemented Docker integration evidence / P0 |

### 11.5 Event Outbox and RabbitMQ

| ID | Test and objective | Expected result | Status / priority |
|---|---|---|---|
| EVT-001 | Enqueue an event with a domain change in one transaction. | Both records commit together and share relevant identifiers. | Planned / P0 |
| EVT-002 | Validate the event envelope schema. | Required identity, type, time, aggregate, correlation, and payload fields are present. | Planned / P0 |
| EVT-003 | Verify routing-key naming and event versioning. | Message uses `atep.<context>.<entity>.<action>.v1`. | Planned / P0 |
| EVT-004 | Verify message durability and publisher confirms. | Persistent message is confirmed by the durable exchange. | Planned / P0 |
| EVT-005 | Publish a batch larger than 100 rows. | Worker processes multiple ordered batches without losing rows. | Planned / P1 |
| EVT-006 | Run two workers concurrently. | `SKIP LOCKED` prevents the same row being published simultaneously. | Planned / P0 |
| EVT-007 | Interrupt broker connectivity during publication. | Transaction does not mark unconfirmed messages as published; robust connection recovers. | Planned / P0 |
| EVT-008 | Restart the worker with pending rows. | Unpublished events resume publication. | Planned / P0 |
| EVT-009 | Deliver the same event twice to a reference consumer. | Consumer deduplicates by `event_id` and applies the effect once. | Planned / P0 |
| EVT-010 | Inject a permanently invalid event. | Policy moves or flags it after maximum attempts and raises an operational alert. | Planned after retry policy / P1 |
| EVT-011 | Create a user through the identity service and inspect pending persistence objects. | User, creation event, and audit record share one session and commit boundary. | Implemented unit evidence; rollback integration planned / P0 |
| EVT-012 | Mutate the module catalogue and inspect the outbox stream. | Registration, metadata/status change, capability declaration, and capability removal append four versioned events sharing the catalogue transaction. | Implemented service/Docker integration evidence / P0 |

### 11.6 Containers and Operations

| ID | Test and objective | Expected result | Status / priority |
|---|---|---|---|
| OPS-001 | Build the application image from a clean context. | Reproducible build succeeds with declared dependencies. | Planned / P0 |
| OPS-002 | Inspect the runtime user. | API and worker run as unprivileged `atep`. | Defined, execution pending / P0 |
| OPS-003 | Start Compose from an empty volume. | Dependencies become healthy, migration runs, API and worker start. | Planned / P0 |
| OPS-004 | Restart services while preserving PostgreSQL volume. | Data remains and migrations are not reapplied destructively. | Planned / P1 |
| OPS-005 | Stop and restart RabbitMQ. | API readiness reflects outage; worker reconnects after recovery. | Planned / P0 |
| OPS-006 | Stop and restart Redis. | Readiness changes predictably; authoritative data remains unaffected. | Planned / P1 |
| OPS-007 | Stop and restart PostgreSQL. | Readiness fails during outage and recovers after connections are re-established. | Planned / P0 |
| OPS-008 | Run a sustained availability exercise. | Measured availability and error budget can be calculated against the target. | Planned / P2 |

### 11.7 Performance, Resilience, and Observability

| ID | Test and objective | Expected result | Status / priority |
|---|---|---|---|
| PERF-001 | Load-test liveness and authenticated read endpoints. | p95 remains below the agreed 250 ms target at defined concurrency. | Planned / P1 |
| PERF-002 | Measure token-issue throughput under Argon2 load. | Capacity and CPU saturation point are documented; no unsafe hash weakening is used. | Planned / P1 |
| PERF-003 | Measure database pool behavior under concurrency. | Requests queue or fail predictably without exhausting PostgreSQL connections. | Planned / P1 |
| PERF-004 | Measure outbox publication throughput and age. | Sustainable events/second and maximum backlog recovery time are documented. | Planned / P1 |
| RES-001 | Kill an outbox worker during a batch. | Uncommitted publication state rolls back and remaining work is recoverable. | Planned / P0 |
| RES-002 | Introduce network latency to each dependency. | Readiness timeouts remain bounded and request threads are not exhausted. | Planned / P1 |
| RES-003 | Exhaust the database connection pool. | Controlled failures occur, logs identify saturation, and service recovers. | Planned / P1 |
| RES-004 | Fill the broker or reject publications. | Worker retains unpublished rows and emits actionable diagnostics. | Planned / P1 |
| OBS-001 | Validate structured log format. | Every application log line is valid JSON with timestamp and level. | Structlog JSON configuration implemented; capture assertion expansion planned / P1 |
| OBS-002 | Trace one correlation ID across request and outbox message. | The same ID is discoverable in API logs, span attributes, database event, and broker envelope. | Correlation propagation and span attribute implemented; broker-to-trace linking expansion planned / P0 |
| OBS-003 | Trigger an application exception. | Error is counted, span-marked, and logged with safe correlation/trace context without secrets. | Exception counter and span-error test passed; log capture expansion planned / P0 |
| OBS-004 | Detect an aging outbox backlog. | Metric or query crosses threshold and raises an alert. | Planned after metrics / P1 |
| OBS-005 | Validate readiness logging during dependency outage. | State change is diagnosable without excessive repetitive noise. | Planned / P2 |
| OBS-006 | Request concrete resource IDs and inspect Prometheus series. | Labels contain route templates and bounded method/status values; concrete IDs never appear. | Focused cardinality test passed / P0 |
| OBS-007 | Send no parent and a valid W3C `traceparent`. | A server span and 32-character `X-Trace-ID` are created; valid parent trace/span linkage is preserved. | Unit and Docker propagation evidence / P0 |
| OBS-008 | Configure tracing off, sample ratios, missing exporter, and OTLP endpoint. | Disabled mode exports nothing; bounds are validated; enabled export batches to the configured Collector without changing requests. | Typed settings and implementation passed; collector failure injection planned / P1 |
| OBS-009 | Scrape `/metrics` directly and through provisioned Prometheus. | Standard content is returned; Prometheus target is healthy; management endpoint remains outside public OpenAPI. | Unit, Docker direct-scrape, asset, and Compose validation evidence / P0 |
| OBS-010 | Load the provisioned Grafana dashboard and inspect all panels. | Request rate, p95, 5xx ratio, and in-progress panels query the pinned Prometheus datasource without raw-path labels. | Dashboard JSON contract passed; live UI inspection pending / P1 |
| OBS-011 | Query module health as authorized, unauthorized, healthy, degraded, unavailable, and unmonitored states. | Only `modules:read` succeeds; the constant-size response includes credentialed modules only and contains no identifiers or secrets. | Aggregate state and OpenAPI tests passed; expanded Docker RBAC assertion delegated to CI / P0 |
| OBS-012 | Update heartbeat/reconciler metrics and inspect series. | Only fixed status labels appear; counts, active ratio, at-risk leases, expirations, and reconciliation failures remain bounded. | Focused metrics contract passed / P0 |
| OBS-013 | Parse and validate SLO/alert rules. | Required recording rules and six named alerts have reviewed expressions, severities, persistence, and runbook links; `promtool` accepts the files. | Asset test passed locally; `promtool` delegated to CI / P0 |
| OBS-014 | Trigger every alert in an isolated environment. | Alert state, ownership, routing, notification, silence, and recovery evidence match the runbook. | Synthetic lifecycle covered; full rule matrix and silence exercise planned / P1 |
| OBS-015 | Measure empty and non-empty outbox backlog and inspect worker metrics. | Count/oldest age are correct; outcomes are success/error only; no event identifiers appear. | Aggregate/cardinality unit test and Docker scrape / P0 |
| OBS-016 | Measure due scheduled jobs before and after dispatch. | Count/oldest age, dispatch total, cycle duration, and failures reflect scheduler behavior without job identifiers. | Aggregate and metrics unit tests; Docker integration / P0 |
| OBS-017 | Open/reject a test-run stream and publish snapshot/update/heartbeat events. | Active connections return to zero; bounded outcomes/kinds increment; no run/user/vehicle label appears. | Metrics/cardinality unit test and existing WebSocket integration / P0 |
| OBS-018 | Stop Redis or RabbitMQ during live/outbox publication. | Failure counters increment; authoritative PostgreSQL state remains; outbox retries after rollback and WebSocket clients recover from snapshot. | Controlled unit failure passed; live dependency outage planned / P0 |
| OBS-019 | Validate the six domain alert rules with `promtool`. | Worker availability, backlog, and failure expressions, severities, persistence windows, and runbook links are accepted. | Asset test locally; `promtool` in CI / P0 |
| OBS-020 | Validate Alertmanager configuration and internal-only destinations. | `amtool` accepts the file; the only URL uses Docker DNS; host ports bind to loopback; image is pinned. | Asset test locally and `amtool` in CI / P0 |
| OBS-021 | Evaluate route grouping and inhibition policy. | Critical/warning routes use reviewed waits; critical inhibits warnings only when `service` is equal. | Configuration contract test / P0 |
| OBS-022 | Send valid and untrusted-severity webhook payloads. | Valid payload returns 202; arbitrary severity becomes `unknown`; no input label/annotation appears in metrics. | Two focused receiver tests passed / P0 |
| OBS-023 | Inject a synthetic alert through Alertmanager. | Alertmanager becomes ready and the receiver's critical/firing notification counter increments. | Disposable CI delivery scenario / P0 |
| OBS-024 | Resolve an injected alert and verify lifecycle delivery. | Receiver records a resolved notification for the same bounded group without retaining context. | Disposable CI delivery scenario / P0 |
| OBS-025 | Record healthy/unavailable dependency probes and attempt an arbitrary dependency label. | Only postgres/redis/rabbitmq and ready/unavailable series exist; arbitrary input is rejected before registration. | Focused cardinality test / P0 |
| OBS-026 | Execute successful and failed object-store operations. | Fixed operation/outcome metrics, exact transferred bytes, capacity gauges, and no object key or run identifier appear. | Instrumented filesystem test / P0 |
| OBS-027 | Call readiness and upload evidence in the disposable stack, then scrape API metrics. | All three dependencies report ready and successful artifact operations/capacity are visible. | Expanded Docker integration scenario / P0 |
| OBS-028 | Validate dependency and storage alerts. | `promtool` accepts persistent dependency, operation-error, and low-capacity rules with bounded labels and runbook links. | Asset test locally and `promtool` in CI / P0 |

### 11.8 Quality and Security Operations

| ID | Test and objective | Expected result | Status / priority |
|---|---|---|---|
| QLT-001 | Run all unit tests. | Suite passes and reports stable test discovery. | Implemented / P0 |
| QLT-002 | Run Ruff lint and formatting checks. | No violations or formatting drift. | Implemented / P0 |
| QLT-003 | Run strict mypy. | No type errors in application source. | Implemented / P0 |
| QLT-004 | Compile application, tests, and migrations. | No Python syntax errors. | Implemented / P0 |
| QLT-005 | Parse project metadata and Compose YAML. | Both documents load without structural errors. | Implemented / P1 |
| QLT-006 | Compare migration metadata against model metadata. | No uncommitted schema drift is detected. | Planned / P0 |
| QLT-007 | Measure unit and branch coverage. | Agreed thresholds pass; uncovered critical paths are reviewed. | Planned / P1 |
| QLT-008 | Mutation-test security and authorization rules. | Tests kill mutations that remove critical checks. | Planned / P1 |
| SECOPS-001 | Scan repository history for secrets with Gitleaks. | No credential or private key is detected. | Automated in security CI / P0 |
| SECOPS-002 | Audit the hash-locked Python runtime graph and emit a CycloneDX SBOM. | No known vulnerability remains unreviewed; SBOM is retained for 14 days. | Implemented; local audit passed / P0 |
| SECOPS-003 | Run CodeQL `security-extended` analysis for Python. | Findings are published and triaged with owner and due date. | Automated in security CI / P1 |
| SECOPS-004 | Generate a CycloneDX image SBOM and scan it with Grype. | High or critical findings fail CI; SBOM is retained for 14 days. | Automated in security CI / P0 |
| SECOPS-005 | Fuzz token and API input parsers. | Malformed input causes controlled 4xx responses and no crash. | Planned / P1 |
| SECOPS-006 | Review CORS, documentation exposure, headers, and TLS policy. | Production configuration matches the approved threat model. | Planned / P0 |
| SECOPS-007 | Attempt privilege escalation across RBAC boundaries. | No unauthorized operation or sensitive disclosure succeeds. | Planned / P0 |
| SECOPS-008 | Rotate the JWT secret in a staged environment. | Rotation procedure behaves as documented, including expected token invalidation. | Planned / P1 |
| SECOPS-009 | Verify dependency locks and immutable workflow/container inputs. | Locks cover direct dependencies with hashes and no index override; actions use full SHAs; the base uses a digest; Dependabot covers all three ecosystems. | Three automated policy tests passed / P0 |

### 11.9 Administrative Audit

| ID | Test and objective | Expected result | Status / priority |
|---|---|---|---|
| AUD-001 | Record user creation with actor, action, resource, and correlation identifiers. | One append-only audit record contains the expected non-sensitive metadata. | Implemented / P0 |
| AUD-002 | Record an account status change and its previous/current values. | Change is immediately visible and audit details preserve the transition. | Implemented / P0 |
| AUD-003 | Record role assignment and removal. | Each effective change produces the correct actor/resource audit entry. | Implemented unit evidence; API integration planned / P0 |
| AUD-004 | Mutate or delete a stored audit row directly. | PostgreSQL trigger blocks the operation. | Offline DDL checked; runtime integration planned / P0 |
| AUD-005 | Create, update, grant, revoke, and delete a role. | Five ordered, correlated, non-sensitive role audit actions remain after role deletion. | Implemented integration evidence / P0 |
| AUD-006 | Search by actor, action, resource, outcome, correlation ID, and time window. | Only matching immutable records are returned in deterministic newest-first order. | Implemented integration evidence / P0 |
| AUD-007 | Request audit pages and exports beyond their safe limits. | HTTP 422 uses the global error envelope; list pages remain at most 100 and exports at most 10,000 rows. | Implemented contract/integration evidence / P0 |
| AUD-008 | Access audit search without `audit:read` and export without `audit:export`. | Each operation returns HTTP 403 without evidence disclosure. | Search implemented integration evidence; export separation implemented by dependency / P0 |
| AUD-009 | Export matching evidence as CSV. | UTF-8 CSV has stable columns, neutralizes formula-like cells, contains only the bounded result, and creates `audit.records.exported` evidence. | Implemented unit/integration evidence / P0 |
| AUD-010 | Present a naive timestamp or reversed date window. | HTTP 422 rejects ambiguous or invalid temporal filters without executing the query. | Implemented unit evidence / P1 |
| AUD-011 | Archive a closed online partition and restore it in an isolated environment. | Counts, schema, and integrity manifest match; search is possible through the archive catalogue. | Planned with archive automation / P0 |
| AUD-012 | Apply and release a legal hold around an otherwise eligible partition. | No held evidence is archived for disposition or purged until formal release. | Planned with legal-hold workflow / P0 |

### 11.10 Distributed Rate Limiting

| ID | Test and objective | Expected result | Status / priority |
|---|---|---|---|
| RATE-001 | Consume a counter below its configured threshold. | Atomic result reports the configured limit, correct remaining count, and rounded reset interval. | Implemented unit evidence / P0 |
| RATE-002 | Send one request beyond the threshold. | HTTP 429 returns `rate_limit_exceeded`, `Retry-After`, and zero remaining quota. | Implemented unit/integration evidence / P0 |
| RATE-003 | Make Redis evaluation fail or exceed its timeout. | HTTP 503 returns `rate_limit_unavailable`; the request does not bypass protection. | Implemented unit evidence / P0 |
| RATE-004 | Inspect Redis limiter keys after authentication attempts. | Keys contain only namespaces and SHA-256-derived account/client fingerprints; no raw identity or credential is stored. | Implemented design/unit evidence / P0 |
| RATE-005 | Attempt authentication using email case and whitespace variants. | Normalization maps variants to the same account quota. | Implemented design; focused integration expansion planned / P1 |
| RATE-006 | Send authentication attempts for many accounts from one client. | The independent network-client threshold limits broad credential spraying. | Implemented control; focused integration expansion planned / P0 |
| RATE-007 | Send concurrent requests from multiple API replicas. | Redis atomic counters enforce one shared threshold without lost increments. | Atomic script implemented; multi-replica load evidence planned / P0 |
| RATE-008 | Deploy behind the production reverse proxy and test client attribution. | Only trusted forwarding data influences the client identity; spoofed headers cannot evade or amplify limits. | Planned production-hardening evidence / P0 |

### 11.11 Module Registry and Capability Catalogue

| ID | Test and objective | Expected result | Status / priority |
|---|---|---|---|
| MOD-001 | Register a canonical module with one initial capability. | HTTP 201 returns registered status, semantic version, endpoint metadata, and the sorted capability catalogue. | Implemented unit/integration evidence / P0 |
| MOD-002 | Register a duplicate canonical module name. | HTTP 409 returns stable `module_name_already_exists`; no second module is committed. | Implemented Docker integration evidence / P0 |
| MOD-003 | Submit unsafe module/capability names or a non-semantic version. | HTTP 422 uses the global validation envelope and no catalogue state changes. | Implemented unit/contract evidence / P0 |
| MOD-004 | Submit duplicate normalized capabilities during registration. | Validation rejects the command before persistence. | Implemented unit evidence / P0 |
| MOD-005 | Page and filter modules by exact capability or administrative status. | Results are deterministic and bounded to 100 records; only matching modules are returned. | Implemented contract/integration evidence / P0 |
| MOD-006 | Read the catalogue with `modules:read` but without `modules:manage`. | Discovery succeeds while every mutation returns HTTP 403. | Permission dependency implemented; focused integration expansion planned / P0 |
| MOD-007 | Access discovery without `modules:read`. | HTTP 403 returns `permission_denied` without catalogue disclosure. | Implemented Docker integration evidence / P0 |
| MOD-008 | Declare, update, and remove a capability. | Scoped uniqueness is retained; responses show the current sorted catalogue and a missing removal returns stable 404. | Declare/remove implemented unit/integration evidence; focused update test planned / P1 |
| MOD-009 | Inspect registration and catalogue mutation audit evidence. | Correlated, non-sensitive actions identify actor and module; four expected actions remain immutable. | Implemented unit/Docker integration evidence / P0 |
| MOD-010 | Inspect outbox atomicity for registration and catalogue mutations. | Module state, audit evidence, and versioned outbox events share one transaction; four events are persisted in the exercised flow. | Implemented service/Docker integration evidence / P0 |
| MOD-011 | Stop heartbeats for an active or degraded module and wait beyond its lease. | The reconciler marks it inactive and atomically writes system audit evidence and an availability event. | Implemented unit/Docker integration evidence / P0 |
| MOD-012 | Issue and then rotate a module credential. | Each raw token is returned only once, only a SHA-256 digest is persisted, and the older token can no longer authenticate. | Implemented unit/Docker integration evidence / P0 |
| MOD-013 | Use an invalid credential or submit `registered`/`inactive` through heartbeat. | Invalid credentials return stable HTTP 401; invalid operational states return the global HTTP 422 validation envelope. | Implemented unit/contract/integration evidence / P0 |
| MOD-014 | Renew a lease and change status/version through authenticated heartbeat. | Lease timestamps advance within the configured bound; only effective status/version transitions enqueue availability events and routine heartbeats create no audit noise. | Implemented unit/Docker integration evidence / P0 |

### 11.12 Vehicle Gateway and Telemetry

| ID | Test and objective | Expected result | Status / priority |
|---|---|---|---|
| VEH-001 | Register, page, inspect, activate, and deactivate a canonical vehicle. | Versioned APIs return deterministic state; lifecycle changes are audited and evented. | Service/contract implementation; Docker API evidence planned / P0 |
| VEH-002 | Register a duplicate or unsafe vehicle identifier. | Canonical duplicate returns HTTP 409; invalid syntax returns the global HTTP 422 envelope. | Validation and stable error implemented; focused API evidence planned / P0 |
| VEH-003 | Exercise `vehicles:read` and `vehicles:manage` independently. | Readers cannot mutate; unauthorized identities receive HTTP 403 without catalogue disclosure. | RBAC dependency implemented; focused API evidence planned / P0 |
| VEH-004 | Publish telemetry with missing, invalid, or rotated gateway credentials. | Request returns stable HTTP 401 and no observation or outbox event is committed. | Credential primitive implemented; focused service/API evidence planned / P0 |
| VEH-005 | Publish from a valid module without `vehicle.telemetry.publish`. | Request returns HTTP 403 `module_capability_required` and names the required capability. | Implemented unit evidence / P0 |
| VEH-006 | Submit invalid property names, event IDs, values, or a timestamp without a UTC offset. | Global HTTP 422 validation envelope identifies the invalid field; no data is persisted. | Implemented schema/contract evidence / P0 |
| VEH-007 | Commit a new telemetry observation and inspect its outbox row. | Observation and `atep.vehicle.telemetry.received.v1` exist together with matching correlation and identifiers. | Implemented service evidence; Docker transaction evidence planned / P0 |
| VEH-008 | Retry an identical event ID and payload after a simulated network timeout. | HTTP 200 returns the original receipt with `duplicate: true`; no second observation or outbox event exists. | Implemented unit evidence; Docker retry evidence planned / P0 |
| VEH-009 | Reuse an event ID with a changed property, value, source, vehicle, module, unit, or timestamp. | HTTP 409 `telemetry_event_conflict` is stable and the original observation remains unchanged. | Implemented unit evidence / P0 |
| VEH-010 | Query vehicle telemetry with bounded paging and exact property filtering. | Results are newest-first, capped at 500, permission protected, and represented by the published OpenAPI schema. | Contract implemented; database/API evidence planned / P1 |
| VEH-011 | Disconnect the Android gateway, buffer observations, reconnect, and resend. | Locally durable events arrive once logically despite retransmission and preserve original timestamps. | Persistent queue and stable-ID retry unit evidence passed; live `CT-SHOW-006` pending / P0 |
| VEH-012 | Compare simulator and CarPropertyManager/VHAL mappings. | The same canonical state and telemetry units are preserved; speed is converted from m/s to km/h and battery percentage from energy/capacity. | Implemented Android unit evidence; live AAOS evidence pending / P0 |
| VEH-013 | Start the showcase without module credentials and inspect gateway state and network behavior. | Gateway reports disabled, stores no event, performs no delivery, and displays no secret material. | Implemented Android unit/build evidence; manual UI check pending / P0 |
| VEH-014 | Select explicit AAOS mode with all, partial, and no accessible VHAL properties. | Origin remains AAOS, local controls remain unavailable, accessible signals continue, and no simulated observation replaces missing evidence. | Implemented negative/unit evidence; manual `CT-SHOW-007` pending / P0 |
| VEH-015 | Queue telemetry offline, close the process, restore connectivity, and inspect unique background work and ATEP receipts. | One job per vehicle survives the activity lifecycle, flushes in order, retains event identity, creates no duplicate observation, and stops or exhausts according to policy. | Implementation and six policy tests passed; manual `CT-SHOW-008` pending / P0 |
| VEH-016 | Inspect rejected telemetry, retry one corrected event, discard one selected record, exhaust background work, and resume explicitly. | Evidence survives process restart; retry preserves identifier and timestamp; discard is item-scoped; eight failures stop automatic scheduling; manual recovery clears exhaustion. | Implementation and five focused tests passed; manual `CT-SHOW-009` pending / P0 |
| VEH-017 | Create a vehicle command with `vehicle_commands:write` and inspect audit/outbox state. | One pending command, one immutable audit record, and `atep.vehicle.command.requested.v1` share the transaction. | Implemented service and Docker API evidence / P0 |
| VEH-018 | Repeat an identical command request and then reuse the identifier with changed parameters. | Exact retry returns the original command without new evidence; changed data returns HTTP 409 `vehicle_command_conflict`. | Implemented unit and stable-error evidence / P0 |
| VEH-019 | Create or list commands without the independent read/write permission. | Request is denied with HTTP 403 and no command catalogue or mutation is disclosed. | RBAC dependency implemented; focused Docker API evidence pending / P0 |
| VEH-020 | Claim a command using invalid credentials, missing capability, wrong target, or no available work. | Invalid identity returns 401, missing capability returns 403, another target cannot receive the command, and an empty claim returns 204. | Authentication/contract implementation and missing-capability Docker evidence / P0 |
| VEH-021 | Claim available or lease-expired work concurrently. | Locked oldest-first selection returns one command, increments attempt count, grants a 10–300-second lease, rotates the claim token, and stores only its SHA-256 digest. | Implemented service and migration evidence / P0 |
| VEH-022 | Acknowledge success/rejection, retry the exact acknowledgement, and submit an invalid or expired claim token. | Terminal state and `atep.vehicle.command.completed.v1` are written once; exact retry is idempotent; invalid/expired claims return a stable conflict. | Implemented unit and successful/duplicate Docker transaction evidence / P0 |
| VEH-023 | Apply allowed, out-of-range, unsafe, unknown, and read-only-source commands in CarSystemUI. | Allowed simulator state changes and emits telemetry; invalid/unsafe/unknown/AAOS mutations remain unchanged and receive a stable rejected acknowledgement. | Six Android tests and live `CT-SHOW-010` passed / P0 |
| VEH-024 | Create, page, filter, and inspect a test run with independent read/write permissions. | Authorized requests return bounded canonical records; missing permission returns HTTP 403. | Service and Docker integration evidence passed / P0 |
| VEH-025 | Repeat an exact test-run creation and reuse the `run_id` with changed input. | Exact retry returns the original record; changed input returns stable HTTP 409 `test_run_conflict`. | Unit and Docker integration evidence passed / P0 |
| VEH-026 | Inspect creation and status transactions. | State, immutable audit, and `atep.test_run.created.v1` or `atep.test_run.status_changed.v1` share one commit. | Unit and disposable outbox integration evidence passed / P0 |
| VEH-027 | Submit valid queued-to-running-to-passed/failed/cancelled transitions and invalid shortcuts or terminal changes. | Valid timestamps, progress, and version advance once; invalid transitions return `test_run_state_conflict`. | Unit, validation, and Docker integration evidence passed / P0 |
| VEH-028 | Race or retry status changes with stale expected versions. | Row locking prevents lost updates; changed stale input returns `test_run_version_conflict`; exact retry remains idempotent. | Unit and Docker integration evidence passed / P0 |
| VEH-029 | Subscribe with missing, invalid, inactive, unauthorized, and authorized bearer tokens. | Connections close with 4401/4403 as applicable; authorized clients receive snapshot, heartbeat, and committed updates without Redis access. | Auth implementation and successful Docker WebSocket evidence; focused negative handshake expansion planned / P0 |
| VEH-030 | Deliver duplicate, out-of-order, heartbeat, disconnect, and reconnect events to CarSystemUI. | Non-increasing versions are ignored, heartbeat retains the latest state, and bounded reconnect preserves the visible snapshot. | Three Android unit tests, lint, and debug build passed / P0 |
| ENV-001 | Create and page EV, hybrid, and autonomous profiles with simulator or AAOS sources. | Canonical profiles are returned deterministically under bounded paging and independent permissions. | Schema/service implementation and focused tests passed / P0 |
| ENV-002 | Repeat exact creation and reuse a profile ID with changed content. | Exact retry returns the original profile; changed content returns `environment_profile_conflict`. | Focused idempotency test passed / P0 |
| ENV-003 | Activate a draft and archive an active profile. | Each effective transition advances the version once and records evidence. | Focused lifecycle test passed / P0 |
| ENV-004 | Skip a lifecycle state, mutate an archived profile, or submit a stale expected version. | Stable state/version conflicts preserve the original profile. | Focused negative tests passed / P0 |
| ENV-005 | Inspect profile creation and transition transactions. | Profile state, immutable audit, and versioned outbox event share one commit. | Service evidence passed; Docker expansion planned / P0 |
| ENV-006 | Create a TestRun with draft, active, archived, and later-archived profile inputs. | Only active input is accepted and the run retains the exact version/configuration snapshot thereafter. | Active guard implemented and snapshot test passed; focused API expansion planned / P0 |
| JOB-001 | Create, page, filter, and inspect a timezone-aware scheduled job under independent permissions. | Canonical bounded responses are returned; missing permission receives HTTP 403. | Schema, OpenAPI, service, and Docker RBAC evidence / P0 |
| JOB-002 | Repeat exact job creation and reuse either the job ID or target run ID differently. | Exact retry returns the original job without duplicate evidence; conflicting reuse returns stable `test_job_conflict`. | Focused idempotency test and database uniqueness / P0 |
| JOB-003 | Cancel scheduled work twice using the original request. | First cancellation advances state/version and records evidence; exact retry returns the same result without duplication. | Focused lifecycle test / P0 |
| JOB-004 | Cancel with a stale version or after dispatch. | Stable version/state conflict is returned and persisted state remains unchanged. | Focused negative tests / P0 |
| JOB-005 | Run two scheduler replicas against the same due batch. | Row locking with `SKIP LOCKED` assigns each job to at most one transaction and preserves oldest-first bounded selection. | Query design implemented; concurrent stress expansion planned / P0 |
| JOB-006 | Dispatch due work and inspect the generated run, job, audit, and outbox rows. | Exactly one queued TestRun is linked; job becomes dispatched; all state and evidence commit atomically. | Focused unit and disposable Docker integration evidence / P0 |
| ART-001 | Upload non-empty log, report, trace, image, video, binary, and other evidence within the configured bound. | Content is streamed to the object adapter; canonical metadata, byte size, and SHA-256 are returned. | Filesystem adapter and multipart Docker scenario implemented / P0 |
| ART-002 | Repeat exact upload and reuse the same run/artifact identifier with changed bytes or metadata. | Exact retry returns HTTP 200 and the original record without new evidence; changed reuse returns `test_artifact_conflict`. | Focused service and Docker API evidence / P0 |
| ART-003 | Interrupt object writing or fail metadata persistence after storage. | Temporary/failed objects are removed when detected and no partial metadata is committed. | Oversize cleanup test passed; database-failure injection planned / P0 |
| ART-004 | Submit empty, oversized, path-like filename, root-escaping key, and missing-content cases. | Stable bounded errors are returned; no unsafe path or partial object remains; internal keys are absent from responses. | Schema, adapter, size, and OpenAPI tests passed / P0 |
| ART-005 | List, inspect, upload, or download without the independent permission. | Unauthorized access receives HTTP 403 before metadata or content is disclosed. | RBAC dependency and disposable Docker denial evidence / P0 |
| ART-006 | Download stored evidence and compare headers/body with metadata. | Media type, safe filename, content length, ETag, SHA-256, and bytes match the immutable record. | Disposable Docker download evidence / P0 |
| ART-007 | Inspect metadata, audit, and outbox rows after one successful upload and exact retry. | One metadata row, one immutable audit row, and one `atep.test_artifact.stored.v1` event exist. | Service assertions and disposable database integration evidence / P0 |

## 12. Suggested CI/CD Quality Pipeline

1. **Source checks:** secret scan, license policy, dependency lock review.
2. **Static checks:** Python compilation, Ruff formatting/lint, strict mypy, SAST.
3. **Unit checks:** fast test suite and coverage threshold.
4. **Contract checks:** OpenAPI snapshot and event-schema compatibility.
5. **Build:** immutable image, labels, SBOM, vulnerability scan, signature.
6. **Integration checks:** disposable PostgreSQL, Redis, and RabbitMQ; migrations; API and outbox tests.
7. **Environment deployment:** development namespace with externally managed secrets.
8. **Smoke checks:** liveness, readiness, authentication, RBAC, and one event publication.
9. **Promotion:** manual or policy gate using retained evidence.
10. **Post-deployment verification:** dashboards, alerts, rollback readiness, and audit record.

Pipeline artifacts should include test reports, coverage, OpenAPI schema, migration plan, SBOM, image digest, security scan results, deployment manifest, and a short verification summary.

## 13. Security Threat Review

| Threat | Current control | Remaining action |
|---|---|---|
| Credential theft | Argon2 hashes, no default credentials, and account/client authentication limits | Add MFA option, breach-password checks, secure reset flow, and measured lockout policy |
| Token theft or forgery | Signed short-lived access token, opaque hash-only refresh storage, rotation, and replay-family revocation | Add key identifiers, asymmetric keys or managed identity; consider access-token deny-listing for high-risk deployments |
| Account enumeration | Generic errors, dummy password verification, and normalized-account rate limiting | Benchmark timing and monitor distributed guessing patterns |
| Privilege escalation | Permission-based checks and normalized identity | Add administration audit trail, approval rules, and negative authorization suite |
| Secret leakage | Environment-based secrets, ignored `.env`, and automated history scanning | Add secret manager, rotation runbooks, and expanded log redaction tests |
| SQL injection | SQLAlchemy expression API, parameterization, and CodeQL analysis | Maintain code review and test any raw SQL explicitly |
| Event spoofing or tampering | Controlled exchange publication and message identity | Add broker TLS/mTLS, broker permissions, schema validation, and optional message signing |
| Message replay | Unique event IDs and documented idempotency | Implement consumer inbox/deduplication and retention policy |
| Dependency compromise | Hash-locked Python graphs, immutable build inputs, weekly updates, SBOMs, and dependency/image scanning | Add signature verification, provenance attestations, long-term release evidence, and supplier-response policy |
| Denial of service | Bounded readiness timeouts and distributed versioned-API limits | Add body-size/pool limits, backpressure, proxy-aware attribution, and load evidence |

## 14. Risk and Technical Debt Register

| ID | Risk or debt | Impact | Mitigation / next action | Priority |
|---|---|---|---|---|
| R-001 | Disposable local integration is automated and a CI workflow is defined, but no remote CI run has been retained yet. | Runner-image or hosted-network differences may remain undiscovered. | Execute the workflow on GitHub and retain the first successful run as evidence. | Low |
| R-002 | Refresh rotation and revocation are implemented, but stateless access tokens cannot be revoked before expiry. | A stolen access token remains usable for its remaining short lifetime. | Evaluate Redis-backed deny-listing and reduce access lifetime for high-risk deployments. | Medium |
| R-003 | Bootstrap configuration remains present after first use. | Misconfiguration could expose unnecessary credential material. | Define one-time deployment procedure and remove bootstrap secrets immediately. | High |
| R-004 | Outbox has no maximum retry or quarantine policy. | A poison event may retry indefinitely or block observability. | Add backoff, attempt policy, quarantine, metrics, and operator replay. | High |
| R-005 | Audit search/export and the retention baseline are implemented, but immutable archive, restore, legal-hold, and disposition automation are not. | PostgreSQL storage will grow indefinitely and long-term restorability remains unproven. | Implement partition-aware archive automation, integrity manifests, restore drills, capacity alerts, and controlled disposition. | Medium |
| R-006 | Health checks create direct dependency connections. | Probe volume may add avoidable load. | Benchmark and consider pooled/lightweight broker health strategy. | Medium |
| R-007 | The global API error schema is not snapshot/version compatibility tested. | An accidental shape change may break clients. | Add OpenAPI snapshots and consumer contract checks. | Medium |
| R-008 | Dependency locks, immutable inputs, update automation, SBOMs, and scanning are implemented, but release signing and verifiable provenance are not. | A compromised authorised build or unsigned artifact may still be substituted downstream. | Add isolated release builders, signatures, attestations, verification policy, and long-term release evidence. | Medium |
| R-009 | Bounded dependency and storage telemetry exists, but database-pool saturation, Redis/RabbitMQ provider internals, durable quota/retention signals, and asynchronous trace links remain incomplete. | Some saturation, capacity-policy, or cross-process failures may still require provider consoles and log-centric investigation. | Add provider exporters/pool metrics and OpenTelemetry links with load, outage, and cardinality evidence. | Medium |
| R-010 | No formal backup/restore evidence. | Data recovery capability is unknown. | Define RPO/RTO, automated backups, restore drills, and evidence retention. | High |
| R-011 | Rate limiting uses fixed windows and the direct network peer when no bearer credential is present. | Bursts near a window boundary may temporarily exceed the nominal rate; a shared reverse-proxy address may group unrelated clients. | Calibrate thresholds with load tests and implement a reviewed trusted-proxy attribution policy before public deployment. | High |
| R-012 | Shared-secret workload authentication and application-process reconciliation are implemented, but mTLS, per-instance identity, and multi-replica scheduler ownership are not. | Credential theft could permit module impersonation, and operational behavior under multiple independently scheduled API replicas is not yet evidenced. | Add secret-manager delivery, mTLS or managed workload identity, instance leases, reconciliation metrics, and explicit leader/scheduler ownership before dynamic routing. | Medium |
| R-013 | The development artifact adapter uses node-local filesystem storage and external object creation cannot share the PostgreSQL transaction. | Multiple replicas may not see the same content; a process crash between object promotion and metadata commit can leave an orphan; unscanned evidence can carry unsafe content. | Use shared encrypted S3-compatible storage in deployed environments; add orphan reconciliation, malware scanning, retention/legal-hold policy, quotas, signed internal retrieval, and lifecycle metrics. | High |
| R-014 | Local Alertmanager routing exists, but Grafana remains anonymous, trace output is debug-only, management endpoints lack application authentication, and no production incident provider/owner is configured. | Deploying local defaults publicly could disclose operations; traces are non-durable; local webhook evidence cannot page an accountable responder. | Keep loopback/network isolation, disable anonymous access, require TLS/workload authentication, add durable traces and managed provider routing, validate escalation, delivery, cardinality, overhead, and thresholds before production. | High |

## 15. Roadmap and Increment Plan

### Increment 2 — Administration and Audit

- user creation, retrieval, pagination, status, and role-assignment endpoints — implemented;
- immutable administrative audit foundation — implemented;
- consistent error and pagination contracts — implemented;
- refresh-token rotation, reuse detection, revocation, and secure logout — implemented;
- role catalogue administration — implemented;
- audit query, bounded export, and retention-policy baseline — implemented;
- immutable archive, restore verification, legal hold, and controlled disposition — production hardening;
- Redis-backed authentication and API rate limiting — implemented;
- trusted-proxy attribution, multi-replica load evidence, and production threshold tuning — production hardening;
- API, database, and broker integration suites.

### Increment 3 — Platform Services

- service registry and module capability catalogue — implemented;
- authenticated module heartbeat, bounded lease expiry, credential rotation, and automatic reconciliation — implemented;
- vehicle catalogue and capability-protected idempotent telemetry ingestion — implemented initial slice;
- CarSystemUI showcase connection to the ATEP REST contract — implemented initial gateway slice;
- replaceable simulator/AAOS `VehiclePropertySource` and read-only CarPropertyManager compatibility bridge — implemented initial slice;
- unique connectivity-constrained WorkManager retry with bounded exponential backoff — implemented and build verified;
- persistent rejected-event inspection, unchanged-identity retry, selective discard, and retry-exhaustion visibility — implemented and build verified;
- immutable operator-decision evidence and live emulator/VHAL-to-ATEP execution — next;
- area-aware door/seat mapping and typed `subscribePropertyEvents` in the AOSP platform build — planned;
- authorized leased test-command delivery with safe Android execution — implemented and verified by live `CT-SHOW-010` emulator evidence;
- production WebSocket connection limits, revocation fan-out, metrics, and resume-from-version replay;
- vehicle/test configuration profiles;
- persistent scheduler boundary and job lifecycle — implemented initial slice;
- object-storage abstraction for test artifacts — implemented initial slice;
- correlated traces, bounded domain/dependency/storage metrics, aggregate health/backlog, dashboards, recording rules, alerts, and local Alertmanager delivery — implemented; durable traces, provider-specific saturation, production routing, threshold calibration, and sustained SLO evidence remain hardening.
- deterministic locks, immutable build inputs, secret/dependency/source/image scanning, CycloneDX SBOMs, and weekly update proposals — implemented; signing and provenance remain hardening.

### Increment 4 — Production Hardening

- Kubernetes deployment and workload identity;
- mTLS and secret-manager integration;
- backup, restore, retention, and disaster-recovery exercises;
- performance, resilience, and security-policy calibration;
- signed artifacts, verifiable provenance, long-term release evidence, and controlled promotion across environments.

## 16. Engineering Review Worksheets

### 16.1 Architecture Change Entry

| Field | Entry |
|---|---|
| Change title |  |
| Date / owner |  |
| Problem and constraints |  |
| Options considered |  |
| Decision and rationale |  |
| Security / reliability impact |  |
| Migration and rollback |  |
| Requirements affected |  |
| Tests and evidence required |  |

### 16.2 Test Execution Record

| Field | Entry |
|---|---|
| Test ID and version |  |
| Date / executor |  |
| Build / image digest |  |
| Environment |  |
| Preconditions and test data |  |
| Procedure / command |  |
| Expected result |  |
| Actual result |  |
| Evidence location |  |
| Pass / fail / blocked |  |
| Defect or follow-up |  |

### 16.3 Increment Retrospective

| Prompt | Notes |
|---|---|
| What was delivered and verified? |  |
| Which assumptions changed? |  |
| What caused rework or delay? |  |
| Which risks increased or decreased? |  |
| What technical debt was accepted? |  |
| Which engineering practice should be retained? |  |
| What is the highest-value next experiment? |  |

## 17. Operational Runbook Starter

### Normal Startup

1. Provide environment-specific URLs and secrets.
2. Start PostgreSQL, Redis, and RabbitMQ and wait for health.
3. Apply Alembic migrations exactly once per release.
4. Start the API and outbox worker from the same immutable image.
5. Verify liveness and readiness.
6. Authenticate a controlled test account and publish one smoke-test event.
7. Confirm logs and correlation IDs, then enable traffic.

### Dependency Outage Triage

- check `/health/ready` to identify the unavailable dependency;
- search structured logs by correlation ID and timestamp;
- inspect database pool, Redis availability, or RabbitMQ connection/channel state;
- avoid deleting outbox rows to resolve a broker outage;
- restore the dependency, verify automatic recovery, and review backlog age;
- record the incident, customer impact, root cause, and preventive action.

### Rollback Principle

Application rollback is safe only when the previous version is compatible with the migrated schema and event contracts. Prefer backward-compatible expand-and-contract migrations. Never perform an automatic destructive database downgrade on production data without a reviewed recovery plan and backup evidence.

## 18. Glossary

| Term | Definition |
|---|---|
| ATEP | Automotive Test Engineering Platform |
| Control plane | APIs and services that configure, secure, coordinate, and observe platform behavior |
| RBAC | Role-Based Access Control; permissions are grouped into roles assigned to users |
| JWT | JSON Web Token used here as a signed, time-limited access credential |
| DTC | Diagnostic Trouble Code, introduced in later diagnostics volumes |
| ECU | Electronic Control Unit |
| Transactional outbox | Pattern that records state and integration events atomically before asynchronous publication |
| At-least-once delivery | A message may be delivered more than once but should not be lost after successful commit |
| Idempotency | Repeating an operation produces no additional unintended effect |
| Liveness | Whether the process itself is running and responsive |
| Readiness | Whether the process can safely serve traffic with required dependencies available |
| Correlation ID | Identifier propagated across operations to reconstruct one distributed flow |
| SLO | Service Level Objective, a measurable reliability target |
| SBOM | Software Bill of Materials listing the components in an artifact |
| Rate limit | A bounded request quota enforced over an expiring time window to reduce abuse and overload |
| Module registry | The authoritative control-plane catalogue of ATEP modules, metadata, declared status, and versioned capabilities |
| Capability | A canonical, versioned function that a module declares for discovery and integration |
| Workload credential | A high-entropy module secret returned once and persisted only as a SHA-256 digest |
| Heartbeat lease | A bounded interval during which an authenticated module is considered operationally present |
| Reconciliation | A periodic process that converts expired operational leases into observable inactive state |
| CarSystemUI | The Android Automotive in-vehicle interface, learning surface, simulator, AAOS property adapter, and ATEP gateway |
| Vehicle Gateway | Adapter that maps CarPropertyManager/VHAL observations and authorized commands to versioned ATEP contracts |
| VehiclePropertySource | Android boundary that supplies canonical vehicle state from an explicitly identified simulator or AAOS origin |
| CarPropertyManager | Android Automotive application API for reading, writing, and subscribing to permitted vehicle properties exposed by CarService |
| VHAL | Vehicle Hardware Abstraction Layer; the Android boundary to a physical or simulated vehicle implementation |
| WorkManager | Android Jetpack scheduler for persistent, constrained, deferrable background work that can survive process termination and reboot |
| Telemetry event | A timestamped property observation identified by a client-generated idempotency key |
| Rejected telemetry | A permanently refused client event retained locally with its original evidence and a non-sensitive reason for explicit disposition |
| Retry exhaustion | A persisted terminal delivery state reached after the configured attempt bound; automatic scheduling remains stopped until explicit recovery |
| Vehicle command | An idempotent operator-requested instruction addressed to one vehicle and one target module for bounded gateway execution |
| Command lease | A time-bounded exclusive claim that permits recovery when execution or acknowledgement is interrupted |
| Claim token | A high-entropy secret binding one acknowledgement to its current command attempt; only its SHA-256 digest is persisted |
| Environment profile | An immutable named vehicle/test baseline containing vehicle kind, property source, bounded configuration, lifecycle status, and version |
| Reproducibility snapshot | The profile identity, version, source, kind, and configuration copied into a TestRun so later archival cannot change executed evidence |

## 19. Evidence Index

| Evidence | Repository location |
|---|---|
| Application composition and middleware | `src/atep/main.py` |
| Security primitives | `src/atep/core/security.py` |
| Configuration contract | `src/atep/core/config.py` and `.env.example` |
| Identity and RBAC | `src/atep/identity/` |
| Global API error contract | `src/atep/core/errors.py` |
| Distributed Redis rate limiting | `src/atep/core/rate_limit.py`, typed settings, and application dependencies |
| Module registry, heartbeat, and reconciliation | `src/atep/registry/`, including `src/atep/registry/reconciler.py`; migrations `0005_module_registry.py` and `0006_module_heartbeat_leases.py`; and module API contracts |
| Vehicle catalogue, telemetry, and leased commands | `src/atep/vehicles/`, migrations `0007_vehicle_telemetry.py` and `0008_vehicle_command_delivery.py`, API contracts, `tests/test_vehicle_telemetry.py`, and `tests/test_vehicle_commands.py` |
| Test-run lifecycle and live updates | `src/atep/test_runs/`, migration `0009_test_runs.py`, `tests/test_test_runs.py`, and the WebSocket path in `tests/integration/test_identity_flow.py` |
| Environment profiles and TestRun snapshots | `src/atep/environment_profiles/`, migration `0010_environment_profiles.py`, and `tests/test_environment_profiles.py` |
| Persistent test-job scheduling | `src/atep/test_jobs/`, migration `0011_test_jobs.py`, `tests/test_test_jobs.py`, and the disposable integration scenario |
| Immutable test-artifact storage | `src/atep/artifacts/`, migration `0012_test_artifacts.py`, `tests/test_artifacts.py`, and multipart upload/download integration evidence |
| Android Vehicle Gateway, property sources, retry worker, operator evidence, and command executor | `CarSystemUI_android/showcase/app/.../gateway/`, `showcase/app/.../vehicle/`, Android unit tests, `docs/ATEP_VEHICLE_GATEWAY.md`, and `docs/TEST_CASE_CT_SHOW_006.md` through `docs/TEST_CASE_CT_SHOW_010.md` in the companion repository |
| Immutable audit model, query/export APIs, and recorder | `src/atep/audit/` |
| Event outbox and worker | `src/atep/events/` |
| Database migrations | `migrations/versions/0001_core_platform.py` through `0012_test_artifacts.py` |
| Refresh-session implementation | `src/atep/identity/sessions.py`, identity models, schemas, and router |
| Local service topology | `compose.yaml` and `Dockerfile` |
| Optional observability topology | `compose.observability.yaml`, `deploy/observability/`, `src/atep/core/observability.py`, and `docs/observability.md` |
| Dependency and storage telemetry | `src/atep/api/health.py`, `src/atep/artifacts/storage.py`, `tests/test_dependency_storage_observability.py`, alert rules, and disposable scrape evidence |
| Disposable integration topology and runner | `compose.integration.yaml` and `tools/run_integration_tests.ps1` |
| Black-box integration scenario | `tests/integration/test_identity_flow.py` |
| Continuous integration workflows | `.github/workflows/integration.yml` and `.github/workflows/security.yml` |
| Supply-chain controls and evidence | `requirements.lock`, `requirements-dev.lock`, `Dockerfile`, `.github/dependabot.yml`, `.github/workflows/security.yml`, `docs/software-supply-chain-security.md`, and `tests/test_supply_chain_security.py` |
| Automated tests | `tests/test_security.py`, `test_identity.py`, `test_user_administration.py`, `test_role_catalogue.py`, `test_audit_query.py`, `test_rate_limit.py`, `test_module_registry.py`, `test_module_health.py`, `test_vehicle_telemetry.py`, `test_vehicle_commands.py`, `test_test_runs.py`, `test_test_jobs.py`, `test_artifacts.py`, `test_observability.py`, `test_domain_observability.py`, `test_dependency_storage_observability.py`, `test_alert_delivery.py`, `test_observability_assets.py`, `test_supply_chain_security.py`, and `test_api_contract.py` |
| Architecture summary | `docs/architecture.md` |
| Requirements baseline | `docs/requirements-volume-i.md` |
| Delivery roadmap | `docs/roadmap-volume-i.md` |
| Audit retention baseline | `docs/audit-retention-policy.md` |

## 20. Workbook Maintenance Checklist

- update the document version and revision history;
- reconcile capability status against the repository;
- add or revise requirements and acceptance criteria;
- record architecture decisions and superseded decisions;
- update the test catalogue and executed evidence;
- review threat model, risk register, and technical debt;
- confirm roadmap priorities and Volume I exit criteria;
- render the Word version and inspect every page before publication.
