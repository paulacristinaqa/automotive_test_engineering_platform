# Test Framework

Volume VIII turns the existing execution infrastructure into a reusable test engineering system.
VIII-1 introduced the catalog, VIII-2 bound reviewed suites to deterministic case execution, and
VIII-3 connects those snapshots to the durable scheduler for smoke, sanity, and regression runs.
VIII-5 adds bounded cross-domain fault campaigns and recovery evidence. VIII-6 adds mutation
quality evidence and requirement traceability. Performance and stress remain intentionally deferred
until stable final baselines exist. VIII-7 closes the functional baseline with one correlated report
across ATEP, Vehicle Gateway, and CarSystemUI.

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
- `POST /api/v1/fault-campaigns` creates an idempotent draft campaign.
- `GET /api/v1/fault-campaigns` and `GET /api/v1/fault-campaigns/{campaign_id}` expose campaigns.
- `PATCH /api/v1/fault-campaigns/{campaign_id}/status` activates or archives a campaign.
- `POST /api/v1/fault-campaigns/{campaign_id}/executions` creates a versioned execution snapshot.
- `GET /api/v1/fault-executions` and `GET /api/v1/fault-executions/{execution_id}` expose execution state.
- `GET /api/v1/fault-executions/{execution_id}/steps` returns ordered step results.
- `PATCH /api/v1/fault-executions/{execution_id}/steps/{step_id}` records injection and recovery evidence.
- `PATCH /api/v1/fault-executions/{execution_id}/cancel` cancels an incomplete execution.
- `POST /api/v1/mutation-campaigns` creates a suite-backed draft mutation campaign.
- `GET /api/v1/mutation-campaigns` and the detail/status routes expose its versioned lifecycle.
- `POST /api/v1/mutation-campaigns/{campaign_id}/executions` materializes mutant results.
- `GET /api/v1/mutation-executions` and the detail/mutant routes expose score evidence.
- `PATCH /api/v1/mutation-executions/{execution_id}/mutants/{mutant_id}` records an outcome.
- `PUT /api/v1/requirement-coverage/{requirement_id}` creates or updates traceability.
- `GET /api/v1/requirement-coverage` exposes filtered items and coverage-gap totals.
- `POST /api/v1/cross-platform-automation/reports` creates one terminal correlated report.
- `GET /api/v1/cross-platform-automation/reports` lists reports with outcome filtering.
- `GET /api/v1/cross-platform-automation/reports/{report_id}` returns report evidence and summary.

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

## Fault campaigns

A campaign defines one to thirty-two ordered fault steps across Digital Vehicle, ECU, CAN,
diagnostics, Electric Vehicle, and ADAS. Each domain has an explicit action allowlist. Every step
must declare its expected effect and a bounded recovery plan, while the campaign limits blast
radius to one component, one network, or one vehicle and caps total injection plus recovery time at
thirty minutes.

An execution snapshots the active campaign and materializes pending step results in one transaction.
Step results move through injection, observation, recovery, and terminal states with optimistic
locking. Required failed or skipped steps fail the aggregate execution after all steps are terminal;
optional failures remain informative. Exact retries remain idempotent after campaign archival.

The framework owns orchestration intent, lifecycle, safety bounds, and evidence. Digital Vehicle,
ECU, CAN, diagnostics, EV, and ADAS simulators remain responsible for performing their native state
mutations. The VIII-5 API deliberately exposes no arbitrary command runner. Native adapter
execution remains a future isolated integration concern; the API remains orchestration-only.

## Mutation testing and coverage

A mutation campaign binds a reviewed active test suite to up to five hundred ordered mutants. Each
mutant uses an explicit operator allowlist and declares a target, bounded structured parameters,
expected detection, and whether its survival is required to fail the execution. The active campaign
is snapshotted when execution begins and pending results are materialized atomically.

Results move from pending to running or skipped and then to killed, survived, error, or skipped.
A killed mutant must name at least one detecting test. The deterministic mutation score is
`killed / (killed + survived)`; error and skipped results do not distort that denominator. A required
survivor, error, or skip fails the aggregate execution, while optional outcomes remain informative.

Requirement coverage links stable requirement IDs to known catalog definitions and evidence
references. Both links present means covered, one kind present means partial, and neither means a
gap. Aggregate counts make missing evidence visible without parsing documents. The current layer
stores reviewed orchestration and results only. Native mutation adapters require isolated execution
and must not introduce arbitrary code execution into the API process.

## Cross-platform automation reporting

VIII-7 reuses the existing public REST, gateway workload identity, command lease, telemetry,
test-run WebSocket, fault, and mutation contracts. It adds one immutable report per terminal test
run rather than introducing another execution channel. A report names the authoritative vehicle,
test run, gateway module, telemetry and command identifiers, optional fault and mutation executions,
and bounded CarSystemUI observations.

Every reference is validated before commit. Telemetry must originate from the selected gateway and
vehicle. Commands must be terminal and addressed to the same gateway, vehicle, and test run. Fault
and mutation executions must also be terminal and correlated to that run. Each CarSystemUI
observation includes a timezone-aware capture time and must display the authoritative run status and
version, preventing stale UI state from being recorded as successful evidence.

The combined outcome is failed if any correlated component failed, cancelled if none failed but one
was cancelled, and passed otherwise. Exact retries return the original report. The transactional
outbox and audit record contain identities, outcome, and counts only; detailed observations and
external evidence references remain in the report.

## Security and cost

Read operations require `test_catalog:read`; mutations require `test_catalog:manage`. Payload and
collection bounds protect database, API, and future executor resources. The implementation runs
locally and requires no GPU, paid cloud service, or paid AI API.
