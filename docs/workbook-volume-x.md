# ATEP Volume X Dashboard Engineering Workbook

Version 0.2.0 records X-1 and X-2, including daily test-quality history and failed-case drill-down.

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

Large time windows can make aggregate queries expensive, so the API caps the window at 30 days.
Dashboard figures can be misread as certification evidence, so the response contains an explicit
limitation. AI evidence can contain explanatory text, so the service returns only previously
governed dashboard projections and a bounded citation list.

## Cost and resource profile

X-1 and X-2 reuse FastAPI and PostgreSQL, perform no external network call, and require no paid
API, cloud account, model, or GPU. Tests are CPU-light and use small deterministic fixtures.

## Next increment

X-3 will add bounded vehicle, ECU, CAN, and diagnostics operational views.
