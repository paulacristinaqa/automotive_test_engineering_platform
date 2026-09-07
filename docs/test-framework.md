# Test Framework

Volume VIII turns the existing execution infrastructure into a reusable test engineering system.
VIII-1 introduces the catalog that defines what a test does and how tests are grouped. Execution,
scheduling, regression selection, fault injection, mutation testing, and coverage build on this
versioned catalog in later increments.

## API

- `POST /api/v1/test-definitions` creates an idempotent draft definition.
- `GET /api/v1/test-definitions` lists definitions with bounded pagination and status filtering.
- `GET /api/v1/test-definitions/{definition_id}` reads one definition.
- `PATCH /api/v1/test-definitions/{definition_id}/status` activates or archives a definition.
- `POST /api/v1/test-suites` creates an idempotent suite from active definitions.
- `GET /api/v1/test-suites` and `GET /api/v1/test-suites/{suite_id}` expose suite snapshots.
- `PATCH /api/v1/test-suites/{suite_id}/status` controls the suite lifecycle.

## Composition model

A definition owns domain, level, automation mode, timeout, tags, preconditions, and one to one
hundred structured steps. A suite contains one to two hundred unique definitions with explicit,
unique order values, a required flag, and bounded parameter overrides. Suite creation captures the
definition name and version so later definition lifecycle changes cannot rewrite historical intent.

Only active definitions can enter a suite. Both resources follow `draft -> active -> archived`, use
optimistic version checks, and never transition backwards. Creation and lifecycle changes write
audit and transactional outbox evidence atomically.

## Security and cost

Read operations require `test_catalog:read`; mutations require `test_catalog:manage`. Payload and
collection bounds protect database, API, and future executor resources. The implementation runs
locally and requires no GPU, paid cloud service, or paid AI API.
