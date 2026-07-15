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
- configuration profiles for vehicle and test environments
- scheduler boundary and job lifecycle
- object storage abstraction for test artefacts
- OpenTelemetry traces, Prometheus metrics, and dashboards

## Increment 4 — production hardening

- Kubernetes manifests and secret-manager integration
- mTLS and workload identity
- backup, restore, retention, and disaster-recovery exercises
- SLOs, alerts, load tests, and security scanning
- CI/CD promotion through development, staging, and production

The Volume I exit criterion is a repeatable deployment that supports the first end-to-end
BMS/CAN/DTC/test event flow without changing its core security or event model.
