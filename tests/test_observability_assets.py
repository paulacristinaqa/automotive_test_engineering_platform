import json
from pathlib import Path


def test_grafana_dashboard_is_versioned_and_uses_bounded_metric_labels() -> None:
    dashboard_path = Path("deploy/observability/grafana/dashboards/atep-core-overview.json")
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    assert dashboard["uid"] == "atep-core-overview"
    assert dashboard["title"] == "ATEP Core Platform Overview"
    assert len(dashboard["panels"]) == 4
    expressions = [target["expr"] for panel in dashboard["panels"] for target in panel["targets"]]
    assert any("atep_http_requests_total" in expression for expression in expressions)
    assert any(
        "atep_http_request_duration_seconds_bucket" in expression for expression in expressions
    )
    assert all("path" not in expression for expression in expressions)


def test_prometheus_and_collector_configs_target_only_internal_services() -> None:
    prometheus = Path("deploy/observability/prometheus.yml").read_text(encoding="utf-8")
    collector = Path("deploy/observability/otel-collector.yaml").read_text(encoding="utf-8")
    assert 'targets: ["api:8000"]' in prometheus
    assert "metrics_path: /metrics" in prometheus
    assert "endpoint: 0.0.0.0:4318" in collector
    assert "memory_limiter" in collector
    assert "exporters:" in collector and "debug:" in collector
