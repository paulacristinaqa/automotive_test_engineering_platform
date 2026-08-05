from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from atep.core.config import Settings
from atep.core.observability import Observability, ObservabilityMiddleware


def settings() -> Settings:
    return Settings(
        jwt_secret="observability-test-secret-at-least-32-characters",
        environment="test",
        tracing_enabled=True,
        otel_trace_sample_ratio=1.0,
    )


def instrumented_app() -> tuple[FastAPI, Observability, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    observability = Observability(settings(), tracer_provider=provider)
    app = FastAPI()

    @app.get("/widgets/{widget_id}")
    async def widget(widget_id: str) -> dict[str, str]:
        return {"id": widget_id}

    @app.get("/failure")
    async def failure() -> None:
        raise RuntimeError("controlled test failure")

    app.add_middleware(ObservabilityMiddleware, observability=observability)
    return app, observability, exporter


def test_metrics_use_route_templates_and_trace_header() -> None:
    app, observability, exporter = instrumented_app()
    response = TestClient(app).get("/widgets/vehicle-secret-001")
    assert response.status_code == 200
    assert len(response.headers["x-trace-id"]) == 32

    metrics, media_type = observability.render_metrics()
    text = metrics.decode()
    assert media_type.startswith("text/plain")
    assert (
        'atep_http_requests_total{method="GET",route="/widgets/{widget_id}",status="200"} 1.0'
        in text
    )
    assert "vehicle-secret-001" not in text
    assert 'atep_build_info{environment="test",service="atep-core",version="0.1.0"} 1.0' in text

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "GET /widgets/{widget_id}"
    attributes = spans[0].attributes
    assert attributes is not None
    assert attributes["http.route"] == "/widgets/{widget_id}"


def test_traceparent_is_propagated_to_server_span() -> None:
    app, _, exporter = instrumented_app()
    trace_id = "11111111111111111111111111111111"
    parent_span_id = "2222222222222222"
    response = TestClient(app).get(
        "/widgets/one",
        headers={"traceparent": f"00-{trace_id}-{parent_span_id}-01"},
    )
    assert response.headers["x-trace-id"] == trace_id
    span = exporter.get_finished_spans()[0]
    assert span.context.trace_id == int(trace_id, 16)
    assert span.parent is not None
    assert span.parent.span_id == int(parent_span_id, 16)


def test_unhandled_exception_is_counted_and_marks_span_error() -> None:
    app, observability, exporter = instrumented_app()
    response = TestClient(app, raise_server_exceptions=False).get("/failure")
    assert response.status_code == 500
    metrics = observability.render_metrics()[0].decode()
    assert (
        "atep_http_request_exceptions_total"
        '{exception_type="RuntimeError",method="GET",route="/failure"} 1.0' in metrics
    )
    span = exporter.get_finished_spans()[0]
    assert span.status.status_code.name == "ERROR"
