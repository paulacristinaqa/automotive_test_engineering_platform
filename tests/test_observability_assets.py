import json
from pathlib import Path

import yaml  # type: ignore[import-untyped]


def test_grafana_dashboard_is_versioned_and_uses_bounded_metric_labels() -> None:
    dashboard_path = Path("deploy/observability/grafana/dashboards/atep-core-overview.json")
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    assert dashboard["uid"] == "atep-core-overview"
    assert dashboard["title"] == "ATEP Core Platform Overview"
    assert dashboard["version"] == 3
    assert len(dashboard["panels"]) == 9
    expressions = [target["expr"] for panel in dashboard["panels"] for target in panel["targets"]]
    assert any("atep_http_requests_total" in expression for expression in expressions)
    assert any(
        "atep_http_request_duration_seconds_bucket" in expression for expression in expressions
    )
    assert all("path" not in expression for expression in expressions)
    assert any("atep:sli_http_success_ratio:rate5m" in expression for expression in expressions)
    assert any("atep_registered_modules" in expression for expression in expressions)
    assert any(
        "atep_outbox_oldest_unpublished_age_seconds" in expression for expression in expressions
    )
    assert any("atep_test_job_oldest_due_age_seconds" in expression for expression in expressions)
    assert any("atep_test_run_websocket_connections" in expression for expression in expressions)


def test_prometheus_and_collector_configs_target_only_internal_services() -> None:
    prometheus = Path("deploy/observability/prometheus.yml").read_text(encoding="utf-8")
    collector = Path("deploy/observability/otel-collector.yaml").read_text(encoding="utf-8")
    assert 'targets: ["api:8000"]' in prometheus
    assert 'targets: ["outbox-worker:9101"]' in prometheus
    assert "metrics_path: /metrics" in prometheus
    assert "/etc/prometheus/alerts.yml" in prometheus
    assert "endpoint: 0.0.0.0:4318" in collector
    assert "memory_limiter" in collector
    assert "exporters:" in collector and "debug:" in collector


def test_slo_recording_rules_and_alerts_are_versioned_as_code() -> None:
    rules = yaml.safe_load(Path("deploy/observability/alerts.yml").read_text(encoding="utf-8"))
    entries = [rule for group in rules["groups"] for rule in group["rules"]]
    records = {entry["record"] for entry in entries if "record" in entry}
    alerts = {entry["alert"]: entry for entry in entries if "alert" in entry}

    assert {
        "atep:sli_http_error_ratio:rate5m",
        "atep:sli_http_error_ratio:rate1h",
        "atep:sli_http_success_ratio:rate5m",
        "atep:sli_http_latency_p95_seconds:rate5m",
    } <= records
    assert {
        "AtepApiFastErrorBudgetBurn",
        "AtepApiSlowErrorBudgetBurn",
        "AtepApiLatencyP95High",
        "AtepModuleUnavailable",
        "AtepModuleDegraded",
        "AtepModuleLeaseAtRisk",
        "AtepOutboxBacklogOld",
        "AtepOutboxWorkerDown",
        "AtepOutboxPublicationErrors",
        "AtepTestSchedulerBacklogOld",
        "AtepTestSchedulerErrors",
        "AtepLiveUpdatePublishErrors",
    } == set(alerts)
    assert alerts["AtepApiFastErrorBudgetBurn"]["labels"]["severity"] == "critical"
    assert all("runbook_url" in entry["annotations"] for entry in alerts.values())
