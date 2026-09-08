# Volume VIII Test Framework Engineering Workbook

Version 0.2.0 records the VIII-1 catalog and VIII-2 execution-binding baseline. It documents
architecture, contracts, lifecycle, RBAC, persistence, events, audit, deterministic case results,
aggregate run semantics, test objectives, risks, and study exercises.

## VIII-1 evidence

- Test definitions contain bounded metadata, preconditions, and structured steps.
- Suites accept only active definitions and snapshot their names and versions.
- Forward-only lifecycle changes use optimistic version checks.
- Exact creation replay is idempotent; conflicting identifier reuse returns stable HTTP 409 errors.
- `test_catalog:read` and `test_catalog:manage` separate catalog consumption from administration.
- Migration 0051 adds test definitions and suites after the completed ADAS migration history.
- Audit records and outbox events are written in the same database transaction as catalog changes.
- Focused tests, Ruff, mypy, full regression, hosted integration, and document QA provide evidence.

## VIII-2 outcome

VIII-2 binds active suite snapshots to test runs, materializes pending cases atomically, and records
bounded case-level outcomes. Required failures or skips fail the aggregate run; otherwise complete
runs pass. The existing authenticated run stream publishes the resulting progress and status.

## VIII-2 evidence

- Catalog-backed runs preserve suite identity, version, type, name, and ordered composition.
- Exact run replay remains idempotent after suite archival.
- Case transitions use optimistic versions and forward-only states.
- Attempts, duration, observed results, and evidence references have explicit bounds.
- Audit and outbox payloads retain evidence counts instead of raw evidence references.
- Migration 0052 adds optional run binding and uniquely constrained case-result records.

## Next increment

VIII-3 will connect scheduled jobs to catalog-suite selection for smoke, sanity, and regression runs.
