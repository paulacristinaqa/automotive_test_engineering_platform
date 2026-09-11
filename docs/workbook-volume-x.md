# ATEP Volume X Dashboard Engineering Workbook

Version 0.5.0 records X-1 through X-4 and the approved X-5 supporting-evidence scope.

## Scope and architecture

The dashboard is a read-only projection over existing ATEP domains. FastAPI publishes a versioned
overview, PostgreSQL performs bounded aggregations, and source services remain authoritative. The
first contract supports KPI cards, charts, heatmaps, and evidence lists without choosing a
frontend framework prematurely.

## Engineering decisions

- Require the dedicated `dashboard:read` permission.
- Use UTC windows from 1 to 720 hours, with a 24-hour default.
- Limit recent evidence to 50 cards and default to 10.
- Return `null` for undefined rates rather than implying zero performance.
- Include citations but exclude prompts, raw logs, and source context.
- Keep requirement coverage as a documented current snapshot.
- Avoid materialized copies until measured query demand justifies them.
- Produce complete UTC day sequences so chart clients do not invent missing buckets.
- Limit failure observations to 500 characters while preserving evidence references.

## Tests and objectives

- KPI tests verify totals, active executions, percentages, rounding, and evidence mapping.
- Empty-state tests verify truthful undefined-rate behavior.
- OpenAPI tests verify response type and safe query limits.
- Permission tests preserve the stable `dashboard:read` name.
- Full regression tests protect all preceding volumes.
- PostgreSQL integration validates the endpoint and RBAC against the deployed schema.
- Ruff and mypy protect formatting and type contracts.
- Trend tests verify UTC bucketing, zero-activity days, outcome counts, and pass rates.
- Failure tests verify filtering, ordering, pagination, evidence mapping, and truncation.

## Risks and controls

Large time windows can make aggregate queries expensive: overview and operations use at most
30 days, while test-quality trends and failures allow at most 90 days.
Dashboard figures can be misread as certification evidence, so the response contains an explicit
limitation. AI evidence can contain explanatory text, so the service returns only previously
governed dashboard projections and a bounded citation list.

## Cost and resource profile

X-1 and X-2 reuse FastAPI and PostgreSQL, perform no external network call, and require no paid
API, cloud account, model, or GPU. Tests are CPU-light and use small deterministic fixtures.

## X-3 — Operational views (2026-09-11)

The operations API adds read-only cross-domain summaries for vehicles, ECUs, CAN and
diagnostics. FastAPI validates the bounded UTC activity window, the existing permission
dependency enforces `dashboard:read`, and SQLAlchemy performs PostgreSQL aggregates.
No migration, external provider, GPU workload or paid infrastructure is introduced.

Design decisions:

- Current inventory and stored DTC distributions are separate from activity history.
- Each activity query has both lower and upper timestamp bounds.
- Independent scalar subqueries prevent duplicate counts from cross-domain joins.
- Only aggregate columns are selected: no secrets or command payloads are loaded.
- Explicit limitations distinguish stored evidence from live health and safety certification.
- Sequential reads are not presented as an atomic vehicle snapshot.

Tests and objectives:

- Populated/empty aggregate tests verify mappings and zero-activity behavior.
- OpenAPI tests verify time limits and exclusion of raw payload fields.
- Integration compares vehicle, ECU and network totals with database counts.
- Integration checks authorized access, forbidden access and invalid time windows.
- Regression: 532 tests passed; Ruff passed; mypy passed for src and tests.
- Docker integration: 1 end-to-end test passed; PostgreSQL backup/restore drill passed.
- Resource sample: GPU 7%; RabbitMQ approximately 225% container CPU (2.25 cores).
  Windows CPU counters were unavailable due to permissions. Samples are not peak measurements.

The existing DOCX edition remains version 0.2.0 (X-1/X-2); this Markdown workbook is
the current development record for X-3 until the next document export.

## X-4 — EV, charging, thermal and ADAS analytics

The mobility endpoint supplies chart-ready distributions without adding a frontend framework.
Six metric summaries expose units and population sizes. Seven sorted state/outcome groups
preserve the terminology of the source services. Current component records are distinct from
time-windowed scenario executions and planning evaluations.

Engineering decisions:

- Reuse FastAPI, Pydantic, SQLAlchemy and PostgreSQL; no new dependencies or migrations.
- Compute unweighted per-component statistics in SQL, without loading raw simulation payloads.
- Use explicit UTC lower and upper boundaries only on activity data.
- Return null numeric statistics for absent components; never infer that missing data is healthy.
- Avoid fleet-wide thermal alarm thresholds: source models own operating-state decisions.
- Keep queries sequential to avoid concurrent session use; do not claim snapshot consistency.
- Defer interactive charts and query-cost hardening to their planned increments.

Tests and objectives:

- Populated and empty fixtures verify metric mapping, counts, statistics and missing-data semantics.
- SQL inspection checks both activity boundaries, deterministic group order and absence of joins.
- OpenAPI checks window limits, metric units and population-count fields.
- PostgreSQL integration compares battery statistics against direct database aggregates.
- Integration checks authorized access, forbidden access and invalid query windows.
- Local regression: 535 tests passed; Ruff and mypy passed.
- Docker integration: 1 test passed, including the mobility endpoint and RBAC.
- PostgreSQL backup and isolated restore drill passed; temporary containers were removed.
- Resource samples: Windows CPU 4% during integration; API container CPU 12.14%.
  GPU utilization was 12% after regression. These samples are not peak measurements.

No paid service, model download, GPU computation or AWS account is required. The DOCX edition
remains X-1/X-2; this Markdown workbook records the current development evidence.

## X-5 — Supporting evidence and explicit gaps

Scope decision: repository inspection found diagnostic flashing, audit and generic requirement
coverage, but no OTA lifecycle or formal standards mappings. The user approved delivering an
evidence/gap panel instead of prematurely implementing those future domains.

The read-only evidence-readiness API executes three sorted aggregate queries. Flash and coverage
are current states; audit outcomes use inclusive UTC bounds. Pydantic fixes the assessment to
not_assessed. Versioned gap cards preserve the distinction between existing supporting records
and missing capabilities. No standards clauses, capability level, ASIL or certification is inferred.

Tests and objectives:

- Empty and populated cases prove successful records never erase implementation/assessment gaps.
- SQL tests verify time bounds, deterministic order and exclusion of sensitive detail columns.
- OpenAPI validates the fixed assessment contract and safe query limits.
- Integration compares flash totals against PostgreSQL and verifies HTTP 403/422 behavior.
- Local regression: 538 tests passed; Ruff and mypy passed for src and tests.
- Docker integration: 1 test passed, including aggregate comparison and HTTP 403/422 checks.
- PostgreSQL backup/restore drill passed; temporary test containers were removed.
- Initial Docker Hub TLS timeout occurred before startup; one retry succeeded.
- Resource samples: Windows CPU 27%, GPU 12%; RabbitMQ 181.67% container CPU
  (approximately 1.8 cores) during integration. These are samples, not peak measurements.

No new dependency, migration, paid provider, GPU workload or cloud account is introduced.
The Markdown workbook is current; the DOCX export remains the X-1/X-2 edition.

## Next increment

X-6: live updates, exports, retention and performance hardening. Full OTA and formal standards
mapping views remain explicitly deferred until their source capabilities are implemented.
