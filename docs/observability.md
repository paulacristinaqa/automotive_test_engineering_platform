# ATEP Volume I Observability Baseline

## Purpose

This baseline makes Core Platform HTTP behavior measurable without placing vehicle identifiers,
user identifiers, raw URLs, credentials, tokens, request bodies, or artifact names in metric
labels. It combines three replaceable signals:

- structured JSON logs with `correlation_id`, `trace_id`, and `span_id`;
- OpenTelemetry server spans with W3C `traceparent` propagation and optional OTLP/HTTP export;
- Prometheus counters, histograms, gauges, and a versioned Grafana dashboard.

## Runtime Configuration

| Setting | Default | Purpose |
|---|---:|---|
| `ATEP_METRICS_ENABLED` | `true` | Exposes the internal `/metrics` scrape endpoint |
| `ATEP_TRACING_ENABLED` | `false` | Records sampled spans and enables configured export |
| `ATEP_OTEL_SERVICE_NAME` | `atep-core` | Stable OpenTelemetry service identity |
| `ATEP_OTEL_EXPORTER_OTLP_ENDPOINT` | unset | Collector HTTP traces endpoint, including `/v1/traces` |
| `ATEP_OTEL_TRACE_SAMPLE_RATIO` | `1.0` | Parent-based root sampling ratio from `0.0` to `1.0` |
| `ATEP_MODULE_AVAILABILITY_SLO_TARGET` | `0.99` | Active/credentialed module snapshot objective |
| `ATEP_MODULE_LEASE_WARNING_SECONDS` | `30` | Remaining-lease window reported as operational risk |
| `ATEP_OUTBOX_METRICS_PORT` | `9101` | Internal outbox-worker Prometheus HTTP port |
| `ATEP_OUTBOX_RETRY_SECONDS` | `1` | Delay after an empty batch or controlled publication failure |

Tracing-disabled requests still receive a valid `X-Trace-ID` for cross-signal correlation, but
their local spans are non-recording and nothing is exported. A caller-provided valid W3C
`traceparent` retains its trace identifier.

## Prometheus Metrics

| Metric | Type | Labels | Objective |
|---|---|---|---|
| `atep_http_requests_total` | Counter | method, route template, status | Traffic and error-rate analysis |
| `atep_http_request_duration_seconds` | Histogram | method, route template | Latency percentiles and SLOs |
| `atep_http_requests_in_progress` | Gauge | method | Saturation and stuck-request detection |
| `atep_http_request_exceptions_total` | Counter | method, route template, exception type | Unhandled-failure diagnosis |
| `atep_build_info` | Gauge | service, version, environment | Deployment identity |
| `atep_module_heartbeats_total` | Counter | reported status | Authenticated workload activity |
| `atep_module_lease_expirations_total` | Counter | none | Lease-expiry reconciliation evidence |
| `atep_module_reconciliation_errors_total` | Counter | none | Registry monitoring failures |
| `atep_registered_modules` | Gauge | bounded status | Credentialed module state distribution |
| `atep_registry_monitored_modules` | Gauge | none | Modules included in availability monitoring |
| `atep_module_availability_ratio` | Gauge | none | Current active/monitored snapshot ratio |
| `atep_module_at_risk_leases` | Gauge | none | Operational leases inside the warning window |
| `atep_outbox_publication_attempts_total` | Counter | fixed outcome | RabbitMQ publication success/failure |
| `atep_outbox_batch_duration_seconds` | Histogram | none | Transactional publication duration |
| `atep_outbox_unpublished_events` | Gauge | none | Current unpublished backlog |
| `atep_outbox_oldest_unpublished_age_seconds` | Gauge | none | Oldest unpublished event age |
| `atep_outbox_worker_up` | Gauge | none | Worker telemetry initialization |
| `atep_test_jobs_dispatched_total` | Counter | none | Scheduler dispatch throughput |
| `atep_test_scheduler_errors_total` | Counter | none | Scheduler cycle failures |
| `atep_test_scheduler_cycle_duration_seconds` | Histogram | none | Scheduler cycle duration |
| `atep_test_jobs_due` | Gauge | none | Jobs currently due |
| `atep_test_job_oldest_due_age_seconds` | Gauge | none | Oldest due-job delay |
| `atep_test_run_websocket_connections` | Gauge | none | Accepted live connections |
| `atep_test_run_websocket_connection_attempts_total` | Counter | fixed outcome | Accepted/rejected/error connections |
| `atep_test_run_websocket_messages_total` | Counter | fixed kind | Snapshot/update/heartbeat messages |
| `atep_test_run_live_publish_attempts_total` | Counter | fixed outcome | Redis live-projection success/failure |

