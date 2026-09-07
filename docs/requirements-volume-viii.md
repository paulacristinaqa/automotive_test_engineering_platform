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
