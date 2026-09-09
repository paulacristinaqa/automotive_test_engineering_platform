# Mutation Testing and Requirement Coverage

ATEP VIII-6 models mutation quality as reviewed, auditable orchestration data. It does not run
arbitrary source code or shell commands inside the API. Future native adapters may apply mutations
in an isolated executor while preserving the contracts and evidence described here.

## Mutation flow

1. An authorized engineer creates a draft campaign from an active catalog suite.
2. A reviewer activates the versioned campaign.
3. An execution snapshots the campaign and vehicle context and materializes pending mutants.
4. An adapter reports running and terminal outcomes with bounded evidence references.
5. ATEP derives completed, killed, survived, score, and aggregate status from persisted results.
6. Exact retries return the original execution, including after campaign archival.

Supported operators are conditional negation, boundary shift, arithmetic replacement, return-value
replacement, constant replacement, boolean replacement, and exception suppression. The allowlist
keeps campaigns portable across future Python, Android, ECU, and simulator adapters.

## Scoring and safety semantics

`mutation_score = killed / (killed + survived)` when the denominator is non-zero. Errors and skips
remain visible but do not inflate or reduce the score. Once every mutant is terminal, any required
survived, errored, or skipped mutant fails the execution; optional outcomes do not.

Campaigns allow no more than 500 mutants. Structured parameters are capped at 8,192 bytes,
detecting-test references at 200, evidence references at 20, and terminal duration at 24 hours.
Audit and outbox messages publish identities, counts, status, and score without copying parameters
or evidence references.

## Requirement coverage

Each stable requirement ID can reference known catalog definitions and external evidence:

- **covered**: at least one definition and one evidence reference;
- **partial**: only definitions or only evidence exists;
- **gap**: neither exists.

The collection API returns totals for all three states, allowing dashboards and quality gates to
identify missing tests or missing execution evidence. Optimistic versions prevent concurrent
updates from silently overwriting reviewed traceability.

## Verification objectives

- prove unsupported mutation operators and unsafe bounds are rejected;
- prove campaign and execution snapshots remain immutable and idempotent;
- prove result transitions, detecting-test rules, and version conflicts are stable;
- prove scores and required/optional aggregate outcomes are deterministic;
- prove unknown test-definition references are rejected;
- prove covered, partial, and gap counts are correct;
- prove RBAC, audit, outbox, migration, and real-stack integration behavior;
- prove the increment runs locally without GPU, paid cloud, or paid AI services.