The route label is the FastAPI template, such as `/api/v1/test-runs/{run_id}`, never the raw
request path. Unmatched requests use the bounded label `unmatched`.

## Reliability Objectives and Rules

`deploy/observability/alerts.yml` versions the initial reliability policy. The API availability
objective is 99.9%; HTTP 5xx responses are failures and all completed HTTP responses are valid
events. Recording rules calculate 5-minute, 1-hour, 6-hour, and 3-day error ratios, the 5-minute
success ratio, and global 5-minute p95 latency. Fast and slow multi-window burn-rate alerts reduce
noise compared with a single threshold.

The module objective is a current operational snapshot, not a historical uptime claim. Only
modules with an issued workload credential are monitored. `active` satisfies the objective;
`registered`, `degraded`, and `inactive` do not. `GET /api/v1/modules/health-summary` requires
`modules:read`, returns constant-size aggregate counts, and never returns module identifiers or
credential material.

The initial latency alert uses 500 ms to detect broad operational degradation. The formal
non-functional target remains p95 below 250 ms for defined production workloads and must be
calibrated through load evidence before release.

## Useful PromQL

```promql
sum by (route) (rate(atep_http_requests_total[5m]))
```

```promql
histogram_quantile(
  0.95,
  sum by (le, route) (rate(atep_http_request_duration_seconds_bucket[5m]))
)
```

```promql
sum(rate(atep_http_requests_total{status=~"5.."}[5m]))
/
clamp_min(sum(rate(atep_http_requests_total[5m])), 0.000001)
```

## Optional Local Stack

The normal ATEP Compose topology does not start observability services. Start them explicitly:

```powershell
docker compose `
  -f compose.yaml `
  -f compose.observability.yaml `
  --profile observability `
  up -d --build
```

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`
- OTLP/HTTP receiver: `http://localhost:4318/v1/traces`
- ATEP metrics: `http://localhost:8000/metrics`

Stop and remove the optional topology with:

```powershell
docker compose `
  -f compose.yaml `
  -f compose.observability.yaml `
  --profile observability `
  down
```

The versioned Grafana dashboard is provisioned automatically as **ATEP Core Platform Overview**.
The development Collector writes basic trace summaries to its own logs; it is not a durable trace
backend.

## Local Alert Delivery

Prometheus sends alerts to the pinned Alertmanager at `alertmanager:9093`. Alertmanager groups by
`alertname`, `service`, and `severity`; critical alerts use zero group wait and inhibit warning
alerts for the same service. Both firing and resolved notifications are sent to
`http://alert-webhook:8080/api/v1/alerts`.

The development receiver validates at most 50 alerts per notification and retains no alert body,
labels, annotations, vehicle IDs, test-run IDs, or credentials. It exposes only aggregate counters
using bounded `severity` (`critical`, `warning`, `info`, `unknown`) and `status` (`firing`,
`resolved`) labels. Alertmanager and receiver host ports bind to loopback:

- Alertmanager: `http://127.0.0.1:9093`
- aggregate webhook metrics: `http://127.0.0.1:9094/metrics`

The receiver is evidence that routing works, not a production incident channel. Production must
replace or extend it with managed provider adapters, secret-manager credentials, on-call ownership,
escalation, delivery retry monitoring, and audited change control.

