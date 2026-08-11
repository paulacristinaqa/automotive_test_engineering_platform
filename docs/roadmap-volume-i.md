# Volume I delivery roadmap

## Increment 1 — executable foundation (completed)

- control-plane API and configuration
- identity schema, authentication, and RBAC primitives
- PostgreSQL migration
- transactional outbox and RabbitMQ worker
- Redis/RabbitMQ/PostgreSQL development stack
- health endpoints, correlation IDs, and structured logs

## Increment 2 — administration and audit (in progress)

- user creation, retrieval, safe pagination, and status management (completed)
- role assignment and removal with `roles:manage` protection (completed)
- global error envelope and validation mapping (completed)
- immutable administrative audit records (completed initial slice)
- atomic user-created outbox event (completed)
- refresh-token rotation, reuse detection, session revocation, and logout (completed)
- role catalogue administration with protected-role invariants and auditable permission grants (completed)
- audit query, bounded export, and retention policy (completed; archive automation remains a production-hardening activity)
- Redis-backed authentication and versioned-API rate limiting (completed; proxy-aware client attribution and load tuning remain production hardening)
- database and broker integration tests (completed with disposable local/CI topology)

## Increment 3 — platform services (in progress)

- service registry and module capability catalogue (completed)
- authenticated module heartbeat, bounded availability leases, credential rotation, and automatic expiry reconciliation (completed)
- vehicle catalogue and capability-protected idempotent Android Automotive telemetry ingestion (completed initial integration slice)
- connect the CarSystemUI showcase Vehicle Gateway to the telemetry API (completed initial slice: changed-property mapping, persistent queue, retry, status UI, and Android unit tests)
- isolate vehicle data behind `VehiclePropertySource` and add a read-only CarPropertyManager/VHAL adapter (completed initial AAOS slice: source selection, provenance UI, safe partial availability, conversion tests, and no silent simulator fallback)
- replace activity-driven retry with unique connectivity-constrained WorkManager delivery (implemented and build verified; live `CT-SHOW-008` evidence pending)
- add rejected-event inspection, idempotent retry, selective discard, and retry-exhaustion visibility (implemented and build verified; live `CT-SHOW-009` evidence pending)
- add area-aware door/seat mapping and migrate the AOSP platform build to typed `subscribePropertyEvents` (planned)
- command delivery from authorized test runs to the simulated vehicle source (implemented and verified by live `CT-SHOW-010`: idempotent request, target capability, lease recovery, safe allowlist, terminal acknowledgement, Android polling, and AAOS read-only rejection)
- persistent test-run lifecycle and WebSocket status updates for CarSystemUI (implemented and verified: RBAC, idempotent creation, optimistic transitions, audit/outbox atomicity, Redis Pub/Sub, authenticated snapshot/update stream, Android deduplication and reconnect UI)
- configuration profiles for vehicle and test environments (implemented initial backend slice: EV/hybrid/autonomous type, simulator/AAOS source, bounded configuration, independent RBAC, immutable lifecycle, audit/outbox, and TestRun snapshot)
- scheduler boundary and job lifecycle (implemented initial slice: persistent idempotent jobs, independent RBAC, optimistic cancellation, bounded multi-instance-safe due selection, atomic TestRun dispatch, audit, and outbox)
- object storage abstraction for test artefacts (implemented initial slice: immutable TestRun evidence, streaming filesystem adapter, replaceable store interface, SHA-256 integrity, independent RBAC, bounded multipart upload, download, audit, and outbox)
- OpenTelemetry traces, Prometheus metrics, and dashboards (implemented initial slice: W3C trace propagation, correlated IDs, bounded HTTP metrics, OTLP/HTTP export, optional Collector/Prometheus/Grafana topology, and versioned overview dashboard)
- module health aggregation, SLO recording rules, and burn-rate/registry alerts (implemented initial slice; production notification routing, load evidence, and threshold calibration remain hardening)
- outbox, scheduler, and WebSocket domain metrics with backlog/failure alerts (implemented initial slice; production capacity thresholds and notification routing remain hardening)
- local Alertmanager grouping/inhibition and aggregate-only delivery receiver (implemented; production provider routing, ownership, escalation, and secret management remain hardening)
- bounded dependency readiness and artifact-store operation/capacity metrics with alerts (implemented; database-pool and provider-specific saturation remain hardening)
- deterministic dependency locks, immutable build inputs, secret/dependency/source/image scanning,
  CycloneDX SBOM evidence, and automated update proposals (implemented supply-chain baseline;
  signing and verifiable provenance remain hardening)

## Increment 4 — production hardening

- Kubernetes manifests and vendor-neutral external secret-manager contract (implemented initial
  foundation/migration/workload slice; real release digest, provider binding, ingress/TLS, staged
  evidence, and multi-replica leadership remain hardening)
- application-side SPIFFE/XFCC workload identity boundary (implemented initial slice: exact
  module identity, trusted proxy CIDRs, fail-closed parsing, capability preservation, and token
  migration path; proxy deployment, certificate lifecycle, direct-path denial, and live mTLS
  evidence remain hardening)
- PostgreSQL logical backup, isolated restore, aggregate integrity evidence, and initial RPO/RTO
  policy (implemented initial CI slice; provider-native encrypted backup, immutable retention,
  artifact-store coordination, PITR/WAL, and deployed disaster exercises remain hardening)
- SLO threshold calibration, production incident-provider routing, load tests, artifact signing,
  provenance verification, and security-policy calibration (signed GHCR provenance/SBOM and
  pre-promotion verification implemented as an initial hosted-build slice; trusted reusable
  builder, live release evidence, admission enforcement, and long-term retention remain)
- CI/CD promotion through development, staging, and production (implemented initial validation
  slice: ordered fixed environments, strict immutable inputs, fail-closed enablement, retained
  manifest evidence, production approval contract, and signed provenance verification; real
  provider deployment remains hardening)

The Volume I exit criterion is a repeatable deployment that supports the first end-to-end
BMS/CAN/DTC/test event flow without changing its core security or event model.
