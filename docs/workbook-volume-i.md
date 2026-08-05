# ATEP Volume I — Core Platform Engineering Workbook

**Subtitle:** Architecture, implementation record, verification strategy, and engineering evidence  
**Project:** Automotive Test Engineering Platform (ATEP)  
**Document version:** 0.14.0

**Baseline date:** 4 August 2026

**Status:** Living engineering document — persistent Android background retry implemented
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

The initial design deliberately starts as a modular monolith rather than a collection of empty microservices. Clear package boundaries and versioned event contracts allow later extraction when scaling, ownership, availability, or release cadence provides a concrete reason. This reduces operational complexity while protecting the intended distributed architecture.

### Current Increment at a Glance

| Capability | Status | Evidence |
|---|---|---|
| FastAPI control-plane API | Implemented | Versioned authentication and health routes load in OpenAPI |
| Authentication | Implemented | Short-lived JWT access tokens, opaque refresh rotation/revocation, generic failures, and Argon2 hashing |
| RBAC data model | Implemented | User, role, permission, and association tables |
| User administration | Implemented | Create, list, inspect, status, role assignment, and role removal routes |
| Role catalogue administration | Implemented | Permission listing; role create, page, inspect, update, grant, revoke, and safe delete routes |
| PostgreSQL persistence | Implemented | SQLAlchemy models and Alembic revisions `0001` through `0007` |
| Module registry | Implemented | Persistent metadata, capability catalogue, hash-only workload credentials, heartbeat leases, and automatic reconciliation |
| Vehicle integration boundary | Implemented initial slice | Vehicle catalogue, lifecycle state, gateway capability authorization, idempotent telemetry, and outbox contract |
| Android Vehicle Gateway | Implemented initial slice | Changed-property mapping, persistent queue, stable retry identity, bounded rejection storage, HTTP transport, and status UI in the CarSystemUI showcase |
| Android vehicle property sources | Implemented initial AAOS slice | Replaceable simulator/AAOS source, provenance status, read-only AAOS UI, safe partial availability, and canonical conversions |
| Android background telemetry retry | Implemented and build verified | Unique per-vehicle WorkManager job, connected-network constraint, bounded exponential retry, lifecycle-independent queue flush, six policy tests, and manual process-death scenario |
| Android telemetry operator evidence | Implemented and build verified | Persistent rejected-event details, unchanged-identity retry, selective discard, attempt/exhaustion state, explicit recovery, five focused tests, and `CT-SHOW-009` |
| Administrative audit | Implemented | Immutable evidence, indexed bounded search, individual inspection, audited CSV export, and retention baseline |
| API error contract | Implemented | Application, HTTP, validation, and unexpected-error handlers |
| Reliable event publication | Implemented | Transactional outbox, resilient RabbitMQ startup, and publisher worker |
| Redis integration | Implemented | Readiness plus atomic expiring authentication and versioned-API rate-limit counters |
| Structured logging | Implemented | JSON logs with request correlation context |
| Container environment | Implemented and locally executed | One-shot migration, API, worker, PostgreSQL, Redis, and RabbitMQ services verified with Docker Compose |
| Automated verification | Implemented | 50 fast tests plus one expanded disposable black-box integration scenario, Ruff, strict mypy, and CI workflow |

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
- liveness and readiness probes;
- local container orchestration;
- engineering quality gates and verification evidence.

### 2.2 Outside the Current Increment

- automated immutable audit archival, restore verification, legal-hold workflow, and disposition tooling;
- proxy-aware client attribution and production rate-limit tuning;
- OpenTelemetry traces and Prometheus metrics;
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
| Observability foundation | Structured logs and correlation propagation | structlog |
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

