import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import extract
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    GCCollector,
    Histogram,
    PlatformCollector,
    ProcessCollector,
    generate_latest,
)

from atep.core.config import Settings

type Scope = MutableMapping[str, Any]
type Message = MutableMapping[str, Any]
type Receive = Callable[[], Awaitable[Message]]
type Send = Callable[[Message], Awaitable[None]]
type ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

log = structlog.get_logger()


class Observability:
    def __init__(
        self, settings: Settings, *, tracer_provider: TracerProvider | None = None
    ) -> None:
        self.settings = settings
        self.registry = CollectorRegistry(auto_describe=True)
        GCCollector(registry=self.registry)
        PlatformCollector(registry=self.registry)
        ProcessCollector(registry=self.registry)
        self.requests = Counter(
            "atep_http_requests_total",
            "Completed ATEP HTTP requests.",
            ("method", "route", "status"),
            registry=self.registry,
        )
        self.duration = Histogram(
            "atep_http_request_duration_seconds",
            "ATEP HTTP request duration in seconds.",
            ("method", "route"),
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
            registry=self.registry,
        )
        self.in_progress = Gauge(
            "atep_http_requests_in_progress",
            "ATEP HTTP requests currently executing.",
            ("method",),
            registry=self.registry,
        )
        self.exceptions = Counter(
            "atep_http_request_exceptions_total",
            "Unhandled exceptions raised while serving ATEP HTTP requests.",
            ("method", "route", "exception_type"),
            registry=self.registry,
        )
        info = Gauge(
            "atep_build_info",
            "ATEP service build and environment information.",
            ("service", "version", "environment"),
            registry=self.registry,
        )
        info.labels(settings.otel_service_name, "0.1.0", settings.environment).set(1)

        self.tracer_provider = tracer_provider or self._build_tracer_provider(settings)
        self.tracer: Tracer = self.tracer_provider.get_tracer("atep.http", "0.1.0")

    def render_metrics(self) -> tuple[bytes, str]:
        return generate_latest(self.registry), CONTENT_TYPE_LATEST

    def shutdown(self) -> None:
        self.tracer_provider.shutdown()

    @staticmethod
    def _build_tracer_provider(settings: Settings) -> TracerProvider:
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": settings.otel_service_name,
                    "service.version": "0.1.0",
                    "deployment.environment.name": settings.environment,
                }
            ),
            sampler=ParentBased(
                TraceIdRatioBased(
                    settings.otel_trace_sample_ratio if settings.tracing_enabled else 0.0
                )
            ),
        )
        if settings.tracing_enabled and settings.otel_exporter_otlp_endpoint:
            exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, timeout=5)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        elif settings.tracing_enabled:
            log.warning("otel_exporter_not_configured")
        return provider


class ObservabilityMiddleware:
    def __init__(self, app: ASGIApp, *, observability: Observability) -> None:
        self.app = app
        self.observability = observability

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "UNKNOWN")).upper()
        status_code = 500
        started_at = time.perf_counter()
        headers = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        parent_context = extract(headers)
        self.observability.in_progress.labels(method).inc()
        with self.observability.tracer.start_as_current_span(
            f"HTTP {method}",
            context=parent_context,
            kind=SpanKind.SERVER,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            span.set_attribute("http.request.method", method)
            span_context = span.get_span_context()
            trace_id = f"{span_context.trace_id:032x}"
            span_id = f"{span_context.span_id:016x}"

            async def send_with_trace(message: Message) -> None:
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = int(message["status"])
                    response_headers = list(message.get("headers", []))
                    response_headers.append((b"x-trace-id", trace_id.encode("ascii")))
                    message["headers"] = response_headers
                await send(message)

            try:
                await self.app(scope, receive, send_with_trace)
            except BaseException as exc:
                route = _route_template(scope)
                self.observability.exceptions.labels(method, route, type(exc).__name__).inc()
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR))
                raise
            finally:
                route = _route_template(scope)
                duration = time.perf_counter() - started_at
                self.observability.in_progress.labels(method).dec()
                self.observability.requests.labels(method, route, str(status_code)).inc()
                self.observability.duration.labels(method, route).observe(duration)
                span.update_name(f"{method} {route}")
                span.set_attribute("http.route", route)
                span.set_attribute("http.response.status_code", status_code)
                if status_code >= 500:
                    span.set_status(Status(StatusCode.ERROR))
                state = scope.get("state", {})
                correlation_id = (
                    state.get("correlation_id")
                    if isinstance(state, MutableMapping)
                    else getattr(state, "correlation_id", None)
                )
                if correlation_id is not None:
                    span.set_attribute("atep.correlation_id", str(correlation_id))
                structlog.contextvars.bind_contextvars(trace_id=trace_id, span_id=span_id)


def current_trace_context() -> dict[str, str]:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return {}
    return {
        "trace_id": f"{span_context.trace_id:032x}",
        "span_id": f"{span_context.span_id:016x}",
    }


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    return str(path) if path else "unmatched"
