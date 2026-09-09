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

## VIII-3 Scheduled selection

- **TF-F-022** Schedule an active catalog suite with an explicit smoke, sanity, or regression policy.
- **TF-F-023** Require the requested run suite, selection policy, and catalog suite type to match.
- **TF-F-024** Snapshot suite identity, version, type, tags, and ordered composition when scheduling.
- **TF-F-025** Dispatch from the persisted selection snapshot without re-reading mutable catalog data.
- **TF-F-026** Materialize one pending case result per scheduled snapshot case atomically with the run.
- **TF-F-027** Preserve legacy scheduled jobs that do not bind a catalog suite.
- **TF-F-028** Expose the snapshot in job APIs and bounded identity, policy, version, and case-count evidence.
- **TF-NF-008** Restrict this increment to smoke, sanity, and regression; performance and stress remain VIII-4.
- **TF-NF-009** Keep due-job dispatch bounded, concurrent-worker safe, CPU-only, and independent of paid services.

## VIII-5 Fault campaigns

- **TF-F-029** Create reusable fault campaigns spanning Digital Vehicle, ECU, CAN, diagnostics, EV, and ADAS domains.
- **TF-F-030** Restrict every domain to an explicit fault-action allowlist and reject cross-domain action reuse.
- **TF-F-031** Require a bounded blast radius, injection duration, recovery action, recovery timeout, and verification statement.
- **TF-F-032** Apply idempotent creation and a draft, active, archived forward-only lifecycle with optimistic locking.
- **TF-F-033** Create executions only from active campaigns and preserve an immutable versioned campaign snapshot.
- **TF-F-034** Materialize one pending result for each ordered campaign step atomically with execution creation.
- **TF-F-035** Bind each execution to a vehicle and optionally to a test run for the same vehicle.
- **TF-F-036** Record injecting, injected, recovering, recovered, failed, and skipped step transitions and derive aggregate progress and outcome.
- **TF-F-037** Allow an authorized operator to cancel an incomplete campaign execution.
- **TF-F-038** Atomically persist audit and outbox evidence using bounded counts and fingerprints instead of raw parameters or evidence references.
- **TF-F-039** Preserve exact execution replay after the source campaign is archived while rejecting new executions.
- **TF-NF-010** Limit campaigns to 32 steps, structured parameters to 8,192 bytes, and total injection plus recovery budget to 30 minutes.
- **TF-NF-011** Keep physical mutation in native domain simulators; campaign contracts must not expose arbitrary generic command execution.
- **TF-NF-012** Run campaign management and verification locally without GPU, paid cloud, or paid AI dependencies.

## VIII-6 Mutation testing and requirement coverage

- **TF-F-040** Create bounded mutation campaigns from active catalog suites and preserve immutable suite snapshots.
- **TF-F-041** Restrict mutants to versioned operators, unique identities and order, bounded targets, parameters, and expected detection.
- **TF-F-042** Apply idempotent creation and a draft, active, archived forward-only lifecycle with optimistic locking.
- **TF-F-043** Create executions only from active campaigns and atomically materialize one pending result per mutant.
- **TF-F-044** Record pending, running, killed, survived, error, and skipped outcomes with versions, duration, detecting tests, and evidence references.
- **TF-F-045** Derive the mutation score as killed divided by killed plus survived mutants.
- **TF-F-046** Fail the aggregate execution for required survived, error, or skipped mutants; optional outcomes remain informative.
- **TF-F-047** Preserve exact execution replay after campaign archival while rejecting new executions.
- **TF-F-048** Trace requirements only to known test definitions and bounded evidence references.
- **TF-F-049** Classify each requirement deterministically as covered, partial, or gap.
- **TF-F-050** Expose filtered coverage lists and aggregate covered, partial, and gap counts.
- **TF-F-051** Atomically persist campaign, execution, result, and coverage audit/outbox evidence without raw parameters or evidence references.
- **TF-NF-013** Limit campaigns to 500 mutants, parameters to 8,192 bytes, detecting tests to 200, and evidence references to 20.
- **TF-NF-014** Treat mutation execution as reviewed orchestration data; native mutation adapters must not expose arbitrary code execution.
- **TF-NF-015** Run campaign, scoring, traceability, and verification locally without GPU, paid cloud, or paid AI dependencies.

## VIII-7 Cross-platform automation reporting