## Alert Response

| Alert | First response |
|---|---|
| `AtepApiFastErrorBudgetBurn` | Treat as critical: correlate recent 5xx spans/logs, inspect readiness and dependency health, and stop risky promotion |
| `AtepApiSlowErrorBudgetBurn` | Review persistent failure routes, deployments, capacity, and dependency error trends |
| `AtepApiLatencyP95High` | Inspect route latency, in-progress requests, database pool, Redis, RabbitMQ, and host saturation |
| `AtepModuleUnavailable` | Inspect lease expiry, module process/network health, and credential rotation history before restarting |
| `AtepModuleDegraded` | Inspect the module's own diagnostic logs and declared degraded reason; do not mask it with a synthetic active heartbeat |
| `AtepModuleLeaseAtRisk` | Confirm heartbeat cadence, clock synchronization, network latency, and reconciler health |
| `AtepOutboxBacklogOld` | Inspect worker/RabbitMQ health and oldest backlog age; preserve rows and avoid manual database deletion |
| `AtepOutboxWorkerDown` | Check Prometheus target state, worker process, RabbitMQ connection, and the last failed batch; unpublished rows remain authoritative |
| `AtepOutboxPublicationErrors` | Inspect RabbitMQ connectivity/confirms and worker logs; expect at-least-once retry after rollback |
| `AtepTestSchedulerBacklogOld` | Inspect scheduler cycle duration/errors, database locks, due volume, and dispatch capacity |
| `AtepTestSchedulerErrors` | Correlate scheduler logs with database and TestRun constraints before retrying operationally |
| `AtepLiveUpdatePublishErrors` | Inspect Redis availability; authoritative TestRun state remains in PostgreSQL and clients must reconnect for a snapshot |

Operators can inspect both the Prometheus alerts page and local Alertmanager in the optional
topology. Local grouping, inhibition, and webhook delivery are tested; production still requires
reviewed provider routing, ownership, escalation, silences, and notification-delivery exercises.

## Security and Production Hardening

- Restrict `/metrics`, Prometheus, Grafana, and OTLP ports to an internal management network.
- Disable anonymous Grafana access outside the disposable local topology.
- Send OTLP over TLS with workload identity and collector authentication.
- Select a sampling ratio from measured traffic and retain error/security traces according to
  policy.
- Never attach credentials, request bodies, raw paths, VINs, email addresses, artifact names, or
  unrestricted exception messages as metric labels or span attributes.
- Replace the debug trace exporter with a durable backend and define retention, tenant isolation,
  access audit, calibrated SLO thresholds, and capacity limits.
- Add WebSocket, background scheduler, outbox, database-pool, Redis, RabbitMQ, and artifact-store
  domain metrics in subsequent hardening slices.

## Verification Objectives

1. Confirm metric labels contain route templates and no concrete identifiers.
2. Confirm `traceparent` produces a child server span with the same trace ID.
3. Confirm every HTTP response includes `X-Trace-ID` and `X-Correlation-ID`.
4. Confirm unhandled exceptions increment the exception counter and mark the span as error.
5. Confirm Prometheus scrapes `api:8000/metrics` and all dashboard panels return data.
6. Confirm tracing disabled produces no OTLP traffic and tracing enabled reaches the Collector.
7. Validate Prometheus configuration and rules with `promtool` in CI.
8. Confirm the health summary denies callers without `modules:read` and has constant-size output.
9. Trigger each alert with synthetic test traffic in an isolated environment and verify its runbook.
10. Confirm Prometheus scrapes both `api:8000/metrics` and internal `outbox-worker:9101/metrics`.
11. Create backlog and Redis/RabbitMQ failure conditions and verify no identifiers enter labels.
12. Load-test histogram/cardinality and calibrate production SLO, backlog, and latency thresholds.
13. Validate Alertmanager configuration with `amtool` and inject a synthetic critical alert.
14. Confirm the receiver increments only bounded counters and receives the resolved notification.
