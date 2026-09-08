# Volume VIII Test Framework Requirements

## VIII-1 Test definitions and suite composition

- **TF-F-001** Create reusable test definitions with stable URL-safe identifiers.
- **TF-F-002** Classify definitions by domain, test level, and automation mode.
- **TF-F-003** Define bounded preconditions and structured action, target, input, and expected-result steps.
- **TF-F-004** Create smoke, sanity, regression, performance, stress, and safety suites.
- **TF-F-005** Compose suites from unique active definitions with explicit unique execution order.
- **TF-F-006** Snapshot definition name and version in every suite composition.
- **TF-F-007** Support draft, active, and archived forward-only lifecycles with optimistic locking.
- **TF-F-008** Provide create, detail, filtered list, and status APIs for definitions and suites.
- **TF-F-009** Make exact creation replay idempotent and conflicting identifier reuse stable.
- **TF-F-010** Atomically record audit and outbox evidence for accepted mutations.
- **TF-F-011** Protect reads with `test_catalog:read` and mutations with `test_catalog:manage`.
- **TF-NF-001** Limit definition steps to 100 and suite cases to 200.
- **TF-NF-002** Limit pagination to 100 and offsets to 1,000,000.
- **TF-NF-003** Limit test timeout to 86,400 seconds and parameter JSON to 8,192 bytes per case.
- **TF-NF-004** Preserve suite intent independently from later definition lifecycle changes.
- **TF-NF-005** Run without GPU, paid cloud, or paid AI dependencies.

## VIII-2 Suite execution and case results

- **TF-F-012** Create a test run from an active catalog suite while preserving legacy run creation.
- **TF-F-013** Snapshot suite identity, version, type, name, and ordered composition in the run.
- **TF-F-014** Materialize one pending result for each suite case in deterministic order.
- **TF-F-015** Record pending, running, passed, failed, and skipped case states with optimistic locking.
- **TF-F-016** Record bounded attempts, duration, observed results, and evidence references.
- **TF-F-017** Derive run progress and terminal status from persisted case results.
- **TF-F-017A** Permit direct lifecycle control of catalog-backed runs only for cancellation.
- **TF-F-018** Treat failed or skipped required cases as a failed aggregate run.
- **TF-F-019** Publish case-result updates through the existing authenticated run stream.
- **TF-F-020** Atomically persist each accepted result with audit and outbox evidence.
- **TF-F-021** Preserve exact creation replay after the referenced suite is archived.
- **TF-NF-006** Limit attempts to 100, duration to 86,400,000 ms, and evidence references to 20.
- **TF-NF-007** Never copy raw evidence content into audit or outbox payloads.

## Verification catalogue

- **TF-T-001** Accept a complete reusable definition and normalize identifiers and tags.
- **TF-T-002** Reject invalid identifiers, empty steps, duplicate step identifiers, and excessive bounds.
- **TF-T-003** Verify definition creation audit and `atep.test_definition.created.v1` outbox evidence.
- **TF-T-004** Verify exact definition replay and stable conflicting reuse.
- **TF-T-005** Accept a suite containing active definitions and preserve explicit order.
- **TF-T-006** Reject missing, draft, archived, or duplicate suite definitions.
- **TF-T-007** Verify suite composition snapshots definition name and version.
- **TF-T-008** Verify suite creation audit and `atep.test_suite.created.v1` outbox evidence.
- **TF-T-009** Verify draft to active to archived transitions and reject backward transitions.
- **TF-T-010** Verify stable optimistic version conflicts.
- **TF-T-011** Verify `test_catalog:read`, `test_catalog:manage`, and HTTP 403 behavior.
- **TF-T-012** Verify API pagination and collection bounds through OpenAPI.
- **TF-T-013** Verify migration 0051 upgrade and downgrade with one linear Alembic head.
- **TF-T-014** Verify PostgreSQL uniqueness for public definition and suite identifiers.
- **TF-T-015** Verify audit and outbox writes share the resource transaction.
- **TF-T-016** Bind an active suite and verify its versioned run snapshot.
- **TF-T-017** Verify pending cases are materialized once and in suite order.
- **TF-T-018** Reject a new run for draft or archived suites.
- **TF-T-019** Replay an exact existing run after suite archival without duplicate cases or events.
- **TF-T-020** Verify case transition, attempt, duration, observation, and evidence bounds.
- **TF-T-021** Verify stale case-result versions and invalid transitions return stable conflicts.
- **TF-T-022** Verify required failure or skip produces a failed aggregate run.
- **TF-T-023** Verify all successful or optional terminal cases produce a passed aggregate run.
- **TF-T-024** Verify case result, aggregate run state, audit, and outbox commit atomically.
- **TF-T-025** Verify case APIs, RBAC, pagination, and authenticated live run projection.
- **TF-T-026** Verify migration 0052 upgrade, downgrade, constraints, and one Alembic head.
