from datetime import datetime
from enum import StrEnum
from typing import Annotated

import structlog
from fastapi import FastAPI, Response, status
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    generate_latest,
)
from pydantic import BaseModel, Field, StringConstraints

log = structlog.get_logger()

LabelName = Annotated[str, StringConstraints(max_length=256)]
LabelValue = Annotated[str, StringConstraints(max_length=2048)]


class AlertStatus(StrEnum):
    FIRING = "firing"
    RESOLVED = "resolved"


class AlertItem(BaseModel):
    status: AlertStatus
    labels: dict[LabelName, LabelValue] = Field(default_factory=dict, max_length=50)
    annotations: dict[LabelName, LabelValue] = Field(default_factory=dict, max_length=50)
    startsAt: datetime  # noqa: N815 - Alertmanager wire contract
    endsAt: datetime | None = None  # noqa: N815 - Alertmanager wire contract
    generatorURL: str = Field(default="", max_length=2048)  # noqa: N815
    fingerprint: str = Field(default="", max_length=128)


class AlertWebhookPayload(BaseModel):
    version: str = Field(max_length=20)
    groupKey: str = Field(max_length=500)  # noqa: N815 - Alertmanager wire contract
    truncatedAlerts: int = Field(default=0, ge=0)  # noqa: N815
    status: AlertStatus
    receiver: str = Field(max_length=100)
    groupLabels: dict[LabelName, LabelValue] = Field(  # noqa: N815
        default_factory=dict, max_length=50
    )
    commonLabels: dict[LabelName, LabelValue] = Field(  # noqa: N815
        default_factory=dict, max_length=50
    )
    commonAnnotations: dict[LabelName, LabelValue] = Field(  # noqa: N815
        default_factory=dict, max_length=50
    )
    externalURL: str = Field(default="", max_length=2048)  # noqa: N815
    alerts: list[AlertItem] = Field(min_length=1, max_length=50)


class AlertReceiver:
    def __init__(self) -> None:
        self.registry = CollectorRegistry(auto_describe=True)
        self.notifications = Counter(
            "atep_alert_webhook_notifications_total",
            "Alertmanager webhook notifications accepted by bounded severity and status.",
            ("severity", "status"),
            registry=self.registry,
        )
        self.alerts = Counter(
            "atep_alert_webhook_alerts_total",
            "Individual alerts accepted from Alertmanager by bounded severity and status.",
            ("severity", "status"),
            registry=self.registry,
        )
        self.last_received = Gauge(
            "atep_alert_webhook_last_received_timestamp_seconds",
            "Unix timestamp of the last accepted Alertmanager webhook notification.",
            registry=self.registry,
        )

    def accept(self, payload: AlertWebhookPayload) -> int:
        notification_severity = _severity(payload.commonLabels.get("severity"))
        self.notifications.labels(notification_severity, payload.status.value).inc()
        for alert in payload.alerts:
            severity = _severity(alert.labels.get("severity"))
            self.alerts.labels(severity, alert.status.value).inc()
        self.last_received.set_to_current_time()
        log.info(
            "alert_webhook_notification_accepted",
            alert_count=len(payload.alerts),
            severity=notification_severity,
            status=payload.status.value,
        )
        return len(payload.alerts)

    def render_metrics(self) -> tuple[bytes, str]:
        return generate_latest(self.registry), CONTENT_TYPE_LATEST


def _severity(value: str | None) -> str:
    normalized = value.casefold() if value is not None else ""
    return normalized if normalized in {"critical", "warning", "info"} else "unknown"


receiver = AlertReceiver()
app = FastAPI(
    title="ATEP Local Alert Webhook",
    version="0.1.0",
    description="Internal aggregate-only receiver for disposable development alert delivery.",
)


@app.get("/health/live", include_in_schema=False)
async def live() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    content, media_type = receiver.render_metrics()
    return Response(content=content, media_type=media_type)


@app.post("/api/v1/alerts", status_code=status.HTTP_202_ACCEPTED)
async def receive_alerts(payload: AlertWebhookPayload) -> dict[str, int]:
    return {"accepted": receiver.accept(payload)}
