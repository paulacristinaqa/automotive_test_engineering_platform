import asyncio
import json
import os
from typing import Any, cast
from uuid import uuid4

import aio_pika
import asyncpg  # type: ignore[import-untyped]
import httpx
import pytest
import websockets

pytestmark = pytest.mark.integration


def required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.fail(f"Required integration environment variable is missing: {name}")
    return value


async def wait_for_published_event(connection: Any, user_id: str) -> asyncpg.Record:
    for _ in range(40):
        row = await connection.fetchrow(
            """
            SELECT event_type, payload, published_at
            FROM outbox_events
            WHERE aggregate_id = $1::uuid
            """,
            user_id,
        )
        if row is not None and row["published_at"] is not None:
            return row
        await asyncio.sleep(0.25)
    pytest.fail("The user-created outbox event was not published within 10 seconds.")


async def wait_for_message(
    queue: aio_pika.abc.AbstractQueue,
) -> aio_pika.abc.AbstractIncomingMessage:
    for _ in range(40):
        message = await queue.get(timeout=1, fail=False)
        if message is not None:
            return message
        await asyncio.sleep(0.25)
    pytest.fail("The RabbitMQ event was not received within 10 seconds.")


async def wait_for_stream_event(stream: Any, event_type: str) -> dict[str, Any]:
    for _ in range(5):
        event = json.loads(await asyncio.wait_for(stream.recv(), timeout=5))
        if event["type"] == event_type:
            return cast(dict[str, Any], event)
    pytest.fail(f"The WebSocket event {event_type} was not received.")


async def wait_for_metric(client: httpx.AsyncClient, sample: str) -> httpx.Response:
    for _ in range(20):
        response = await client.get("/metrics")
        assert response.status_code == 200, response.text
        if sample in response.text:
            return response
        await asyncio.sleep(0.05)
    pytest.fail(f"The metric sample {sample!r} was not observed within one second.")


async def expected_error(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    status_code: int,
    **kwargs: Any,
) -> dict[str, Any]:
    response = await client.request(method, path, **kwargs)
    assert response.status_code == status_code, response.text
    body = response.json()
    assert body["correlation_id"]
    return cast(dict[str, Any], body["error"])


