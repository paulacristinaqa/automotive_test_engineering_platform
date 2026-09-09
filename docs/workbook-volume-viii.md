# Volume VIII Test Framework Engineering Workbook

Version 0.7.0 records the complete Volume VIII baseline: VIII-1 catalog, VIII-2 execution
binding, VIII-3 scheduled selection, VIII-5 fault campaigns, VIII-6 mutation/coverage, and VIII-7
cross-platform reporting. It documents
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

## VIII-3 outcome

VIII-3 binds durable test jobs to an explicit smoke, sanity, or regression catalog selection. The
job preserves the reviewed suite snapshot before waiting, and dispatch later creates the run and
its pending cases from that immutable intent.

## VIII-3 evidence

- Catalog suite ID and selection policy must be supplied together and match the requested run suite.
- Only active smoke, sanity, and regression suites can enter the scheduled-selection path.
- Suite identity, version, type, tags, and ordered cases are persisted on the job.
- Dispatch uses the job snapshot and materializes case results atomically with the run.
- Legacy jobs remain supported, while selection metadata appears in API, audit, and outbox evidence.
- Migration 0053 adds the nullable catalog reference, selection policy, version, snapshot, and indexes.

## VIII-5 outcome

VIII-5 defines reusable, versioned fault campaigns across Digital Vehicle, ECU, CAN, diagnostics,
Electric Vehicle, and ADAS. Executions preserve immutable intent, track injection and recovery as
explicit states, and aggregate required outcomes without granting a generic command-execution path.

## VIII-5 evidence

- Domain-specific action allowlists prevent misleading or arbitrary cross-domain commands.
- Every fault step declares expected behavior and a bounded recovery action and verification.
- Blast radius is limited to one component, network, or vehicle; fleet-wide campaigns are excluded.
- Active campaign executions snapshot up to 32 ordered steps and optionally link to a test run.
- Step updates use optimistic locking and derive aggregate progress, pass, or fail state.
- Exact execution replay remains idempotent after campaign archival.
- Audit and outbox records contain counts and fingerprints, not raw parameters or evidence references.
- Migration 0054 adds campaigns, executions, and step results with reversible constraints and indexes.
- Native simulators retain ownership of state mutation; adapter execution remains isolated from the API.

## VIII-6 outcome

VIII-6 introduces reviewed mutation campaigns backed by active suite snapshots, deterministic
mutant-result aggregation, and a requirement traceability register that makes coverage gaps explicit.
It records portable evidence without executing arbitrary source transformations in the API process.

## VIII-6 evidence

- Seven explicit operators replace free-form mutation commands.
- Campaigns contain up to 500 unique ordered mutants and preserve the source suite snapshot.
- Execution creation atomically materializes pending results and remains replay-safe after archival.
- Killed results identify detecting tests; bounded evidence references stay out of audit/outbox payloads.
- Mutation score uses killed and survived results only; required survivors, errors, or skips fail the run.
- Requirements reference known catalog definitions and classify deterministically as covered, partial, or gap.
- Coverage collection responses include aggregate counts for immediate gap analysis.
- Migration 0055 adds campaign, execution, result, and coverage tables with reversible constraints and indexes.

## VIII-4 outcome

VIII-4 adds bounded performance and stress profiles, deterministic threshold evaluation, immutable
execution evidence, and same-profile historical comparisons. Profiles cap duration, virtual users,
request rate, CPU, and memory, and always prohibit GPU use. Load generation remains outside the API.

## VIII-4 evidence

- Profiles contain at most twelve stages and one hour of total workload intent.
- Executions reference terminal test runs and portable evidence rather than raw load artifacts.
- Every configured minimum or maximum threshold contributes to the deterministic outcome.
- Same-profile baselines preserve current value, baseline value, and signed metric delta.
- Audit and outbox events contain outcome and counts without raw metrics or evidence references.
- Migration 0058 adds profiles and executions with reversible constraints and indexes.

## VIII-7 outcome

VIII-7 creates one immutable automation report that correlates the authoritative terminal test run
with Vehicle Gateway telemetry and commands, optional fault and mutation executions, and the status
and version actually displayed by CarSystemUI.

## VIII-7 evidence

- Existing REST, WebSocket, workload identity, telemetry, and command channels remain authoritative.
- Gateway capability, source, target, vehicle, and test-run relationships are validated before commit.
- Fault and mutation executions must be terminal and belong to the same vehicle and test run.
- CarSystemUI observations are timezone-aware and must match the persisted run status and version.
- Combined passed, failed, or cancelled outcome follows deterministic precedence.
- One report per test run prevents contradictory final evidence; exact replay remains idempotent.
- Audit/outbox evidence contains identifiers and counts without raw cross-platform collections.
- Migration 0056 adds the report table with reversible foreign keys, uniqueness, and indexes.

## Volume completion

The complete Volume VIII baseline is implemented. Meaningful load generation remains bounded and
isolated from the API, with hosted CI preferred to protect workstation CPU and GPU resources.