**Consequences.** The current shared module secret is a development-stage workload mechanism and must be protected on the Android side; managed OAuth2 workload tokens or mTLS remain production follow-ups. REST is implemented first. WebSocket test-run updates, authorized command delivery, offline gateway buffering, and CarPropertyManager integration remain subsequent slices.

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
| Alembic migration chain | Passed | Revisions `0001` through `0007` applied successfully to a clean PostgreSQL database in the disposable Docker topology |
| Project metadata | Passed | `pyproject.toml` parsed successfully |
| Compose syntax | Passed | YAML loaded successfully |
| Application contract load | Passed | Authentication, health, identity, audit, module-registry, vehicle, and telemetry paths present in OpenAPI; bounded pagination and gateway headers confirmed |
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
| Android Vehicle Gateway build | Passed | CarSystemUI `showcase` produced a debug APK with the ATEP transport, persistent queue, status UI, and debug-only cleartext emulator policy |
| Android Vehicle Gateway and property-source unit suite | Passed | Nine tests verified gateway mapping/delivery plus simulator mutation, AAOS conversion, battery percentage, and unavailable-VHAL behavior |
| Android AAOS source build and lint | Passed | The standalone APK compiled its runtime CarPropertyManager compatibility bridge, required permission declarations, source provenance UI, and read-only AAOS mode without lint findings |
| Android WorkManager retry build and tests | Passed | WorkManager `2.11.2` resolved; scheduler, worker, unique-work policy, connectivity constraint, exponential backoff, eight-attempt bound, disabled-mode suppression, and six policy tests compiled and passed |
| Android rejected-event and exhaustion build and tests | Passed | Persistent inspection, atomic requeue, selective discard, attempt/exhaustion state, queue observation, explicit recovery, and five focused tests compiled and passed within the 18-test Android suite |
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

### 9.3 Evidence Limitations

The automated local run proves clean-database repeatability and the happy-path interaction among PostgreSQL, Redis, RabbitMQ, migrations, API, and publisher worker on one developer workstation. The CI workflow is defined but has not yet produced remote execution evidence. Broker/database outage recovery, sustained retry behavior, multi-replica limiter concurrency, production availability, latency objectives, security certification, and safety compliance remain unproven.

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
| OBS-001 | Validate structured log format. | Every log line is valid JSON with timestamp and level. | Planned / P1 |
| OBS-002 | Trace one correlation ID across request and outbox message. | The same ID is discoverable in API logs, database event, and broker envelope. | Planned / P0 |
| OBS-003 | Trigger an application exception. | Error is logged with safe context and correlation ID, without secrets. | Planned / P0 |
| OBS-004 | Detect an aging outbox backlog. | Metric or query crosses threshold and raises an alert. | Planned after metrics / P1 |
| OBS-005 | Validate readiness logging during dependency outage. | State change is diagnosable without excessive repetitive noise. | Planned / P2 |

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
| SECOPS-001 | Scan the repository for secrets. | No credential or private key is detected. | Planned / P0 |
| SECOPS-002 | Scan Python dependencies for known vulnerabilities. | No unaccepted critical/high vulnerability remains. | Planned / P0 |
| SECOPS-003 | Run static application security analysis. | Findings are triaged with owner and due date. | Planned / P1 |
| SECOPS-004 | Scan the container image and generate an SBOM. | Critical findings fail release; SBOM is retained with the artifact. | Planned / P0 |
| SECOPS-005 | Fuzz token and API input parsers. | Malformed input causes controlled 4xx responses and no crash. | Planned / P1 |
| SECOPS-006 | Review CORS, documentation exposure, headers, and TLS policy. | Production configuration matches the approved threat model. | Planned / P0 |
| SECOPS-007 | Attempt privilege escalation across RBAC boundaries. | No unauthorized operation or sensitive disclosure succeeds. | Planned / P0 |
| SECOPS-008 | Rotate the JWT secret in a staged environment. | Rotation procedure behaves as documented, including expected token invalidation. | Planned / P1 |

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
| Secret leakage | Environment-based secrets and ignored `.env` | Add secret manager, scanning, rotation runbooks, and log redaction tests |
| SQL injection | SQLAlchemy expression API and parameterization | Maintain code review and SAST; test any raw SQL explicitly |
| Event spoofing or tampering | Controlled exchange publication and message identity | Add broker TLS/mTLS, broker permissions, schema validation, and optional message signing |
| Message replay | Unique event IDs and documented idempotency | Implement consumer inbox/deduplication and retention policy |
| Dependency compromise | Version ranges and isolated image | Add lock file, SBOM, signature verification, and automated advisory scanning |
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
| R-008 | Dependency versions use ranges without a committed lock file. | Builds may change over time. | Adopt deterministic dependency locking and update automation. | Medium |
| R-009 | No telemetry metrics or distributed traces. | Performance and failure investigation remain log-centric. | Add OpenTelemetry and Prometheus instrumentation. | Medium |
| R-010 | No formal backup/restore evidence. | Data recovery capability is unknown. | Define RPO/RTO, automated backups, restore drills, and evidence retention. | High |
| R-011 | Rate limiting uses fixed windows and the direct network peer when no bearer credential is present. | Bursts near a window boundary may temporarily exceed the nominal rate; a shared reverse-proxy address may group unrelated clients. | Calibrate thresholds with load tests and implement a reviewed trusted-proxy attribution policy before public deployment. | High |
| R-012 | Shared-secret workload authentication and application-process reconciliation are implemented, but mTLS, per-instance identity, and multi-replica scheduler ownership are not. | Credential theft could permit module impersonation, and operational behavior under multiple independently scheduled API replicas is not yet evidenced. | Add secret-manager delivery, mTLS or managed workload identity, instance leases, reconciliation metrics, and explicit leader/scheduler ownership before dynamic routing. | Medium |

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
- authorized test-command delivery and WebSocket test updates — planned;
- vehicle/test configuration profiles;
- scheduler boundary and job lifecycle;
- object-storage abstraction for test artifacts;
- OpenTelemetry traces, Prometheus metrics, alerts, and dashboards.

