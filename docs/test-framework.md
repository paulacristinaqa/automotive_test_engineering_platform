# Test Framework

Volume VIII turns the existing execution infrastructure into a reusable test engineering system.
VIII-1 introduced the catalog, VIII-2 bound reviewed suites to deterministic case execution, and
VIII-3 connects those snapshots to the durable scheduler for smoke, sanity, and regression runs.
Performance, stress, fault injection, mutation testing, and coverage remain later increments.

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
- `POST /api/v1/test-jobs` accepts a catalog suite and matching smoke, sanity, or regression policy.
- `GET /api/v1/test-jobs` and `GET /api/v1/test-jobs/{job_id}` expose the immutable selection.

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

## Scheduled selection

A catalog-backed job requires `catalog_suite_id` and `selection_policy` together. The policy must
be smoke, sanity, or regression and must match both the run suite and the active catalog suite type.
This prevents a suite from being scheduled under misleading execution semantics.

The job freezes suite identity, version, type, tags, and ordered composition at scheduling time.
When the bounded background scheduler dispatches the job, it creates the run and pending case
results from that stored snapshot in the same transaction. It does not re-read mutable catalog
composition, so later archival cannot change scheduled intent. Jobs without a catalog binding keep
their existing behavior for backward compatibility.

## Security and cost

Read operations require `test_catalog:read`; mutations require `test_catalog:manage`. Payload and
collection bounds protect database, API, and future executor resources. The implementation runs
locally and requires no GPU, paid cloud service, or paid AI API.