- **TF-F-052** Create one immutable cross-platform automation report per terminal test run.
- **TF-F-053** Correlate the report with one vehicle and one gateway module that can publish telemetry and consume commands.
- **TF-F-054** Require referenced telemetry to originate from the selected vehicle and gateway.
- **TF-F-055** Require referenced commands to be terminal and belong to the selected vehicle, gateway, and test run.
- **TF-F-056** Optionally correlate terminal fault and mutation executions for the same vehicle and test run.
- **TF-F-057** Retain bounded CarSystemUI observations containing surface, connection state, displayed status/version, client version, capture time, and optional evidence reference.
- **TF-F-058** Reject CarSystemUI observations that differ from the authoritative test-run status or version.
- **TF-F-059** Derive a passed, failed, or cancelled combined outcome from all correlated terminal executions.
- **TF-F-060** Make exact report retries idempotent and conflicting report or test-run reuse stable.
- **TF-F-061** Provide create, detail, filtered list, and safe pagination APIs protected by catalog RBAC.
- **TF-F-062** Atomically persist the report, audit record, and `atep.cross_platform_automation.report.created.v1` outbox event.
- **TF-NF-016** Limit telemetry and command references to 100 each and CarSystemUI observations to 50.
- **TF-NF-017** Keep audit/outbox payloads free from raw telemetry, commands, and CarSystemUI observation collections.
- **TF-NF-018** Run correlation and reporting locally without GPU, paid cloud, or paid AI dependencies.

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
- **TF-T-027** Accept matching smoke, sanity, and regression selections and normalize suite IDs.
- **TF-T-028** Reject incomplete, mismatched, inactive, performance, stress, and safety selections.
- **TF-T-029** Verify exact job replay preserves idempotency and does not duplicate evidence.
- **TF-T-030** Verify scheduled selection snapshots remain unchanged after catalog mutation or archival.
- **TF-T-031** Dispatch the persisted snapshot and materialize its ordered pending cases atomically.
- **TF-T-032** Verify job and run events expose selection metadata without copying case payloads.
- **TF-T-033** Verify API contracts, RBAC, safe pagination, and legacy scheduler compatibility.
- **TF-T-034** Verify migration 0053 upgrade, downgrade, foreign keys, indexes, and one Alembic head.
- **TF-T-035** Accept every supported domain and its allowlisted fault actions.
- **TF-T-036** Reject cross-domain actions, duplicate step identities or order, and excessive campaign budgets.
- **TF-T-037** Verify campaign creation idempotency, conflict behavior, audit, and bounded outbox evidence.
- **TF-T-038** Verify campaign lifecycle and optimistic version conflicts.
- **TF-T-039** Create an execution snapshot and materialize ordered pending step results atomically.
- **TF-T-040** Reject inactive campaigns, mismatched test-run vehicles, and unsafe execution bounds.
- **TF-T-041** Replay an exact execution after campaign archival without duplicating steps or evidence.
- **TF-T-042** Verify the complete inject, observe, recover lifecycle and aggregate passed outcome.
- **TF-T-043** Verify required failures or skips fail the execution while optional failures do not.
- **TF-T-044** Reject invalid step transitions and stale step-result versions with stable conflicts.
- **TF-T-045** Verify cancellation of incomplete executions and rejection after terminal completion.
- **TF-T-046** Verify API contracts, RBAC, pagination, safe schema bounds, and stable HTTP errors.
- **TF-T-047** Verify audit and outbox payloads expose fingerprints and counts without raw parameters or evidence references.
- **TF-T-048** Verify migration 0054 upgrade, downgrade, constraints, indexes, and one linear Alembic head.
- **TF-T-049** Accept the allowlisted mutation operators and reject unknown operators, duplicate identities or order, and excessive bounds.
- **TF-T-050** Verify campaign suite snapshots, idempotency, lifecycle, optimistic locking, audit, and bounded events.
- **TF-T-051** Create an execution snapshot and atomically materialize ordered pending mutant results.
- **TF-T-052** Reject inactive campaigns and mismatched test-run vehicles while preserving exact replay after archival.
- **TF-T-053** Verify valid mutant transitions, terminal evidence rules, stale versions, and stable conflicts.
- **TF-T-054** Verify deterministic kill rate and aggregate passed and failed outcomes for required and optional mutants.
- **TF-T-055** Create and update requirement traceability, reject unknown definitions, and classify covered, partial, and gap states.
- **TF-T-056** Verify coverage filters, aggregate counts, pagination bounds, RBAC, and stable HTTP errors.
- **TF-T-057** Verify audit/outbox evidence exposes counts rather than raw parameters or evidence references.
- **TF-T-058** Verify migration 0055 upgrade, downgrade, constraints, indexes, and one linear Alembic head.
- **TF-T-059** Exercise campaign, execution, scoring, archival replay, traceability, gap analysis, and RBAC against the real integration stack.
- **TF-T-060** Accept a complete terminal report and derive its combined outcome and summary.
- **TF-T-061** Reject nonterminal test runs, fault executions, mutation executions, and commands.
- **TF-T-062** Reject cross-vehicle, cross-gateway, cross-run, missing, or capability-incomplete references.
- **TF-T-063** Reject stale or inconsistent CarSystemUI status/version and timezone-free timestamps.
- **TF-T-064** Verify exact retry, conflicting report/test-run reuse, and database uniqueness.
- **TF-T-065** Verify collection bounds, filtered pagination, OpenAPI contracts, and RBAC.
- **TF-T-066** Verify audit/outbox atomicity and minimized event evidence.
- **TF-T-067** Verify migration 0056 upgrade, downgrade, foreign keys, indexes, and one linear Alembic head.
- **TF-T-068** Exercise the complete test-run, fault, mutation, gateway telemetry/command, CarSystemUI, report, replay, and RBAC flow against the disposable integration stack.
