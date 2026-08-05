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

The route label is the FastAPI template, such as `/api/v1/test-runs/{run_id}`, never the raw
request path. Unmatched requests use the bounded label `unmatched`.

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

## Security and Production Hardening

- Restrict `/metrics`, Prometheus, Grafana, and OTLP ports to an internal management network.
- Disable anonymous Grafana access outside the disposable local topology.
- Send OTLP over TLS with workload identity and collector authentication.
- Select a sampling ratio from measured traffic and retain error/security traces according to
  policy.
- Never attach credentials, request bodies, raw paths, VINs, email addresses, artifact names, or
  unrestricted exception messages as metric labels or span attributes.
- Replace the debug trace exporter with a durable backend and define retention, tenant isolation,
  access audit, alert rules, SLO burn-rate windows, and capacity limits.
- Add WebSocket, background scheduler, outbox, database-pool, Redis, RabbitMQ, and artifact-store
  domain metrics in subsequent hardening slices.

## Verification Objectives

1. Confirm metric labels contain route templates and no concrete identifiers.
2. Confirm `traceparent` produces a child server span with the same trace ID.
3. Confirm every HTTP response includes `X-Trace-ID` and `X-Correlation-ID`.
4. Confirm unhandled exceptions increment the exception counter and mark the span as error.
5. Confirm Prometheus scrapes `api:8000/metrics` and all dashboard panels return data.
6. Confirm tracing disabled produces no OTLP traffic and tracing enabled reaches the Collector.
7. Load-test histogram and label cardinality before setting production SLO thresholds.
