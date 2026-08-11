# Volume I requirements

## Functional requirements

| ID | Requirement | Initial verification |
|---|---|---|
| CORE-F-001 | The platform shall authenticate an active user and issue a time-limited token. | API test |
| CORE-F-002 | The platform shall authorize operations using role permissions. | Unit/API test |
| CORE-F-003 | The platform shall persist identity and outbox state in PostgreSQL. | Automated Docker integration test |
| CORE-F-004 | The platform shall publish versioned domain events to RabbitMQ. | Automated Docker integration test |
| CORE-F-005 | The platform shall expose liveness and dependency readiness. | API test |
| CORE-F-006 | The platform shall attach a correlation ID to requests and responses. | API test |
| CORE-F-007 | The platform shall create the first administrator only from explicit bootstrap configuration. | Automated Docker integration test |
| CORE-F-008 | An authorized administrator shall create, list, inspect, activate, and deactivate users and manage their role assignments. | API/service test |
| CORE-F-009 | Security-relevant identity changes shall create immutable audit records containing actor, action, resource, correlation, and non-sensitive details. | Service/database test |
| CORE-F-010 | User creation shall persist the user and `atep.identity.user.created.v1` outbox event atomically. | Automated Docker integration test |
| CORE-F-011 | API failures shall use one stable error envelope with a correlation identifier. | API contract test |
| CORE-F-012 | Successful authentication shall issue a short-lived access token and a longer-lived opaque refresh token. | Automated Docker integration test |
| CORE-F-013 | Refresh-token use shall atomically invalidate the presented token and issue a new token pair. | Automated Docker integration test |
| CORE-F-014 | Reuse of a rotated refresh token shall revoke every active token in the same family. | Automated Docker integration test |
| CORE-F-015 | A user shall revoke one refresh-token family or all of their renewable sessions. | Automated Docker integration test |
| CORE-F-016 | An authorized administrator shall list, create, inspect, update, and safely delete roles and manage their permission grants. | API/service and automated Docker integration test |
| CORE-F-017 | The platform shall protect the `platform-admin` role from renaming, permission removal, and deletion, and reject deletion of roles assigned to users. | Negative API and automated Docker integration test |
| CORE-F-018 | An authorized investigator shall search and inspect immutable audit records using bounded pagination and indexed filters, while a separately authorized user may export a bounded CSV whose creation is itself audited. | API, service, and automated Docker integration test |
| CORE-F-019 | The platform shall enforce distributed Redis-backed limits for authentication and versioned API requests and return stable retry metadata when a limit is exceeded. | Unit and automated Docker integration test |
| CORE-F-020 | An authorized administrator shall register, inspect, page, filter, and update ATEP modules and declare or remove their versioned capabilities. | API, service, and automated Docker integration test |
| CORE-F-021 | Module registration and effective catalogue mutations shall append correlated immutable audit evidence and versioned transactional outbox events. | Service/database and automated Docker integration test |
| CORE-F-022 | An authorized administrator shall issue or rotate a module workload credential whose raw value is returned once and whose SHA-256 digest is the only persisted representation. | Service and automated Docker integration test |
| CORE-F-023 | An authenticated module shall renew a bounded availability lease through heartbeat, while automatic reconciliation shall mark an expired module inactive and record the transition. | Unit, API contract, and automated Docker integration test |
| CORE-F-024 | An authorized administrator shall register, list, inspect, activate, and deactivate canonical vehicle records through versioned APIs. | Service and API contract test |
| CORE-F-025 | An authenticated Vehicle Gateway declaring `vehicle.telemetry.publish` shall submit timezone-aware vehicle observations without direct access to platform infrastructure. | Unit, negative, API contract, and automated Docker integration test |
| CORE-F-026 | Telemetry persistence and `atep.vehicle.telemetry.received.v1` outbox creation shall be atomic. | Service/database and automated Docker integration test |
| CORE-F-027 | Repeating the same telemetry event shall not duplicate state or events; reusing its identifier with different data shall return a stable conflict. | Positive retry, negative conflict, and automated Docker integration test |
| CORE-F-028 | The Android Vehicle Gateway shall persist changed simulated properties before delivery and reuse the original event identifier and timestamp after a temporary failure. | Android unit tests and manual end-to-end test `CT-SHOW-006` |
| CORE-F-029 | The Android showcase shall expose gateway disabled, synchronized, pending, and rejected states without displaying workload credentials. | Android build verification and manual UI test `CT-SHOW-006` |
| CORE-F-030 | The Android showcase shall obtain canonical vehicle state through a replaceable `VehiclePropertySource` supporting both deterministic simulation and read-only AAOS `CarPropertyManager` observations. | Android source-contract and mapping unit tests |
| CORE-F-031 | Explicit AAOS mode shall report inaccessible or unsupported VHAL properties and shall never silently replace them with simulated observations. | Negative Android unit test and manual AAOS test `CT-SHOW-007` |
| CORE-F-032 | Pending Android telemetry shall reconcile to one persistent background job per vehicle, run only with connectivity, retain queue order and event identity, and use bounded exponential retry. | Android retry-policy tests and manual process-death test `CT-SHOW-008` |
| CORE-F-033 | The Android showcase shall expose rejected telemetry and exhausted background delivery, retain non-sensitive event evidence across process restart, and allow one selected event to be retried with unchanged identity or discarded. | Android gateway-operation tests and manual operator test `CT-SHOW-009` |
| CORE-F-034 | An operator with `vehicle_commands:write` shall idempotently request a bounded `set_property` command for one vehicle and one capability-authorized target module. | Service, RBAC, validation, API contract, and automated Docker integration test |
| CORE-F-035 | An authenticated module declaring `vehicle.commands.consume` shall atomically claim one available command under a bounded lease and acknowledge it using a claim token whose digest is the only persisted representation. | Service, negative claim, lease-expiry, and automated Docker integration test |
| CORE-F-036 | The Android Vehicle Gateway shall execute only allowlisted simulator properties, reject invalid or unsafe state transitions, refuse mutation of a read-only AAOS source, and return a terminal acknowledgement to ATEP. | Android command-executor/coordinator tests and manual end-to-end test `CT-SHOW-010` |
| CORE-F-037 | An operator with `test_runs:write` shall create an idempotent, vehicle-scoped test run and retrieve it through bounded, permission-protected queries. | Service tests and automated Docker integration test |
| CORE-F-038 | Test-run creation and each effective status transition shall atomically persist immutable audit evidence and a versioned transactional outbox event. | Service and automated Docker integration test |
| CORE-F-039 | Test runs shall follow the controlled `queued` to `running` to terminal lifecycle and reject stale versions or illegal transitions with stable conflicts. | Validation, transition, idempotency, and automated Docker integration tests |
| CORE-F-040 | An active user with `test_runs:read` shall receive an authoritative snapshot and versioned live updates over an authenticated WebSocket without direct infrastructure access. | Authenticated Redis/WebSocket Docker integration test |
| CORE-F-041 | CarSystemUI shall display the configured test run, connection state, progress, summary, and version; ignore duplicate or out-of-order updates; and reconnect with bounded backoff. | Android unit tests, lint, and debug build |
| CORE-F-042 | An operator with `environment_profiles:manage` shall idempotently create a bounded vehicle/test environment profile, while `environment_profiles:read` independently protects discovery. | Service, RBAC, validation, and API contract tests |
| CORE-F-043 | Environment profiles shall follow the immutable `draft` to `active` to `archived` lifecycle and reject stale versions or invalid transitions with stable conflicts. | State, optimistic-version, and negative service tests |
| CORE-F-044 | Profile creation and each effective lifecycle transition shall atomically persist immutable audit evidence and a versioned transactional outbox event. | Service and database integration tests |
| CORE-F-045 | A test run may reference only an active environment profile and shall retain the profile identifier, version, vehicle kind, property source, and configuration snapshot used at creation. | Service, snapshot, and reproducibility tests |
| CORE-F-046 | An operator with `test_jobs:manage` shall idempotently schedule a vehicle-scoped test job for a timezone-aware instant and discover it through independently protected bounded queries. | Validation, service, RBAC, OpenAPI, and Docker integration tests |
| CORE-F-047 | A scheduled job may be cancelled exactly once before dispatch using optimistic version control; dispatched jobs shall reject cancellation with a stable state conflict. | Lifecycle, idempotency, stale-version, and negative tests |
| CORE-F-048 | The scheduler shall atomically claim due jobs using row locks that skip work owned by another instance, create one queued TestRun, and mark the job dispatched. | Service query review and multi-instance database integration test |
| CORE-F-049 | Scheduling, cancellation, and dispatch shall append versioned transactional outbox events and immutable audit evidence in the same unit of work as their state changes. | Unit and automated Docker integration test |
| CORE-F-050 | An operator with `test_artifacts:write` shall upload a bounded immutable artifact to an existing TestRun, while `test_artifacts:read` independently protects metadata and content retrieval. | Service, RBAC, multipart API, and Docker integration tests |
| CORE-F-051 | Repeating an artifact upload with the same run, identifier, metadata, size, and SHA-256 shall return the original record without duplicate evidence; conflicting reuse shall return a stable error. | Idempotency, conflict, and database uniqueness tests |
| CORE-F-052 | Artifact metadata, `atep.test_artifact.stored.v1`, and immutable audit evidence shall be committed atomically after object storage succeeds. | Unit and automated Docker integration test |
| CORE-F-053 | Artifact downloads shall preserve the stored media type and filename and expose authoritative size, ETag, and SHA-256 integrity metadata without disclosing the internal object key. | Contract, security, and download integration tests |
| CORE-F-054 | When metrics are enabled, the platform shall expose Prometheus request count, duration, in-progress, exception, process, and build information through an internal scrape endpoint. | Unit, contract, and Docker integration tests |
| CORE-F-055 | Every HTTP request shall create a server trace context, honor a valid W3C `traceparent`, and return the effective trace identifier in `X-Trace-ID`. | Propagation and Docker integration tests |
| CORE-F-056 | Structured request logs and server spans shall carry the ATEP correlation identifier, trace identifier, and span identifier without recording credentials or request bodies. | Unit test and structured-log inspection |
| CORE-F-057 | Operators shall configure trace recording, parent-based sample ratio, service identity, and OTLP/HTTP export exclusively through validated environment settings. | Configuration and exporter tests |
| CORE-F-058 | The repository shall provide an optional, version-pinned Collector, Prometheus, and Grafana topology with provisioned datasource and dashboard assets. | Compose validation and dashboard contract tests |
| CORE-F-059 | An authorized operator shall retrieve a bounded aggregate health summary for credentialed modules without exposing workload credentials or unbounded module identifiers. | Service, RBAC, OpenAPI, and integration tests |
| CORE-F-060 | The registry reconciler shall publish bounded module status, availability, lease-risk, heartbeat, expiry, and reconciliation-failure metrics. | Unit and metrics contract tests |
| CORE-F-061 | Prometheus shall evaluate versioned recording rules for API availability, error ratios, and p95 latency. | Rule asset test and `promtool` CI validation |
| CORE-F-062 | Prometheus shall raise severity-labelled, runbook-linked alerts for fast/slow error-budget burn, excessive latency, unavailable/degraded modules, and leases at risk. | Alert contract test and `promtool` CI validation |
| CORE-F-063 | The outbox worker shall expose an internal Prometheus endpoint reporting bounded publication outcomes, batch duration, unpublished count, oldest-event age, process state, and worker state. | Unit, cardinality, Prometheus scrape, and Docker integration tests |
| CORE-F-064 | The test scheduler shall report dispatched count, cycle failures/duration, due-job count, and oldest-due age from constant-size database aggregates. | Unit, metrics contract, and Docker integration tests |
| CORE-F-065 | Test-run live delivery shall report bounded connection outcomes, active connections, message kinds, and Redis publication outcomes without run, user, or vehicle identifiers. | Unit, cardinality, WebSocket, and Docker integration tests |
| CORE-F-066 | Prometheus shall raise runbook-linked alerts for an unavailable outbox worker, old outbox or scheduler backlog, and failed outbox, scheduler, or live-update publication. | Alert contract and `promtool` CI validation |
| CORE-F-067 | Prometheus shall deliver firing and resolved alerts to a version-pinned Alertmanager using reviewed grouping intervals. | Compose, Prometheus, Alertmanager, and CI delivery tests |
| CORE-F-068 | Alertmanager shall route critical and warning alerts to an internal development webhook and inhibit warnings while a critical alert for the same service is firing. | Configuration contract and `amtool` validation |
| CORE-F-069 | The development webhook shall validate bounded Alertmanager payloads and expose only aggregate severity/status counters without retaining labels, annotations, or domain identifiers. | Positive, negative-cardinality, API, and live-delivery tests |
| CORE-F-070 | Readiness shall publish duration, result, and current-state metrics for PostgreSQL, Redis, and RabbitMQ using only reviewed dependency and outcome labels. | Unit, cardinality, readiness, and Docker integration tests |
| CORE-F-071 | The artifact-store boundary shall report bounded operation outcomes, duration, bytes read/written, and optional capacity without exposing object keys or evidence identifiers. | Decorator, filesystem, cardinality, and integration tests |
| CORE-F-072 | Prometheus shall raise runbook-linked alerts for persistent dependency unavailability, artifact-store operation failures, and low free capacity. | Alert contract and `promtool` CI validation |
| CORE-F-073 | Runtime and development Python dependency graphs, including build requirements, shall be committed as deterministic manifests with SHA-256 hashes. | Lock regeneration and policy tests |
| CORE-F-074 | Security CI shall scan repository history, Python dependencies, Python source, and the built container image and shall retain machine-readable CycloneDX SBOM evidence. | Gitleaks, pip-audit, CodeQL, Syft, and Grype workflow evidence |
| CORE-F-075 | Third-party CI actions and the runtime base image shall use immutable identifiers, with reviewed weekly update proposals for Python, Actions, and Docker inputs. | Policy tests and Dependabot configuration review |
| CORE-F-076 | The repository shall provide separately renderable Kubernetes foundation, migration, and workload targets so schema migration is explicitly completed before application rollout. | Kustomize render and policy tests |
| CORE-F-077 | Kubernetes workloads shall consume non-sensitive configuration from a ConfigMap and credentials only from a named Secret materialized by an approved external secret provider. | Manifest policy and secret-contract review |
| CORE-F-078 | The Kubernetes API and outbox worker shall expose bounded liveness/readiness evidence and run with explicit resource, storage, identity, and network controls. | Manifest policy, render, and staged smoke tests |
| CORE-F-079 | A registered module shall authenticate heartbeat, telemetry, and command operations with one canonical SPIFFE ID forwarded by an approved mTLS proxy while existing capability authorization remains enforced. | Parser, authentication, capability, API-contract, and future live proxy tests |
| CORE-F-080 | The repository shall provide a bounded PostgreSQL logical backup and isolated restore drill that validates archive readability, Alembic revision, schema, and per-table row counts. | Pure unit tests, workflow policy tests, and disposable CI restore evidence |
| CORE-F-081 | A successful restore drill shall retain a versioned aggregate evidence report containing timestamps, duration, archive integrity, migration revision, and fingerprints without retaining the database archive or domain records. | Report contract, privacy test, and CI artifact review |

## Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| CORE-NF-001 | API availability | 99.9% after production deployment |
| CORE-NF-002 | API latency | p95 under 250 ms excluding long-running test operations |
| CORE-NF-003 | Event delivery | at-least-once with retry and idempotent consumers |
| CORE-NF-004 | Security | Argon2 credentials, least privilege, no committed secrets |
| CORE-NF-005 | Observability | structured logs and end-to-end correlation IDs |
| CORE-NF-006 | Maintainability | module boundaries, typed code, automated lint/test gates |
| CORE-NF-007 | Data protection | passwords and password hashes never appear in API responses, event payloads, audit details, or application logs |
| CORE-NF-008 | Integration repeatability | isolated ports, ephemeral credentials, disposable data, automatic cleanup, and CI execution |
| CORE-NF-009 | Refresh-token protection | raw refresh tokens are returned once, only SHA-256 hashes are persisted, and security actions are audited without token material |
| CORE-NF-010 | Role-catalogue integrity | role names are canonical and unique, mutations are auditable, pagination is bounded, and protected-role invariants cannot be bypassed through the API |
| CORE-NF-011 | Audit evidence lifecycle | audit records remain immutable, are retained online for at least 365 days, are archived for at least seven years unless policy requires longer, and are never purged while subject to legal hold |
| CORE-NF-012 | Abuse-control consistency | rate-limit counters are atomic, expire automatically, store no raw email, address, or credential, and fail closed with a controlled response when Redis is unavailable |
| CORE-NF-013 | Module-catalogue integrity | module and capability names are canonical and unique in scope, versions follow semantic-version syntax, pagination is bounded, and read/manage permissions are independent |
| CORE-NF-014 | Operational-registry integrity | raw workload credentials never enter persistence or evidence, operational states are heartbeat-controlled, leases are bounded, and expiry transitions are evented and audited |
| CORE-NF-015 | Automotive integration isolation | Android clients communicate only through public ATEP APIs; PostgreSQL, Redis, and RabbitMQ remain inaccessible to CarSystemUI and the Vehicle Gateway |
| CORE-NF-016 | Telemetry interoperability | property names and event identifiers are canonical, timestamps are timezone-aware, contracts are published in OpenAPI, and retries are idempotent |
| CORE-NF-017 | Gateway resilience | pending telemetry survives Android process restart, delivery preserves queue order, permanent client rejections are bounded, and temporary failures remain retryable |
| CORE-NF-018 | Evidence provenance | the UI identifies simulator versus AAOS origin, disables local mutation for AAOS observations, and preserves unit conversions defined by the canonical source adapter |
| CORE-NF-019 | Background delivery control | retry work is unique per vehicle, persists beyond the activity lifecycle, requires connectivity, remains inactive for disabled configuration, and stops after eight worker attempts |
| CORE-NF-020 | Telemetry disposition safety | exhausted work does not restart silently; retry preserves event identity; discard affects only the selected rejected record; credentials never enter operator evidence |
| CORE-NF-021 | Command-delivery safety | commands are target-scoped, leased, idempotent, allowlisted, bounded by vehicle-state invariants, and acknowledged without persisting raw claim tokens |
| CORE-NF-022 | Live test-run consistency | PostgreSQL and the transactional outbox remain authoritative; row-locked optimistic transitions prevent lost updates; Redis Pub/Sub is a best-effort projection; clients deduplicate by monotonically increasing version |
| CORE-NF-023 | Test reproducibility | environment configurations are JSON-compatible and limited to 16 KiB; active profiles are immutable; every associated test run retains a versioned configuration snapshot independent of later archival |
| CORE-NF-024 | Scheduler consistency | due work is selected oldest-first in bounded batches with `FOR UPDATE SKIP LOCKED`; job state, generated TestRun, audit, and outbox evidence commit or roll back together |
| CORE-NF-025 | Artifact integrity | content is streamed through a configurable 1-byte to 1-GiB bound, hashed with SHA-256, stored under an internally generated key, and treated as immutable |
| CORE-NF-026 | Storage isolation | client filenames never become filesystem paths; storage adapters reject root escape; object keys remain absent from public API, audit, and event contracts |
| CORE-NF-027 | Metric cardinality | HTTP labels use bounded method, route-template, status, and exception-type values; raw paths, query strings, vehicle/user IDs, emails, filenames, and credentials are forbidden |
| CORE-NF-028 | Observability isolation | metrics, Grafana, Prometheus, Collector, and OTLP ports are internal-only deployment surfaces; production transport requires TLS and workload authentication |
| CORE-NF-029 | Telemetry overhead | tracing can be disabled or sampled from 0.0 to 1.0; export is batched with bounded Collector memory; observability failures must not change authoritative business state |
| CORE-NF-030 | SLO policy as code | API availability uses a 99.9% target, module snapshot availability uses a configurable target, and all recording/alert rules are versioned and CI-validated |
| CORE-NF-031 | Alert safety | alerts use bounded labels, explicit severities, minimum persistence windows, and a runbook reference; they never include credentials or domain identifiers |
| CORE-NF-032 | Health aggregation | module health queries use database aggregation with constant-size responses and consider only modules issued a workload credential |
| CORE-NF-033 | Domain metric cardinality | outbox, scheduler, and WebSocket metrics use only fixed outcomes/message kinds or no labels; event, run, user, vehicle, and job identifiers are forbidden |
| CORE-NF-034 | Worker telemetry isolation | the outbox metrics server is internal-only, uses a dedicated registry/port, and metric failure cannot change transactional event state |
| CORE-NF-035 | Backlog measurement | outbox and scheduler lag derive from constant-size count/minimum-time queries and never load or label individual records |
| CORE-NF-036 | Alert delivery isolation | Alertmanager and webhook host ports bind only to loopback; the receiver configuration contains no external destinations or credentials |
| CORE-NF-037 | Notification cardinality | receiver metric labels are restricted to critical, warning, info, unknown and firing/resolved; arbitrary incoming values never become labels |
| CORE-NF-038 | Alert lifecycle | resolved notifications are enabled, repeat/group intervals are bounded, and critical alerts inhibit warnings only within the same service |
| CORE-NF-039 | Dependency metric cardinality | dependency labels are restricted to postgres, redis, and rabbitmq; outcomes are ready or unavailable |
| CORE-NF-040 | Storage metric privacy | operation labels are fixed; object keys, filenames, artifact/run identifiers, endpoints, and exception messages are forbidden |
| CORE-NF-041 | Observability non-interference | capacity refresh and metric recording must not change object persistence, transaction success, or dependency readiness semantics |
| CORE-NF-042 | Build reproducibility | Linux x86-64/Python 3.14 is the canonical lock platform; Python 3.12 remains the tested minimum; identical reviewed manifests install the same dependency artifacts and reject absent or mismatched hashes |
| CORE-NF-043 | CI least privilege | workflow permissions are read-only by default, elevated only per job, and third-party actions are pinned to full commit SHAs |
| CORE-NF-044 | Vulnerability evidence | Python and image SBOMs are retained for 14 days; known high or critical image vulnerabilities fail CI unless a documented, time-bounded exception is reviewed |
| CORE-NF-045 | Kubernetes least privilege | restricted Pod Security, non-root execution, RuntimeDefault seccomp, dropped capabilities, read-only root filesystems, no privilege escalation, and no automatic ServiceAccount token mounting |
| CORE-NF-046 | Deployment secret isolation | no Kubernetes Secret values are committed; the required `atep-runtime-secrets` object is externally materialized and bootstrap credentials are removed after first use |
| CORE-NF-047 | Deployment immutability | migration and workload overlays use the same reviewed application manifest digest; the committed zero digest prevents accidental deployment before release substitution |
| CORE-NF-048 | Deployment ordering | the bounded migration Job completes and its evidence is retained before singleton API and worker workloads are applied; database downgrade is never automatic |
| CORE-NF-049 | Kubernetes network isolation | default-deny ingress/egress is combined with explicit DNS, dependency-port, API-client, and metrics-client allowances on a policy-capable CNI |
| CORE-NF-050 | Forwarded identity integrity | XFCC is accepted only from configured direct-peer CIDRs, must contain exactly one canonical SPIFFE module URI, and any presented invalid identity fails without token downgrade |
| CORE-NF-051 | Workload-identity migration safety | Trusted-proxy identity is disabled by default; the legacy hash-only token remains valid only when XFCC is absent, and production enablement requires proxy sanitization, mTLS validation, and direct-path denial |
| CORE-NF-052 | Backup secret isolation | Database credentials remain in the PostgreSQL service environment and must not appear in process arguments, reports, logs, or retained CI artifacts |
| CORE-NF-053 | Restore evidence integrity | The dump is non-empty and SHA-256 identified; restore fails on the first database error; revision, ordered schema, and every public-table count must match |
| CORE-NF-054 | Recovery isolation | Restore targets a randomly named empty database created from `template0`, application writers are quiesced for exact comparison, and temporary archive/database state is removed |
| CORE-NF-055 | Recovery objectives | Initial database targets are RPO 24 hours and RTO 4 hours until business impact analysis and deployed provider exercises establish approved values |
