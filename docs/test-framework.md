# Test Framework

Volume VIII turns the existing execution infrastructure into a reusable test engineering system.
VIII-1 introduced the catalog that defines what a test does and how tests are grouped. VIII-2 binds
an active suite to the existing test-run lifecycle, freezes its reviewed composition, and records
deterministic case results. Scheduling, regression selection, fault injection, mutation testing,
and coverage build on this execution boundary in later increments.

## API

- `POST /api/v1/test-definitions` creates an idempotent draft definition.
- `GET /api/v1/test-definitions` lists definitions with bounded pagination and status filtering.
- `GET /api/v1/test-definitions/{definition_id}` reads one definition.
- `PATCH /api/v1/test-definitions/{definition_id}/status` activates or archives a definition.
- `POST /api/v1/test-suites` creates an idempotent suite from active definitions.
- `GET /api/v1/test-suites` and `GET /api/v1/test-suites/{suite_id}` expose suite snapshots.
- `PATCH /api/v1/test-suites/{suite_id}/status` controls the suite lifecycle.
- `POST /api/v1/test-runs` accepts an optional active `catalog_suite_id` and creates pending cases.
- `GET /api/v1/test-runs/{run_id}/cases` returns ordered results with bounded pagination.
- `PATCH /api/v1/test-runs/{run_id}/cases/{case_id}` records a versioned case transition.

## Composition model

A definition owns domain, level, automation mode, timeout, tags, preconditions, and one to one
hundred structured steps. A suite contains one to two hundred unique definitions with explicit,
unique order values, a required flag, and bounded parameter overrides. Suite creation captures the
definition name and version so later definition lifecycle changes cannot rewrite historical intent.

Only active definitions can enter a suite. Both resources follow `draft -> active -> archived`, use
optimistic version checks, and never transition backwards. Creation and lifecycle changes write
audit and transactional outbox evidence atomically.

## Execution binding

A catalog-backed run snapshots the suite identifier, name, type, version, and ordered case
composition. The database materializes each case as pending in the same transaction as the run,
audit record, and creation event. A suite must be active for a new run. Exact retries remain
idempotent after later suite archival because the existing run snapshot is authoritative.

Case results move from pending to running or skipped, and from running to passed, failed, or
skipped. Each accepted transition records an attempt number, optional terminal duration, a bounded
observed result, and up to twenty evidence references. Raw evidence stays in the artifact store;
events and audits expose only a count. Required failure or skip fails the run after all cases become
terminal. Otherwise the run passes. Every accepted case transition updates progress and the
existing authenticated WebSocket projection. Direct status updates may cancel a catalog-backed run,
but case results exclusively derive its running, passed, and failed states.

## Security and cost

Read operations require `test_catalog:read`; mutations require `test_catalog:manage`. Payload and
collection bounds protect database, API, and future executor resources. The implementation runs
locally and requires no GPU, paid cloud service, or paid AI API.