### Increment 4 — Production Hardening

- Kubernetes deployment and workload identity;
- mTLS and secret-manager integration;
- backup, restore, retention, and disaster-recovery exercises;
- performance, resilience, and security baselines;
- signed artifacts and controlled promotion across environments.

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
| Vehicle catalogue and Android Automotive telemetry | `src/atep/vehicles/`, migration `0007_vehicle_telemetry.py`, vehicle API contracts, and `tests/test_vehicle_telemetry.py` |
| Android Vehicle Gateway, property sources, retry worker, and operator evidence | `CarSystemUI_android/showcase/app/.../gateway/`, `showcase/app/.../vehicle/`, Android unit tests, `docs/ATEP_VEHICLE_GATEWAY.md`, and `docs/TEST_CASE_CT_SHOW_006.md` through `docs/TEST_CASE_CT_SHOW_009.md` in the companion repository |
| Immutable audit model, query/export APIs, and recorder | `src/atep/audit/` |
| Event outbox and worker | `src/atep/events/` |
| Database migrations | `migrations/versions/0001_core_platform.py` through `0007_vehicle_telemetry.py` |
| Refresh-session implementation | `src/atep/identity/sessions.py`, identity models, schemas, and router |
| Local service topology | `compose.yaml` and `Dockerfile` |
| Disposable integration topology and runner | `compose.integration.yaml` and `tools/run_integration_tests.ps1` |
| Black-box integration scenario | `tests/integration/test_identity_flow.py` |
| Continuous integration workflow | `.github/workflows/integration.yml` |
| Automated tests | `tests/test_security.py`, `test_identity.py`, `test_user_administration.py`, `test_role_catalogue.py`, `test_audit_query.py`, `test_rate_limit.py`, `test_module_registry.py`, `test_vehicle_telemetry.py`, and `test_api_contract.py` |
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
