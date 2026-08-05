from fastapi.testclient import TestClient

from atep.alerts.receiver import app


def alertmanager_payload(*, severity: str = "critical") -> dict[str, object]:
    return {
        "version": "4",
        "groupKey": '{}:{alertname="AtepDeliveryProbe"}',
        "truncatedAlerts": 0,
        "status": "firing",
        "receiver": "local-webhook",
        "groupLabels": {"alertname": "AtepDeliveryProbe"},
        "commonLabels": {
            "alertname": "AtepDeliveryProbe",
            "service": "atep-alerting",
            "severity": severity,
        },
        "commonAnnotations": {"summary": "Development delivery probe"},
        "externalURL": "http://alertmanager:9093",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "AtepDeliveryProbe",
                    "service": "atep-alerting",
                    "severity": severity,
                    "vehicle_id": "vehicle-secret-001",
                },
                "annotations": {"secret": "must-not-enter-metrics"},
                "startsAt": "2026-08-05T12:00:00Z",
                "endsAt": "2026-08-05T13:00:00Z",
                "generatorURL": "http://prometheus:9090/graph",
                "fingerprint": "abcdef0123456789",
            }
        ],
    }


def test_local_webhook_accepts_alertmanager_contract_without_persisting_labels() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/alerts", json=alertmanager_payload())
    assert response.status_code == 202
    assert response.json() == {"accepted": 1}

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert (
        'atep_alert_webhook_notifications_total{severity="critical",status="firing"} 1.0'
        in metrics.text
    )
    assert (
        'atep_alert_webhook_alerts_total{severity="critical",status="firing"} 1.0' in metrics.text
    )
    assert "vehicle-secret-001" not in metrics.text
    assert "must-not-enter-metrics" not in metrics.text


def test_local_webhook_maps_untrusted_severity_to_bounded_unknown_label() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/alerts", json=alertmanager_payload(severity="custom-secret"))
    assert response.status_code == 202
    metrics = client.get("/metrics").text
    assert 'severity="unknown"' in metrics
    assert "custom-secret" not in metrics

    oversized = alertmanager_payload()
    oversized["commonAnnotations"] = {"summary": "x" * 2049}
    invalid = client.post("/api/v1/alerts", json=oversized)
    assert invalid.status_code == 422