@pytest.mark.asyncio
async def test_administrator_identity_event_and_audit_flow() -> None:
    api_url = required_environment("ATEP_INTEGRATION_API_URL")
    database_url = required_environment("ATEP_INTEGRATION_DATABASE_URL")
    rabbitmq_url = required_environment("ATEP_INTEGRATION_RABBITMQ_URL")
    outbox_metrics_url = required_environment("ATEP_INTEGRATION_OUTBOX_METRICS_URL")
    admin_email = required_environment("ATEP_INTEGRATION_ADMIN_EMAIL")
    admin_password = required_environment("ATEP_INTEGRATION_ADMIN_PASSWORD")

    database = await asyncpg.connect(database_url)
    broker = await aio_pika.connect_robust(rabbitmq_url)
    try:
        channel = await broker.channel()
        exchange = await channel.declare_exchange(
            "atep.events", aio_pika.ExchangeType.TOPIC, durable=True
        )
        queue = await channel.declare_queue(exclusive=True, auto_delete=True)
        await queue.bind(exchange, routing_key="atep.identity.user.created.v1")

        async with httpx.AsyncClient(base_url=api_url, timeout=10) as client:
            propagated_trace_id = "11111111111111111111111111111111"
            live_response = await client.get(
                "/health/live",
                headers={"traceparent": f"00-{propagated_trace_id}-2222222222222222-01"},
            )
            assert live_response.status_code == 200, live_response.text
            assert live_response.headers["x-trace-id"] == propagated_trace_id
            metrics_response = await wait_for_metric(client, 'route="/health/live"')
            assert "atep_http_requests_total" in metrics_response.text

            token_response = await client.post(
                "/api/v1/auth/token",
                data={"username": admin_email, "password": admin_password},
            )
            assert token_response.status_code == 200, token_response.text
            assert token_response.headers["x-ratelimit-limit"] == "5"
            assert int(token_response.headers["x-ratelimit-remaining"]) >= 0
            admin_headers = {
                "Authorization": f"Bearer {token_response.json()['access_token']}",
                "X-Correlation-ID": str(uuid4()),
            }

            permissions_response = await client.get("/api/v1/permissions", headers=admin_headers)
            assert permissions_response.status_code == 200, permissions_response.text
            permission_names = {item["name"] for item in permissions_response.json()}
            assert {
                "users:read",
                "users:write",
                "roles:manage",
                "audit:read",
                "audit:export",
                "modules:read",
                "modules:manage",
                "vehicles:read",
                "vehicles:manage",
                "telemetry:read",
                "digital_vehicle:read",
                "digital_vehicle:write",
                "test_runs:read",
                "test_runs:write",
            } <= permission_names

            module_name = f"integration-can-{uuid4().hex[:12]}"
            module_command = {
                "name": module_name,
                "display_name": "Integration CAN Simulator",
                "description": "Disposable module registration",
                "version": "1.0.0",
                "base_url": "http://can-simulator:8080",
                "capabilities": [
                    {
                        "name": "can.frames.publish",
                        "version": "1.0.0",
                        "description": "Publish simulated CAN frames",
                    }
                ],
            }
            module_create_response = await client.post(
                "/api/v1/modules", headers=admin_headers, json=module_command
            )
            assert module_create_response.status_code == 201, module_create_response.text
            module = module_create_response.json()
            module_id = module["id"]
            assert module["status"] == "registered"
            assert [item["name"] for item in module["capabilities"]] == ["can.frames.publish"]

            duplicate_module = await expected_error(
                client,
                "POST",
                "/api/v1/modules",
                409,
                headers=admin_headers,
                json=module_command,
            )
            assert duplicate_module["code"] == "module_name_already_exists"

            module_page_response = await client.get(
                "/api/v1/modules",
                headers=admin_headers,
                params={"capability": "can.frames.publish", "limit": 100},
            )
            assert module_page_response.status_code == 200, module_page_response.text
            assert any(item["id"] == module_id for item in module_page_response.json()["items"])

            module_update_response = await client.patch(
                f"/api/v1/modules/{module_id}",
                headers=admin_headers,
                json={"version": "1.1.0"},
            )
            assert module_update_response.status_code == 200, module_update_response.text
            assert module_update_response.json()["status"] == "registered"

            credential_response = await client.post(
                f"/api/v1/modules/{module_id}/credentials",
                headers=admin_headers,
                json={"lease_duration_seconds": 5},
            )
            assert credential_response.status_code == 200, credential_response.text
            module_token = credential_response.json()["module_token"]
            assert len(module_token) >= 32
            stored_module_token = await database.fetchval(
                "SELECT heartbeat_token_hash FROM platform_modules WHERE id = $1::uuid",
                module_id,
            )
            assert stored_module_token != module_token
            assert len(stored_module_token) == 64

            invalid_heartbeat = await expected_error(
                client,
                "POST",
                f"/api/v1/modules/{module_id}/heartbeat",
                401,
                headers={"X-ATEP-Module-Token": "invalid-module-token-with-sufficient-length"},
                json={"status": "active"},
            )
            assert invalid_heartbeat["code"] == "invalid_module_credential"

            heartbeat_response = await client.post(
                f"/api/v1/modules/{module_id}/heartbeat",
                headers={"X-ATEP-Module-Token": module_token},
                json={"status": "degraded", "version": "1.2.0"},
            )
            assert heartbeat_response.status_code == 200, heartbeat_response.text
            heartbeat_module = heartbeat_response.json()
            assert heartbeat_module["status"] == "degraded"
            assert heartbeat_module["version"] == "1.2.0"
            assert heartbeat_module["last_seen_at"]
            assert heartbeat_module["lease_expires_at"]
            assert heartbeat_module["lease_duration_seconds"] == 5

            health_response = await client.get(
                "/api/v1/modules/health-summary", headers=admin_headers
            )
            assert health_response.status_code == 200, health_response.text
            health = health_response.json()
            assert health["status"] == "unavailable"
            assert health["objective_met"] is False
            assert health["monitored_modules"] == 1
            assert health["counts"] == {
                "registered": 0,
                "active": 0,
                "degraded": 1,
                "inactive": 0,
            }

            capability_response = await client.put(
                f"/api/v1/modules/{module_id}/capabilities/can.frames.consume",
                headers=admin_headers,
                json={"version": "1.0.0", "description": "Consume CAN frames"},
            )
            assert capability_response.status_code == 200, capability_response.text
            assert {item["name"] for item in capability_response.json()["capabilities"]} == {
                "can.frames.consume",
                "can.frames.publish",
            }
            capability_removal = await client.delete(
                f"/api/v1/modules/{module_id}/capabilities/can.frames.consume",
                headers=admin_headers,
            )
            assert capability_removal.status_code == 200, capability_removal.text
            assert [item["name"] for item in capability_removal.json()["capabilities"]] == [
                "can.frames.publish"
            ]

            for _ in range(16):
                await asyncio.sleep(0.5)
                reconciled_module = await client.get(
                    f"/api/v1/modules/{module_id}", headers=admin_headers
                )
                assert reconciled_module.status_code == 200, reconciled_module.text
                if reconciled_module.json()["status"] == "inactive":
                    break
            else:
                pytest.fail("The expired module lease was not reconciled within 8 seconds.")

            vehicle_identifier = f"vehicle-{uuid4().hex[:12]}"
            vehicle_response = await client.post(
                "/api/v1/vehicles",
                headers=admin_headers,
                json={
                    "identifier": vehicle_identifier,
                    "display_name": "Integration EV",
                    "model": "ATEP Reference Vehicle",
                    "description": "Disposable Android Automotive integration vehicle",
                },
            )
            assert vehicle_response.status_code == 201, vehicle_response.text
            vehicle = vehicle_response.json()
            vehicle_uuid = vehicle["id"]
            assert vehicle["status"] == "registered"

            duplicate_vehicle = await expected_error(
                client,
                "POST",
                "/api/v1/vehicles",
                409,
                headers=admin_headers,
                json={
                    "identifier": vehicle_identifier.upper(),
                    "display_name": "Duplicate Integration EV",
                },
            )
            assert duplicate_vehicle["code"] == "vehicle_identifier_already_exists"

            active_vehicle = await client.patch(
                f"/api/v1/vehicles/{vehicle_identifier}/status",
                headers=admin_headers,
                json={"status": "active"},
            )
            assert active_vehicle.status_code == 200, active_vehicle.text
            assert active_vehicle.json()["status"] == "active"

            initial_state = await client.get(
                f"/api/v1/vehicles/{vehicle_identifier}/state", headers=admin_headers
            )
            assert initial_state.status_code == 200, initial_state.text
            assert initial_state.json()["version"] == 1
            assert initial_state.json()["operational_mode"] == "parked"
            assert initial_state.json()["brakes"]["parking_brake_applied"] is True

            driving_state_payload = {
                "expected_version": 1,
                "operational_mode": "driving",
                "battery": {
                    "state_of_charge_pct": 79.5,
                    "state_of_health_pct": 99.8,
                    "pack_voltage_v": 398.0,
                    "pack_current_a": 120.0,
                    "temperature_c": 31.0,
                    "contactors_closed": True,
                    "charging_status": "disconnected",
                },
                "powertrain": {
                    "motor_enabled": True,
                    "gear": "drive",
                    "speed_kph": 45.0,
                    "requested_torque_nm": 180.0,
                    "delivered_torque_nm": 176.0,
                },
                "brakes": {
                    "pedal_pct": 0.0,
                    "hydraulic_pressure_bar": 0.0,
                    "parking_brake_applied": False,
                    "abs_active": False,
                },
                "steering": {"wheel_angle_deg": 3.5, "assist_active": True},
                "lighting": {
                    "exterior_mode": "auto",
                    "brake_lights": False,
                    "indicator": "off",
                },
            }
            driving_state = await client.put(
                f"/api/v1/vehicles/{vehicle_identifier}/state",
                headers=admin_headers,
                json=driving_state_payload,
            )
            assert driving_state.status_code == 200, driving_state.text
            assert driving_state.json()["version"] == 2
            assert driving_state.json()["powertrain"]["speed_kph"] == 45.0

            repeated_state = await client.put(
                f"/api/v1/vehicles/{vehicle_identifier}/state",
                headers=admin_headers,
                json=driving_state_payload,
            )
            assert repeated_state.status_code == 200, repeated_state.text
            assert repeated_state.json()["version"] == 2

            stale_state = await expected_error(
                client,
                "PUT",
                f"/api/v1/vehicles/{vehicle_identifier}/state",
                409,
                headers=admin_headers,
                json={"expected_version": 1},
            )
            assert stale_state["code"] == "vehicle_state_version_conflict"
            assert stale_state["details"] == {"current_version": 2}

            simulation_command = {
                "command_id": f"simulation-{uuid4().hex}",
                "expected_version": 2,
                "target_mode": "parked",
                "duration_ms": 750,
            }
            simulation_transition = await client.post(
                f"/api/v1/vehicles/{vehicle_identifier}/simulation/transitions",
                headers=admin_headers,
                json=simulation_command,
            )
            assert simulation_transition.status_code == 201, simulation_transition.text
            assert simulation_transition.json()["from_mode"] == "driving"
            assert simulation_transition.json()["to_mode"] == "parked"
            assert simulation_transition.json()["state_version"] == 3
            assert simulation_transition.json()["simulation_time_ms"] == 750
            assert simulation_transition.json()["duplicate"] is False

            repeated_transition = await client.post(
                f"/api/v1/vehicles/{vehicle_identifier}/simulation/transitions",
                headers=admin_headers,
                json=simulation_command,
            )
            assert repeated_transition.status_code == 200, repeated_transition.text
            assert repeated_transition.json()["duplicate"] is True
            assert repeated_transition.json()["simulation_time_ms"] == 750

            parked_state = await client.get(
                f"/api/v1/vehicles/{vehicle_identifier}/state", headers=admin_headers
            )
            assert parked_state.status_code == 200, parked_state.text
            assert parked_state.json()["version"] == 3
            assert parked_state.json()["simulation_time_ms"] == 750
            assert parked_state.json()["operational_mode"] == "parked"

            test_run_id = uuid4().hex
            test_run_payload = {
                "run_id": test_run_id,
                "vehicle_id": vehicle_identifier,
                "name": "Integration battery thermal smoke test",
                "suite": "smoke",
                "metadata": {"requirement": "CORE-F-038"},
            }
            created_test_run = await client.post(
                "/api/v1/test-runs", headers=admin_headers, json=test_run_payload
            )
            assert created_test_run.status_code == 201, created_test_run.text
            assert created_test_run.json()["status"] == "queued"
            assert created_test_run.json()["version"] == 1

            duplicate_test_run = await client.post(
                "/api/v1/test-runs", headers=admin_headers, json=test_run_payload
            )
            assert duplicate_test_run.status_code == 200, duplicate_test_run.text
            assert duplicate_test_run.json()["id"] == created_test_run.json()["id"]

            test_run_conflict = await expected_error(
                client,
                "POST",
                "/api/v1/test-runs",
                409,
                headers=admin_headers,
                json={**test_run_payload, "name": "Different test"},
            )
            assert test_run_conflict["code"] == "test_run_conflict"

            ws_url = (
                api_url.replace("https://", "wss://").replace("http://", "ws://")
                + f"/api/v1/test-runs/{test_run_id}/stream"
            )
            async with websockets.connect(
                ws_url,
                additional_headers={"Authorization": admin_headers["Authorization"]},
            ) as stream:
                snapshot = await wait_for_stream_event(stream, "atep.test_run.snapshot.v1")
                assert snapshot["type"] == "atep.test_run.snapshot.v1"
                assert snapshot["test_run"]["version"] == 1

                running_test_run = await client.patch(
                    f"/api/v1/test-runs/{test_run_id}/status",
                    headers=admin_headers,
                    json={
                        "expected_version": 1,
                        "status": "running",
                        "progress_percent": 25,
                        "summary": "Executing vehicle commands",
                    },
                )
                assert running_test_run.status_code == 200, running_test_run.text
                running_event = await wait_for_stream_event(stream, "atep.test_run.updated.v1")
                assert running_event["test_run"]["status"] == "running"
                assert running_event["test_run"]["version"] == 2

                exact_retry = await client.patch(
                    f"/api/v1/test-runs/{test_run_id}/status",
                    headers=admin_headers,
                    json={
                        "expected_version": 1,
                        "status": "running",
                        "progress_percent": 25,
                        "summary": "Executing vehicle commands",
                    },
                )
                assert exact_retry.status_code == 200, exact_retry.text
                assert exact_retry.json()["version"] == 2

                stale_update = await expected_error(
                    client,
                    "PATCH",
                    f"/api/v1/test-runs/{test_run_id}/status",
                    409,
                    headers=admin_headers,
                    json={
                        "expected_version": 1,
                        "status": "running",
                        "progress_percent": 50,
                    },
                )
                assert stale_update["code"] == "test_run_version_conflict"
                assert stale_update["details"]["current_version"] == 2

                passed_test_run = await client.patch(
                    f"/api/v1/test-runs/{test_run_id}/status",
                    headers=admin_headers,
                    json={
                        "expected_version": 2,
                        "status": "passed",
                        "progress_percent": 100,
                        "summary": "All assertions passed",
                    },
                )
                assert passed_test_run.status_code == 200, passed_test_run.text
                passed_event = await wait_for_stream_event(stream, "atep.test_run.updated.v1")
                assert passed_event["test_run"]["status"] == "passed"
                assert passed_event["test_run"]["version"] == 3

            illegal_transition = await expected_error(
                client,
                "PATCH",
                f"/api/v1/test-runs/{test_run_id}/status",
                409,
                headers=admin_headers,
                json={
                    "expected_version": 3,
                    "status": "running",
                    "progress_percent": 80,
                },
            )
            assert illegal_transition["code"] == "test_run_state_conflict"

            test_run_page = await client.get(
                "/api/v1/test-runs",
                headers=admin_headers,
                params={"vehicle_id": vehicle_identifier, "status": "passed"},
            )
            assert test_run_page.status_code == 200, test_run_page.text
            assert test_run_page.json()["total"] == 1
            assert test_run_page.json()["items"][0]["run_id"] == test_run_id

            artifact_id = uuid4().hex
            artifact_content = b'{"result":"passed","temperature_celsius":47.8}'
            artifact_upload = await client.post(
                f"/api/v1/test-runs/{test_run_id}/artifacts",
                headers=admin_headers,
                data={"artifact_id": artifact_id, "kind": "report"},
                files={
                    "file": (
                        "battery-report.json",
                        artifact_content,
                        "application/json",
                    )
                },
            )
            assert artifact_upload.status_code == 201, artifact_upload.text
            artifact = artifact_upload.json()
            artifact_uuid = artifact["id"]
            assert artifact["size_bytes"] == len(artifact_content)
            assert len(artifact["sha256"]) == 64
            assert "object_key" not in artifact

            duplicate_artifact = await client.post(
                f"/api/v1/test-runs/{test_run_id}/artifacts",
                headers=admin_headers,
                data={"artifact_id": artifact_id, "kind": "report"},
                files={"file": ("battery-report.json", artifact_content, "application/json")},
            )
            assert duplicate_artifact.status_code == 200, duplicate_artifact.text
            assert duplicate_artifact.json()["id"] == artifact_uuid

            artifact_conflict = await expected_error(
                client,
                "POST",
                f"/api/v1/test-runs/{test_run_id}/artifacts",
                409,
                headers=admin_headers,
                data={"artifact_id": artifact_id, "kind": "report"},
                files={"file": ("battery-report.json", b"different", "application/json")},
            )
            assert artifact_conflict["code"] == "test_artifact_conflict"

            oversized_artifact = await expected_error(
                client,
                "POST",
                f"/api/v1/test-runs/{test_run_id}/artifacts",
                413,
                headers=admin_headers,
                data={"artifact_id": uuid4().hex, "kind": "binary"},
                files={"file": ("bounded.bin", b"x" * 1025, "application/octet-stream")},
            )
            assert oversized_artifact["code"] == "test_artifact_too_large"
            assert oversized_artifact["details"] == {"max_bytes": 1024}

            empty_artifact = await expected_error(
                client,
                "POST",
                f"/api/v1/test-runs/{test_run_id}/artifacts",
                422,
                headers=admin_headers,
                data={"artifact_id": uuid4().hex, "kind": "log"},
                files={"file": ("empty.log", b"", "text/plain")},
            )
            assert empty_artifact["code"] == "empty_test_artifact"

            unsafe_filename = await expected_error(
                client,
                "POST",
                f"/api/v1/test-runs/{test_run_id}/artifacts",
                422,
                headers=admin_headers,
                data={"artifact_id": uuid4().hex, "kind": "report"},
                files={"file": ("../unsafe.json", b"{}", "application/json")},
            )
            assert unsafe_filename["code"] == "validation_error"

            artifact_page = await client.get(
                f"/api/v1/test-runs/{test_run_id}/artifacts",
                headers=admin_headers,
                params={"kind": "report"},
            )
            assert artifact_page.status_code == 200, artifact_page.text
            assert artifact_page.json()["total"] == 1
            artifact_download = await client.get(
                f"/api/v1/test-runs/{test_run_id}/artifacts/{artifact_id}/content",
                headers=admin_headers,
            )
            assert artifact_download.status_code == 200, artifact_download.text
            assert artifact_download.content == artifact_content
            assert artifact_download.headers["x-content-sha256"] == artifact["sha256"]

            scheduled_job_id = uuid4().hex
            scheduled_run_id = uuid4().hex
            scheduled_payload = {
                "job_id": scheduled_job_id,
                "run_id": scheduled_run_id,
                "vehicle_id": vehicle_identifier,
                "name": "Integration scheduled battery smoke test",
                "suite": "smoke",
                "metadata": {"requirement": "CORE-F-046"},
                "scheduled_for": "2099-01-01T00:00:00Z",
            }
            scheduled_job = await client.post(
                "/api/v1/test-jobs", headers=admin_headers, json=scheduled_payload
            )
            assert scheduled_job.status_code == 201, scheduled_job.text
            assert scheduled_job.json()["status"] == "scheduled"

            duplicate_job = await client.post(
                "/api/v1/test-jobs", headers=admin_headers, json=scheduled_payload
            )
            assert duplicate_job.status_code == 200, duplicate_job.text
            assert duplicate_job.json()["id"] == scheduled_job.json()["id"]

            cancelled_job = await client.patch(
                f"/api/v1/test-jobs/{scheduled_job_id}/cancel",
                headers=admin_headers,
                json={"expected_version": 1, "reason": "Integration cancellation"},
            )
            assert cancelled_job.status_code == 200, cancelled_job.text
            assert cancelled_job.json()["status"] == "cancelled"
            assert cancelled_job.json()["version"] == 2

            due_job_id = uuid4().hex
            due_run_id = uuid4().hex
            due_job = await client.post(
                "/api/v1/test-jobs",
                headers=admin_headers,
                json={
                    **scheduled_payload,
                    "job_id": due_job_id,
                    "run_id": due_run_id,
                    "scheduled_for": "2000-01-01T00:00:00Z",
                },
            )
            assert due_job.status_code == 201, due_job.text
            for _ in range(16):
                await asyncio.sleep(0.5)
                dispatched_job = await client.get(
                    f"/api/v1/test-jobs/{due_job_id}", headers=admin_headers
                )
                assert dispatched_job.status_code == 200, dispatched_job.text
                if dispatched_job.json()["status"] == "dispatched":
                    break
            else:
                pytest.fail("The due test job was not dispatched within 8 seconds.")
            dispatched_body = dispatched_job.json()
            assert dispatched_body["test_run_id"]
            generated_run = await client.get(
                f"/api/v1/test-runs/{due_run_id}", headers=admin_headers
            )
            assert generated_run.status_code == 200, generated_run.text
            assert generated_run.json()["status"] == "queued"

            gateway_name = f"integration-gateway-{uuid4().hex[:12]}"
            gateway_response = await client.post(
                "/api/v1/modules",
                headers=admin_headers,
                json={
                    "name": gateway_name,
                    "display_name": "Integration Vehicle Gateway",
                    "version": "1.0.0",
                    "capabilities": [
                        {
                            "name": "vehicle.telemetry.publish",
                            "version": "1.0.0",
                            "description": "Publish Android Automotive telemetry",
                        },
                        {
                            "name": "vehicle.commands.consume",
                            "version": "1.0.0",
                            "description": "Consume leased vehicle commands",
                        },
                    ],
                },
            )
            assert gateway_response.status_code == 201, gateway_response.text
            gateway_id = gateway_response.json()["id"]
            gateway_credential_response = await client.post(
                f"/api/v1/modules/{gateway_id}/credentials",
                headers=admin_headers,
                json={"lease_duration_seconds": 60},
            )
            assert gateway_credential_response.status_code == 200
            gateway_token = gateway_credential_response.json()["module_token"]
            telemetry_event_id = uuid4().hex
            telemetry_payload = {
                "event_id": telemetry_event_id,
                "property": "battery_temperature",
                "value": 47.8,
                "unit": "celsius",
                "timestamp": "2026-07-27T20:30:00Z",
                "source": "android-automotive",
            }

            missing_capability = await expected_error(
                client,
                "POST",
                f"/api/v1/vehicles/{vehicle_identifier}/telemetry",
                403,
                headers={
                    "X-ATEP-Module-ID": module_id,
                    "X-ATEP-Module-Token": module_token,
                },
                json=telemetry_payload,
            )
            assert missing_capability["code"] == "module_capability_required"

            telemetry_headers = {
                "X-ATEP-Module-ID": gateway_id,
                "X-ATEP-Module-Token": gateway_token,
            }
            accepted_telemetry = await client.post(
                f"/api/v1/vehicles/{vehicle_identifier}/telemetry",
                headers=telemetry_headers,
                json=telemetry_payload,
            )
            assert accepted_telemetry.status_code == 202, accepted_telemetry.text
            assert accepted_telemetry.json()["duplicate"] is False

            duplicate_telemetry = await client.post(
                f"/api/v1/vehicles/{vehicle_identifier}/telemetry",
                headers=telemetry_headers,
                json=telemetry_payload,
            )
            assert duplicate_telemetry.status_code == 200, duplicate_telemetry.text
            assert duplicate_telemetry.json()["id"] == accepted_telemetry.json()["id"]
            assert duplicate_telemetry.json()["duplicate"] is True

            conflict_payload = {**telemetry_payload, "value": 48.9}
            telemetry_conflict = await expected_error(
                client,
                "POST",
                f"/api/v1/vehicles/{vehicle_identifier}/telemetry",
                409,
                headers=telemetry_headers,
                json=conflict_payload,
            )
            assert telemetry_conflict["code"] == "telemetry_event_conflict"

            telemetry_page = await client.get(
                f"/api/v1/vehicles/{vehicle_identifier}/telemetry",
                headers=admin_headers,
                params={"property": "battery_temperature"},
            )
            assert telemetry_page.status_code == 200, telemetry_page.text
            assert telemetry_page.json()["total"] == 1
            assert telemetry_page.json()["items"][0]["event_id"] == telemetry_event_id

            command_id = uuid4().hex
            command_payload = {
                "command_id": command_id,
                "target_module_id": gateway_id,
                "test_run_id": uuid4().hex,
                "kind": "set_property",
                "parameters": {"property": "battery_level", "value": 25},
            }
            command_response = await client.post(
                f"/api/v1/vehicles/{vehicle_identifier}/commands",
                headers=admin_headers,
                json=command_payload,
            )
            assert command_response.status_code == 201, command_response.text
            assert command_response.json()["status"] == "pending"

            duplicate_command = await client.post(
                f"/api/v1/vehicles/{vehicle_identifier}/commands",
                headers=admin_headers,
                json=command_payload,
            )
            assert duplicate_command.status_code == 200, duplicate_command.text
            assert duplicate_command.json()["id"] == command_response.json()["id"]

            command_conflict = await expected_error(
                client,
                "POST",
                f"/api/v1/vehicles/{vehicle_identifier}/commands",
                409,
                headers=admin_headers,
                json={
                    **command_payload,
                    "parameters": {"property": "battery_level", "value": 30},
                },
            )
            assert command_conflict["code"] == "vehicle_command_conflict"

            missing_command_capability = await expected_error(
                client,
                "POST",
                f"/api/v1/vehicles/{vehicle_identifier}/commands/claim",
                403,
                headers={
                    "X-ATEP-Module-ID": module_id,
                    "X-ATEP-Module-Token": module_token,
                },
                json={"lease_seconds": 60},
            )
            assert missing_command_capability["code"] == "module_capability_required"

            claimed_command = await client.post(
                f"/api/v1/vehicles/{vehicle_identifier}/commands/claim",
                headers=telemetry_headers,
                json={"lease_seconds": 60},
            )
            assert claimed_command.status_code == 200, claimed_command.text
            claimed = claimed_command.json()
            assert claimed["command_id"] == command_id
            assert claimed["status"] == "claimed"
            assert claimed["attempt_count"] == 1
            claim_token = claimed["claim_token"]
            stored_claim_hash = await database.fetchval(
                "SELECT lease_token_hash FROM vehicle_commands WHERE command_id = $1",
                command_id,
            )
            assert stored_claim_hash != claim_token
            assert len(stored_claim_hash) == 64

            acknowledgement_payload = {
                "claim_token": claim_token,
                "outcome": "succeeded",
                "result": {"property": "battery_level", "applied": True},
            }
            acknowledgement = await client.post(
                f"/api/v1/vehicles/{vehicle_identifier}/commands/{command_id}/acknowledgement",
                headers=telemetry_headers,
                json=acknowledgement_payload,
            )
            assert acknowledgement.status_code == 200, acknowledgement.text
            assert acknowledgement.json()["status"] == "succeeded"

            duplicate_acknowledgement = await client.post(
                f"/api/v1/vehicles/{vehicle_identifier}/commands/{command_id}/acknowledgement",
                headers=telemetry_headers,
                json=acknowledgement_payload,
            )
            assert duplicate_acknowledgement.status_code == 200

            command_page = await client.get(
                f"/api/v1/vehicles/{vehicle_identifier}/commands",
                headers=admin_headers,
            )
            assert command_page.status_code == 200, command_page.text
            assert command_page.json()["total"] == 1
            assert command_page.json()["items"][0]["status"] == "succeeded"
            assert (
                await database.fetchval(
                    "SELECT count(*) FROM outbox_events WHERE aggregate_id = $1::uuid",
                    command_response.json()["id"],
                )
                == 3
            )

            role_name = f"integration-qa-{uuid4().hex[:12]}"
            role_command = {
                "name": role_name,
                "description": "Integration test role",
                "permissions": ["users:read"],
            }
            role_create_response = await client.post(
                "/api/v1/roles", headers=admin_headers, json=role_command
            )
            assert role_create_response.status_code == 201, role_create_response.text
            role = role_create_response.json()
            role_id = role["id"]
            assert role["permissions"] == ["users:read"]

            duplicate_role = await expected_error(
                client,
                "POST",
                "/api/v1/roles",
                409,
                headers=admin_headers,
                json=role_command,
            )
            assert duplicate_role["code"] == "role_name_already_exists"

            role_page_response = await client.get(
                "/api/v1/roles", headers=admin_headers, params={"limit": 100}
            )
            assert role_page_response.status_code == 200, role_page_response.text
            role_page = role_page_response.json()
            platform_admin = next(
                item for item in role_page["items"] if item["name"] == "platform-admin"
            )
            assert any(item["id"] == role_id for item in role_page["items"])

            protected_delete = await expected_error(
                client,
                "DELETE",
                f"/api/v1/roles/{platform_admin['id']}",
                409,
                headers=admin_headers,
            )
            assert protected_delete["code"] == "protected_role"

            role_detail_response = await client.get(
                f"/api/v1/roles/{role_id}", headers=admin_headers
            )
            assert role_detail_response.status_code == 200, role_detail_response.text
            role_update_response = await client.patch(
                f"/api/v1/roles/{role_id}",
                headers=admin_headers,
                json={"description": "Updated integration test role"},
            )
            assert role_update_response.status_code == 200, role_update_response.text

            grant_response = await client.put(
                f"/api/v1/roles/{role_id}/permissions/roles:manage",
                headers=admin_headers,
            )
            assert grant_response.status_code == 200, grant_response.text
            assert "roles:manage" in grant_response.json()["permissions"]
            revoke_response = await client.delete(
                f"/api/v1/roles/{role_id}/permissions/roles:manage",
                headers=admin_headers,
            )
            assert revoke_response.status_code == 200, revoke_response.text
            assert "roles:manage" not in revoke_response.json()["permissions"]

            email = f"integration-{uuid4().hex}@example.com"
            password = f"Integration-{uuid4().hex}!"
            command = {
                "email": email,
                "display_name": "Integration Engineer",
                "password": password,
            }
            create_response = await client.post(
                "/api/v1/users", headers=admin_headers, json=command
            )
            assert create_response.status_code == 201, create_response.text
            created = create_response.json()
            user_id = created["id"]
            assert "password" not in created
            assert "password_hash" not in created

            stored = await database.fetchrow(
                "SELECT email, password_hash FROM users WHERE id = $1::uuid", user_id
            )
            assert stored is not None
            assert stored["email"] == email
            assert password not in stored["password_hash"]
            assert (
                await database.fetchval(
                    "SELECT count(*) FROM outbox_events WHERE aggregate_id = $1::uuid",
                    user_id,
                )
                == 1
            )

            duplicate = await expected_error(
                client,
                "POST",
                "/api/v1/users",
                409,
                headers=admin_headers,
                json=command,
            )
            assert duplicate["code"] == "email_already_exists"

            page_response = await client.get(
                "/api/v1/users", headers=admin_headers, params={"limit": 100, "offset": 0}
            )
            assert page_response.status_code == 200, page_response.text
            page = page_response.json()
            assert page["limit"] == 100
            assert any(item["id"] == user_id for item in page["items"])

            detail_response = await client.get(f"/api/v1/users/{user_id}", headers=admin_headers)
            assert detail_response.status_code == 200, detail_response.text
            assert detail_response.json()["email"] == email

            validation = await expected_error(
                client,
                "GET",
                "/api/v1/users?limit=101",
                422,
                headers=admin_headers,
            )
            assert validation["code"] == "validation_error"

            assignment_response = await client.put(
                f"/api/v1/users/{user_id}/roles/{role_id}", headers=admin_headers
            )
            assert assignment_response.status_code == 200, assignment_response.text
            assert role_name in assignment_response.json()["roles"]

            role_in_use = await expected_error(
                client,
                "DELETE",
                f"/api/v1/roles/{role_id}",
                409,
                headers=admin_headers,
            )
            assert role_in_use["code"] == "role_in_use"

            user_token_response = await client.post(
                "/api/v1/auth/token", data={"username": email, "password": password}
            )
            assert user_token_response.status_code == 200, user_token_response.text
            first_pair = user_token_response.json()
            first_refresh_token = first_pair["refresh_token"]
            assert first_pair["refresh_expires_in"] > first_pair["expires_in"]

            refresh_response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": first_refresh_token},
            )
            assert refresh_response.status_code == 200, refresh_response.text
            rotated_pair = refresh_response.json()
            assert rotated_pair["refresh_token"] != first_refresh_token
            refreshed_me = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {rotated_pair['access_token']}"},
            )
            assert refreshed_me.status_code == 200, refreshed_me.text

            reuse = await expected_error(
                client,
                "POST",
                "/api/v1/auth/refresh",
                401,
                json={"refresh_token": first_refresh_token},
            )
            assert reuse["code"] == "invalid_refresh_token"
            revoked_family = await expected_error(
                client,
                "POST",
                "/api/v1/auth/refresh",
                401,
                json={"refresh_token": rotated_pair["refresh_token"]},
            )
            assert revoked_family["code"] == "invalid_refresh_token"

            logout_pair_response = await client.post(
                "/api/v1/auth/token", data={"username": email, "password": password}
            )
            logout_pair = logout_pair_response.json()
            logout_response = await client.post(
                "/api/v1/auth/logout",
                json={"refresh_token": logout_pair["refresh_token"]},
            )
            assert logout_response.status_code == 204, logout_response.text
            logged_out = await expected_error(
                client,
                "POST",
                "/api/v1/auth/refresh",
                401,
                json={"refresh_token": logout_pair["refresh_token"]},
            )
            assert logged_out["code"] == "invalid_refresh_token"

            logout_all_pair_response = await client.post(
                "/api/v1/auth/token", data={"username": email, "password": password}
            )
            logout_all_pair = logout_all_pair_response.json()
            logout_all_response = await client.post(
                "/api/v1/auth/logout-all",
                headers={"Authorization": f"Bearer {logout_all_pair['access_token']}"},
            )
            assert logout_all_response.status_code == 204, logout_all_response.text
            globally_logged_out = await expected_error(
                client,
                "POST",
                "/api/v1/auth/refresh",
                401,
                json={"refresh_token": logout_all_pair["refresh_token"]},
            )
            assert globally_logged_out["code"] == "invalid_refresh_token"

            final_pair_response = await client.post(
                "/api/v1/auth/token", data={"username": email, "password": password}
            )
            final_pair = final_pair_response.json()
            user_headers = {"Authorization": f"Bearer {final_pair['access_token']}"}

            permitted_response = await client.get("/api/v1/users", headers=user_headers)
            assert permitted_response.status_code == 200, permitted_response.text
            audit_denied = await expected_error(
                client, "GET", "/api/v1/audit-records", 403, headers=user_headers
            )
            assert audit_denied["code"] == "permission_denied"
            modules_denied = await expected_error(
                client, "GET", "/api/v1/modules", 403, headers=user_headers
            )
            assert modules_denied["code"] == "permission_denied"
            module_health_denied = await expected_error(
                client, "GET", "/api/v1/modules/health-summary", 403, headers=user_headers
            )
            assert module_health_denied["code"] == "permission_denied"
            jobs_denied = await expected_error(
                client, "GET", "/api/v1/test-jobs", 403, headers=user_headers
            )
            assert jobs_denied["code"] == "permission_denied"
            artifacts_denied = await expected_error(
                client,
                "GET",
                f"/api/v1/test-runs/{test_run_id}/artifacts",
                403,
                headers=user_headers,
            )
            assert artifacts_denied["code"] == "permission_denied"

            refresh_rows = await database.fetch(
                "SELECT token_hash FROM refresh_tokens WHERE user_id = $1::uuid", user_id
            )
            assert len(refresh_rows) >= 5
            assert all(len(row["token_hash"]) == 64 for row in refresh_rows)
            assert all(first_refresh_token != row["token_hash"] for row in refresh_rows)

            removal_response = await client.delete(
                f"/api/v1/users/{user_id}/roles/{role_id}", headers=admin_headers
            )
            assert removal_response.status_code == 200, removal_response.text
            denied = await expected_error(client, "GET", "/api/v1/users", 403, headers=user_headers)
            assert denied["code"] == "permission_denied"

            reassignment_response = await client.put(
                f"/api/v1/users/{user_id}/roles/{role_id}", headers=admin_headers
            )
            assert reassignment_response.status_code == 200, reassignment_response.text
            disable_response = await client.patch(
                f"/api/v1/users/{user_id}/status",
                headers=admin_headers,
                json={"is_active": False},
            )
            assert disable_response.status_code == 200, disable_response.text
            assert disable_response.json()["is_active"] is False
            inactive = await expected_error(
                client, "GET", "/api/v1/auth/me", 401, headers=user_headers
            )
            assert inactive["code"] == "invalid_credentials"

            final_removal = await client.delete(
                f"/api/v1/users/{user_id}/roles/{role_id}", headers=admin_headers
            )
            assert final_removal.status_code == 200, final_removal.text
            role_delete_response = await client.delete(
                f"/api/v1/roles/{role_id}", headers=admin_headers
            )
            assert role_delete_response.status_code == 204, role_delete_response.text

            audit_response = await client.get(
                "/api/v1/audit-records",
                headers=admin_headers,
                params={"resource_id": role_id, "limit": 100},
            )
            assert audit_response.status_code == 200, audit_response.text
            audit_page = audit_response.json()
            assert audit_page["total"] == 5
            assert [item["action"] for item in audit_page["items"]] == [
                "identity.role.deleted",
                "identity.role.permission_revoked",
                "identity.role.permission_granted",
                "identity.role.updated",
                "identity.role.created",
            ]
            detail = await client.get(
                f"/api/v1/audit-records/{audit_page['items'][0]['id']}",
                headers=admin_headers,
            )
            assert detail.status_code == 200, detail.text
            assert detail.json()["resource_id"] == role_id

            export_response = await client.get(
                "/api/v1/audit-records/export",
                headers=admin_headers,
                params={"resource_id": role_id, "limit": 100},
            )
            assert export_response.status_code == 200, export_response.text
            assert export_response.headers["content-type"].startswith("text/csv")
            assert "identity.role.created" in export_response.text
            assert "identity.role.deleted" in export_response.text

            invalid_audit_page = await expected_error(
                client,
                "GET",
                "/api/v1/audit-records?limit=101",
                422,
                headers=admin_headers,
            )
            assert invalid_audit_page["code"] == "validation_error"

            limited_email = f"limited-{uuid4().hex}@example.com"
            for _ in range(5):
                invalid_login = await client.post(
                    "/api/v1/auth/token",
                    data={"username": limited_email, "password": "invalid-password"},
                )
                assert invalid_login.status_code == 401, invalid_login.text
            rate_limited = await client.post(
                "/api/v1/auth/token",
                data={"username": limited_email, "password": "invalid-password"},
            )
            assert rate_limited.status_code == 429, rate_limited.text
            assert rate_limited.json()["error"]["code"] == "rate_limit_exceeded"
            assert rate_limited.headers["retry-after"]
            assert rate_limited.headers["x-ratelimit-limit"] == "5"
            assert rate_limited.headers["x-ratelimit-remaining"] == "0"

            domain_metrics = await client.get("/metrics")
            assert domain_metrics.status_code == 200, domain_metrics.text
            assert "atep_test_jobs_dispatched_total" in domain_metrics.text
            assert "atep_test_run_websocket_connections" in domain_metrics.text
            assert 'kind="snapshot"' in domain_metrics.text
            assert 'kind="update"' in domain_metrics.text
            assert 'atep_dependency_ready{dependency="postgres"} 1.0' in domain_metrics.text
            assert 'atep_dependency_ready{dependency="redis"} 1.0' in domain_metrics.text
            assert 'atep_dependency_ready{dependency="rabbitmq"} 1.0' in domain_metrics.text
            assert 'atep_artifact_store_operations_total{operation="put",outcome="success"}' in (
                domain_metrics.text
            )
            assert "atep_artifact_store_capacity_bytes" in domain_metrics.text

        message = await wait_for_message(queue)
        async with message.process():
            envelope = json.loads(message.body)
        assert envelope["event_type"] == "atep.identity.user.created.v1"
        assert envelope["aggregate"] == {"type": "user", "id": user_id}
        assert envelope["payload"]["email"] == email
        assert "password" not in json.dumps(envelope).casefold()

        outbox = await wait_for_published_event(database, user_id)
        assert outbox["event_type"] == "atep.identity.user.created.v1"
        assert "password" not in json.dumps(outbox["payload"]).casefold()

        async with httpx.AsyncClient(base_url=outbox_metrics_url, timeout=10) as metrics_client:
            worker_metrics = await metrics_client.get("/metrics")
        assert worker_metrics.status_code == 200, worker_metrics.text
        assert "atep_outbox_worker_up 1.0" in worker_metrics.text
        assert 'atep_outbox_publication_attempts_total{outcome="success"}' in worker_metrics.text
        assert "atep_outbox_unpublished_events" in worker_metrics.text

        audit_actions = await database.fetch(
            """
            SELECT action
            FROM audit_records
            WHERE resource_id = $1::uuid AND action LIKE 'identity.user.%'
            ORDER BY created_at, id
            """,
            user_id,
        )
        assert [row["action"] for row in audit_actions] == [
            "identity.user.created",
            "identity.user.role_assigned",
            "identity.user.role_removed",
            "identity.user.role_assigned",
            "identity.user.status_changed",
            "identity.user.role_removed",
        ]
        role_audit_actions = await database.fetch(
            """
            SELECT action
            FROM audit_records
            WHERE resource_id = $1::uuid AND action LIKE 'identity.role.%'
            ORDER BY created_at, id
            """,
            role_id,
        )
        assert [row["action"] for row in role_audit_actions] == [
            "identity.role.created",
            "identity.role.updated",
            "identity.role.permission_granted",
            "identity.role.permission_revoked",
            "identity.role.deleted",
        ]
        module_audit_actions = await database.fetch(
            """
            SELECT action
            FROM audit_records
            WHERE resource_id = $1::uuid AND action LIKE 'platform.module.%'
            ORDER BY created_at, id
            """,
            module_id,
        )
        assert [row["action"] for row in module_audit_actions] == [
            "platform.module.registered",
            "platform.module.updated",
            "platform.module.credential_rotated",
            "platform.module.capability_declared",
            "platform.module.capability_removed",
            "platform.module.lease_expired",
        ]
        assert (
            await database.fetchval(
                "SELECT count(*) FROM outbox_events WHERE aggregate_id = $1::uuid",
                module_id,
            )
            == 7
        )
        assert (
            await database.fetchval(
                "SELECT count(*) FROM vehicle_telemetry_events WHERE vehicle_id = $1::uuid",
                vehicle_uuid,
            )
            == 1
        )
        vehicle_event_types = await database.fetch(
            """
            SELECT event_type
            FROM outbox_events
            WHERE aggregate_id = $1::uuid
            ORDER BY created_at, id
            """,
            vehicle_uuid,
        )
        assert [row["event_type"] for row in vehicle_event_types] == [
            "atep.vehicle.registered.v1",
            "atep.vehicle.status-changed.v1",
            "atep.digital_vehicle.state.updated.v1",
            "atep.digital_vehicle.simulation.transitioned.v1",
            "atep.vehicle.telemetry.received.v1",
        ]
        simulation_audit_actions = await database.fetch(
            """
            SELECT action
            FROM audit_records
            WHERE resource_id = $1::uuid AND action LIKE 'digital_vehicle.%'
            ORDER BY created_at, id
            """,
            vehicle_uuid,
        )
        assert [row["action"] for row in simulation_audit_actions] == [
            "digital_vehicle.state_updated",
            "digital_vehicle.simulation_transitioned",
        ]
        vehicle_audit_actions = await database.fetch(
            """
            SELECT action
            FROM audit_records
            WHERE resource_id = $1::uuid AND action LIKE 'vehicle.%'
            ORDER BY created_at, id
            """,
            vehicle_uuid,
        )
        assert [row["action"] for row in vehicle_audit_actions] == [
            "vehicle.registered",
            "vehicle.status_changed",
        ]
        dispatched_job_uuid = dispatched_body["id"]
        assert (
            await database.fetchval("SELECT count(*) FROM test_runs WHERE run_id = $1", due_run_id)
            == 1
        )
        assert (
            await database.fetchval(
                "SELECT count(*) FROM outbox_events WHERE aggregate_id = $1::uuid",
                dispatched_job_uuid,
            )
            == 2
        )
        assert (
            await database.fetchval(
                "SELECT count(*) FROM audit_records WHERE resource_id = $1::uuid",
                dispatched_job_uuid,
            )
            == 2
        )
        assert (
            await database.fetchval(
                "SELECT count(*) FROM test_artifacts WHERE id = $1::uuid", artifact_uuid
            )
            == 1
        )
        assert (
            await database.fetchval(
                "SELECT count(*) FROM outbox_events WHERE aggregate_id = $1::uuid", artifact_uuid
            )
            == 1
        )
        assert (
            await database.fetchval(
                "SELECT count(*) FROM audit_records WHERE resource_id = $1::uuid", artifact_uuid
            )
            == 1
        )
        audit_id = await database.fetchval(
            "SELECT id FROM audit_records WHERE resource_id = $1::uuid LIMIT 1", user_id
        )
        with pytest.raises(asyncpg.RaiseError, match="immutable"):
            await database.execute(
                "UPDATE audit_records SET action = 'tampered' WHERE id = $1", audit_id
            )
    finally:
        await broker.close()
        await database.close()
