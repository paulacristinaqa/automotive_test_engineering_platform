# ATEP Volume X Dashboard Engineering Workbook

Version 0.3.0 records X-1 through X-3, including test-quality history and operational summaries.

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

## Next increment

X-4 will add EV, charging, thermal, and ADAS visual analytics contracts.
