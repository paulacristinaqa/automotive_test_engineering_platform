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

            definition_id = f"battery-case-{uuid4().hex[:12]}"
            suite_id = f"battery-suite-{uuid4().hex[:12]}"
            catalog_run_id = uuid4().hex
            definition = await client.post(
                "/api/v1/test-definitions",
                headers=admin_headers,
                json={
                    "definition_id": definition_id,
                    "name": "Battery warning is displayed",
                    "domain": "electric_vehicle",
                    "level": "end_to_end",
                    "steps": [
                        {
                            "step_id": "inject-temperature",
                            "action": "set_property",
                            "target": "battery_temperature",
                            "inputs": {"value": 48},
                            "expected": "CarSystemUI displays a battery warning",
                        }
                    ],
                },
            )
            assert definition.status_code == 201, definition.text
            activated_definition = await client.patch(
                f"/api/v1/test-definitions/{definition_id}/status",
                headers=admin_headers,
                json={"expected_version": 1, "status": "active"},
            )
            assert activated_definition.status_code == 200, activated_definition.text
            suite = await client.post(
                "/api/v1/test-suites",
                headers=admin_headers,
                json={
                    "suite_id": suite_id,
                    "name": "Battery integration smoke suite",
                    "suite_type": "smoke",
                    "cases": [
                        {
                            "definition_id": definition_id,
                            "order": 1,
                            "required": True,
                            "parameter_overrides": {},
                        }
                    ],
                },
            )
            assert suite.status_code == 201, suite.text
            activated_suite = await client.patch(
                f"/api/v1/test-suites/{suite_id}/status",
                headers=admin_headers,
                json={"expected_version": 1, "status": "active"},
            )
            assert activated_suite.status_code == 200, activated_suite.text
            catalog_run_payload = {
                "run_id": catalog_run_id,
                "vehicle_id": vehicle_identifier,
                "catalog_suite_id": suite_id,
                "name": "Catalog-backed battery smoke test",
                "suite": "smoke",
                "metadata": {"requirement": "TF-F-012"},
            }
            catalog_run = await client.post(
                "/api/v1/test-runs", headers=admin_headers, json=catalog_run_payload
            )
            assert catalog_run.status_code == 201, catalog_run.text
            assert catalog_run.json()["catalog_suite_id"] == suite_id
            assert catalog_run.json()["catalog_suite_version"] == 2
            catalog_cases = await client.get(
                f"/api/v1/test-runs/{catalog_run_id}/cases", headers=admin_headers
            )
            assert catalog_cases.status_code == 200, catalog_cases.text
            assert catalog_cases.json()["total"] == 1
            assert catalog_cases.json()["items"][0]["status"] == "pending"
            running_case = await client.patch(
                f"/api/v1/test-runs/{catalog_run_id}/cases/{definition_id}",
                headers=admin_headers,
                json={"expected_version": 1, "status": "running", "attempt": 1},
            )
            assert running_case.status_code == 200, running_case.text
            passed_case = await client.patch(
                f"/api/v1/test-runs/{catalog_run_id}/cases/{definition_id}",
                headers=admin_headers,
                json={
                    "expected_version": 2,
                    "status": "passed",
                    "attempt": 1,
                    "duration_ms": 125,
                    "observed": "Battery warning displayed",
                    "evidence_refs": ["telemetry://battery-warning-observation"],
                },
            )
            assert passed_case.status_code == 200, passed_case.text
            completed_catalog_run = await client.get(
                f"/api/v1/test-runs/{catalog_run_id}", headers=admin_headers
            )
            assert completed_catalog_run.status_code == 200, completed_catalog_run.text
            assert completed_catalog_run.json()["status"] == "passed"
            assert completed_catalog_run.json()["progress_percent"] == 100

            fault_campaign_id = f"battery-fault-{uuid4().hex[:12]}"
            fault_execution_id = f"fault-run-{uuid4().hex[:12]}"
            campaign_payload = {
                "campaign_id": fault_campaign_id,
                "name": "Battery thermal recovery campaign",
                "description": "Bounded EV fault with explicit recovery evidence.",
                "blast_radius": "single_component",
                "tags": ["battery", "regression"],
                "steps": [
                    {
                        "step_id": "inject-temperature",
                        "order": 1,
                        "domain": "electric_vehicle",
                        "action": "battery_overtemperature",
                        "target_id": "battery-pack-main",
                        "parameters": {"temperature_celsius": 48.0},
                        "duration_ms": 5_000,
                        "expected_effect": "BMS warning is observable",
                        "recovery": {
                            "action": "restore nominal thermal state",
                            "timeout_ms": 10_000,
                            "verification": "Temperature returns below the warning threshold",
                        },
                    }
                ],
            }
            fault_campaign = await client.post(
                "/api/v1/fault-campaigns", headers=admin_headers, json=campaign_payload
            )
            assert fault_campaign.status_code == 201, fault_campaign.text
            activated_campaign = await client.patch(
                f"/api/v1/fault-campaigns/{fault_campaign_id}/status",
                headers=admin_headers,
                json={"expected_version": 1, "status": "active"},
            )
            assert activated_campaign.status_code == 200, activated_campaign.text
            fault_execution_payload = {
                "execution_id": fault_execution_id,
                "vehicle_id": vehicle_identifier,
                "test_run_id": catalog_run_id,
                "seed": 42,
                "dry_run": False,
                "metadata": {"requirement": "TF-F-035"},
            }
            fault_execution = await client.post(
                f"/api/v1/fault-campaigns/{fault_campaign_id}/executions",
                headers=admin_headers,
                json=fault_execution_payload,
            )
            assert fault_execution.status_code == 201, fault_execution.text
            assert fault_execution.json()["campaign_version"] == 2
            assert fault_execution.json()["test_run_id"] == catalog_run_id
            for version, step_status in enumerate(
                ("injecting", "injected", "recovering", "recovered"), start=1
            ):
                step_update = await client.patch(
                    f"/api/v1/fault-executions/{fault_execution_id}/steps/inject-temperature",
                    headers=admin_headers,
                    json={
                        "expected_version": version,
                        "status": step_status,
                        "attempt": 1,
                        "duration_ms": 125 if step_status == "recovered" else None,
                        "observed_effect": step_status,
                        "evidence_refs": (
                            ["telemetry://battery-temperature"]
                            if step_status == "recovered"
                            else []
                        ),
                    },
                )
                assert step_update.status_code == 200, step_update.text
            completed_fault_execution = await client.get(
                f"/api/v1/fault-executions/{fault_execution_id}", headers=admin_headers
            )
            assert completed_fault_execution.status_code == 200, completed_fault_execution.text
            assert completed_fault_execution.json()["status"] == "passed"
            assert completed_fault_execution.json()["progress_percent"] == 100
            archived_campaign = await client.patch(
                f"/api/v1/fault-campaigns/{fault_campaign_id}/status",
                headers=admin_headers,
                json={"expected_version": 2, "status": "archived"},
            )
            assert archived_campaign.status_code == 200, archived_campaign.text
            replayed_fault_execution = await client.post(
                f"/api/v1/fault-campaigns/{fault_campaign_id}/executions",
                headers=admin_headers,
                json=fault_execution_payload,
            )
            assert replayed_fault_execution.status_code == 200, replayed_fault_execution.text
            archived_rejection = await expected_error(
                client,
                "POST",
                f"/api/v1/fault-campaigns/{fault_campaign_id}/executions",
                409,
                headers=admin_headers,
                json={**fault_execution_payload, "execution_id": f"fault-run-{uuid4().hex[:12]}"},
            )
            assert archived_rejection["code"] == "fault_campaign_state_conflict"

            mutation_campaign_id = f"battery-mutation-{uuid4().hex[:12]}"
            mutation_execution_id = f"mutation-run-{uuid4().hex[:12]}"
            mutation_campaign = await client.post(
                "/api/v1/mutation-campaigns",
                headers=admin_headers,
                json={
                    "campaign_id": mutation_campaign_id,
                    "catalog_suite_id": suite_id,
                    "name": "Battery safety mutation baseline",
                    "description": "Bounded mutation evidence for the active battery suite.",
                    "tags": ["battery", "safety"],
                    "mutants": [
                        {
                            "mutant_id": "shift-temperature-boundary",
                            "order": 1,
                            "operator": "boundary_shift",
                            "target": "battery.temperature_warning_threshold",
                            "parameters": {"delta_celsius": 1},
                            "expected_detection": "The battery warning test fails",
                            "required": True,
                        },
                        {
                            "mutant_id": "invert-warning-guard",
                            "order": 2,
                            "operator": "conditional_negation",
                            "target": "battery.warning_guard",
                            "parameters": {},
                            "expected_detection": "The warning invariant fails",
                            "required": False,
                        },
                    ],
                },
            )
            assert mutation_campaign.status_code == 201, mutation_campaign.text
            activated_mutation_campaign = await client.patch(
                f"/api/v1/mutation-campaigns/{mutation_campaign_id}/status",
                headers=admin_headers,
                json={"expected_version": 1, "status": "active"},
            )
            assert activated_mutation_campaign.status_code == 200, activated_mutation_campaign.text
            mutation_execution_payload = {
                "execution_id": mutation_execution_id,
                "vehicle_id": vehicle_identifier,
                "test_run_id": catalog_run_id,
            }
            mutation_execution = await client.post(
                f"/api/v1/mutation-campaigns/{mutation_campaign_id}/executions",
                headers=admin_headers,
                json=mutation_execution_payload,
            )
            assert mutation_execution.status_code == 201, mutation_execution.text
            assert mutation_execution.json()["total_mutants"] == 2
            mutation_results = await client.get(
                f"/api/v1/mutation-executions/{mutation_execution_id}/mutants",
                headers=admin_headers,
            )
            assert mutation_results.status_code == 200, mutation_results.text
            assert mutation_results.json()["total"] == 2
            for mutant_id, terminal_status, detected_by in (
                ("shift-temperature-boundary", "killed", [definition_id]),
                ("invert-warning-guard", "survived", []),
            ):
                running_mutant = await client.patch(
                    f"/api/v1/mutation-executions/{mutation_execution_id}/mutants/{mutant_id}",
                    headers=admin_headers,
                    json={"expected_version": 1, "status": "running"},
                )
                assert running_mutant.status_code == 200, running_mutant.text
                completed_mutant = await client.patch(
                    f"/api/v1/mutation-executions/{mutation_execution_id}/mutants/{mutant_id}",
                    headers=admin_headers,
                    json={
                        "expected_version": 2,
                        "status": terminal_status,
                        "duration_ms": 125,
                        "detected_by": detected_by,
                        "evidence_refs": ["artifact://mutation-report"],
                    },
                )
                assert completed_mutant.status_code == 200, completed_mutant.text
            completed_mutation_execution = await client.get(
                f"/api/v1/mutation-executions/{mutation_execution_id}",
                headers=admin_headers,
            )
            assert completed_mutation_execution.status_code == 200
            assert completed_mutation_execution.json()["status"] == "passed"
            assert completed_mutation_execution.json()["mutation_score"] == 0.5

            covered_requirement = await client.put(
                "/api/v1/requirement-coverage/EV-F-001",
                headers=admin_headers,
                json={
                    "title": "Battery warning remains observable",
                    "criticality": "asil_b",
                    "definition_ids": [definition_id],
                    "evidence_refs": ["artifact://mutation-report"],
                },
            )
            assert covered_requirement.status_code == 201, covered_requirement.text
            assert covered_requirement.json()["status"] == "covered"
            gap_requirement = await client.put(
                "/api/v1/requirement-coverage/EV-F-002",
                headers=admin_headers,
                json={
                    "title": "Battery isolation response is verified",
                    "criticality": "asil_c",
                    "definition_ids": [],
                    "evidence_refs": [],
                },
            )
            assert gap_requirement.status_code == 201, gap_requirement.text
            assert gap_requirement.json()["status"] == "gap"
            coverage_page = await client.get("/api/v1/requirement-coverage", headers=admin_headers)
            assert coverage_page.status_code == 200, coverage_page.text
            assert coverage_page.json()["covered"] == 1
            assert coverage_page.json()["gaps"] == 1

            archived_mutation_campaign = await client.patch(
                f"/api/v1/mutation-campaigns/{mutation_campaign_id}/status",
                headers=admin_headers,
                json={"expected_version": 2, "status": "archived"},
            )
            assert archived_mutation_campaign.status_code == 200
            replayed_mutation_execution = await client.post(
                f"/api/v1/mutation-campaigns/{mutation_campaign_id}/executions",
                headers=admin_headers,
                json=mutation_execution_payload,
            )
            assert replayed_mutation_execution.status_code == 200
            archived_mutation_rejection = await expected_error(
                client,
                "POST",
                f"/api/v1/mutation-campaigns/{mutation_campaign_id}/executions",
                409,
                headers=admin_headers,
                json={
                    **mutation_execution_payload,
                    "execution_id": f"mutation-run-{uuid4().hex[:12]}",
                },
            )
            assert archived_mutation_rejection["code"] == "mutation_campaign_state_conflict"

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
                    "catalog_suite_id": suite_id,
                    "selection_policy": "smoke",
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
            assert generated_run.json()["catalog_suite_id"] == suite_id
            scheduled_cases = await client.get(
                f"/api/v1/test-runs/{due_run_id}/cases", headers=admin_headers
            )
            assert scheduled_cases.status_code == 200, scheduled_cases.text
            assert scheduled_cases.json()["total"] == 1
            assert scheduled_cases.json()["items"][0]["definition_id"] == definition_id

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
                "test_run_id": catalog_run_id,
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

            automation_report_id = f"automation-report-{uuid4().hex[:12]}"
            automation_report_payload = {
                "report_id": automation_report_id,
                "vehicle_id": vehicle_identifier,
                "test_run_id": catalog_run_id,
                "gateway_module_id": gateway_id,
                "fault_execution_id": fault_execution_id,
                "mutation_execution_id": mutation_execution_id,
                "telemetry_event_ids": [telemetry_event_id],
                "vehicle_command_ids": [command_id],
                "carsystemui_observations": [
                    {
                        "observation_id": f"ui-observation-{uuid4().hex[:12]}",
                        "surface": "test_detail",
                        "connection_state": "connected",
                        "displayed_run_status": "passed",
                        "displayed_run_version": completed_catalog_run.json()["version"],
                        "client_version": "1.0.0-integration",
                        "captured_at": "2026-09-09T13:00:00Z",
                        "evidence_ref": "artifact://carsystemui-test-detail",
                    }
                ],
            }
            automation_report = await client.post(
                "/api/v1/cross-platform-automation/reports",
                headers=admin_headers,
                json=automation_report_payload,
            )
            assert automation_report.status_code == 201, automation_report.text
            assert automation_report.json()["outcome"] == "passed"
            assert automation_report.json()["summary"]["mutation_score"] == 0.5
            assert automation_report.json()["summary"]["telemetry_event_count"] == 1
            replayed_automation_report = await client.post(
                "/api/v1/cross-platform-automation/reports",
                headers=admin_headers,
                json=automation_report_payload,
            )
            assert replayed_automation_report.status_code == 200
            assert replayed_automation_report.json()["duplicate"] is True
            automation_report_page = await client.get(
                "/api/v1/cross-platform-automation/reports", headers=admin_headers
            )
            assert automation_report_page.status_code == 200
            assert automation_report_page.json()["total"] == 1

            performance_profile_id = f"performance-profile-{uuid4().hex[:12]}"
            performance_profile = await client.post(
                "/api/v1/performance/profiles",
                headers=admin_headers,
                json={
                    "profile_id": performance_profile_id,
                    "name": "Integration API baseline",
                    "workload_type": "performance",
                    "target": "public-api",
                    "stages": [
                        {
                            "duration_seconds": 60,
                            "virtual_users": 10,
                            "requests_per_second": 20,
                        }
                    ],
                    "thresholds": [{"metric": "p95_latency_ms", "operator": "max", "value": 250}],
                    "resource_limits": {
                        "cpu_cores": 2,
                        "memory_mb": 1024,
                        "gpu_allowed": False,
                    },
                },
            )
            assert performance_profile.status_code == 201, performance_profile.text
            performance_execution = await client.post(
                f"/api/v1/performance/profiles/{performance_profile_id}/executions",
                headers=admin_headers,
                json={
                    "execution_id": f"performance-execution-{uuid4().hex[:12]}",
                    "test_run_id": catalog_run_id,
                    "sample_count": 1200,
                    "duration_seconds": 60,
                    "metrics": {"p95_latency_ms": 210},
                    "evidence_refs": ["artifact://integration-performance-summary"],
                },
            )
            assert performance_execution.status_code == 201, performance_execution.text
            assert performance_execution.json()["outcome"] == "passed"

            ai_request_payload = {
                "request_id": f"ai-analysis-{uuid4().hex[:12]}",
                "task": "root_cause",
                "subject_type": "automation_report",
                "subject_id": automation_report_id,
                "evidence_refs": ["artifact://carsystemui-test-detail"],
                "context": {"dtc_codes": ["P0A80"]},
                "instructions": "Rank evidence-backed hypotheses.",
            }
            ai_request = await client.post(
                "/api/v1/ai/analysis-requests", headers=admin_headers, json=ai_request_payload
            )
            assert ai_request.status_code == 201, ai_request.text
            assert ai_request.json()["provider_policy"] == "local_only"
            ai_request_id = ai_request.json()["request_id"]
            replayed_ai_request = await client.post(
                "/api/v1/ai/analysis-requests", headers=admin_headers, json=ai_request_payload
            )
            assert replayed_ai_request.status_code == 200
            assert replayed_ai_request.json()["duplicate"] is True
            ai_request_page = await client.get(
                "/api/v1/ai/analysis-requests", headers=admin_headers
            )
            assert ai_request_page.status_code == 200
            assert ai_request_page.json()["total"] == 1
            ai_execution_payload = {
                "execution_id": f"ai-execution-{uuid4().hex[:12]}",
                "provider_id": "local-rules",
            }
            ai_execution = await client.post(
                f"/api/v1/ai/analysis-requests/{ai_request_id}/executions",
                headers=admin_headers,
                json=ai_execution_payload,
            )
            assert ai_execution.status_code == 201, ai_execution.text
            assert ai_execution.json()["status"] == "succeeded"
            assert ai_execution.json()["result"]["findings"][0]["code"] == "DTC_PRESENT"
            replayed_ai_execution = await client.post(
                f"/api/v1/ai/analysis-requests/{ai_request_id}/executions",
                headers=admin_headers,
                json=ai_execution_payload,
            )
            assert replayed_ai_execution.status_code == 200
            assert replayed_ai_execution.json()["duplicate"] is True
            ai_execution_page = await client.get(
                f"/api/v1/ai/analysis-requests/{ai_request_id}/executions",
                headers=admin_headers,
            )
            assert ai_execution_page.status_code == 200
            assert ai_execution_page.json()["total"] == 1
            log_analysis_id = f"log-analysis-{uuid4().hex[:12]}"
            log_analysis_payload = {
                "analysis_id": log_analysis_id,
                "source": "bms-ecu",
                "lines": [
                    "2026-09-10T10:00:00Z INFO [bms] Monitor started",
                    "2026-09-10T10:00:01Z ERROR [bms] Cell voltage 2.1",
                    "2026-09-10T10:00:02Z ERROR [bms] Cell voltage 2.2",
                    "2026-09-10T10:00:03Z ERROR [bms] Cell voltage 2.3",
                    "unsupported line",
                ],
            }
            log_analysis = await client.post(
                f"/api/v1/ai/analysis-requests/{ai_request_id}/log-intelligence",
                headers=admin_headers,
                json=log_analysis_payload,
            )
            assert log_analysis.status_code == 201, log_analysis.text
            assert log_analysis.json()["parsed_count"] == 4
            assert log_analysis.json()["rejected_count"] == 1
            assert len(log_analysis.json()["anomalies"]) == 2
            replayed_log_analysis = await client.post(
                f"/api/v1/ai/analysis-requests/{ai_request_id}/log-intelligence",
                headers=admin_headers,
                json=log_analysis_payload,
            )
            assert replayed_log_analysis.status_code == 200
            assert replayed_log_analysis.json()["duplicate"] is True
            log_analysis_page = await client.get(
                "/api/v1/ai/log-analyses?source=bms-ecu", headers=admin_headers
            )
            assert log_analysis_page.status_code == 200
            assert log_analysis_page.json()["total"] == 1
            log_analysis_detail = await client.get(
                f"/api/v1/ai/log-analyses/{log_analysis_id}", headers=admin_headers
            )
            assert log_analysis_detail.status_code == 200

            root_risk_id = f"root-risk-{uuid4().hex[:12]}"
            root_risk_payload = {
                "analysis_id": root_risk_id,
                "horizon_hours": 24,
                "signals": [
                    {
                        "code": "BMS_DTC_PRESENT",
                        "component": "bms",
                        "symptom": "Battery degradation DTC with repeated thermal anomalies",
                        "severity": "critical",
                        "occurrence_count": 5,
                        "confidence": 0.8,
                        "detectability": 0.3,
                        "evidence_refs": ["artifact://carsystemui-test-detail"],
                    }
                ],
            }
            root_risk = await client.post(
                f"/api/v1/ai/analysis-requests/{ai_request_id}/root-cause-risk",
                headers=admin_headers,
                json=root_risk_payload,
            )
            assert root_risk.status_code == 201, root_risk.text
            assert root_risk.json()["risk_band"] == "critical"
            assert root_risk.json()["hypotheses"][0]["code"] == "BMS_DTC_PRESENT"
            replayed_root_risk = await client.post(
                f"/api/v1/ai/analysis-requests/{ai_request_id}/root-cause-risk",
                headers=admin_headers,
                json=root_risk_payload,
            )
            assert replayed_root_risk.status_code == 200
            assert replayed_root_risk.json()["duplicate"] is True
            root_risk_evaluation = await client.post(
                f"/api/v1/ai/root-cause-risk/{root_risk_id}/evaluation",
                headers=admin_headers,
                json={
                    "evaluation_id": f"prediction-evaluation-{uuid4().hex[:12]}",
                    "expected_version": 1,
                    "actual_failure": True,
                    "confirmed_hypothesis_code": "BMS_DTC_PRESENT",
                    "evidence_refs": ["artifact://carsystemui-test-detail"],
                },
            )
            assert root_risk_evaluation.status_code == 200, root_risk_evaluation.text
            assert root_risk_evaluation.json()["prediction_correct"] is True
            assert 0 <= root_risk_evaluation.json()["brier_score"] <= 1
            root_risk_page = await client.get(
                "/api/v1/ai/root-cause-risk?risk_band=critical", headers=admin_headers
            )
            assert root_risk_page.status_code == 200
            assert root_risk_page.json()["total"] == 1
            prediction_metrics = await client.get(
                "/api/v1/ai/root-cause-risk/prediction-metrics", headers=admin_headers
            )
            assert prediction_metrics.status_code == 200
            assert prediction_metrics.json()["evaluated_count"] == 1
            assert prediction_metrics.json()["accuracy"] == 1.0

            suggestion_request_id = f"ai-suggestion-request-{uuid4().hex[:12]}"
            suggestion_request = await client.post(
                "/api/v1/ai/analysis-requests",
                headers=admin_headers,
                json={
                    "request_id": suggestion_request_id,
                    "task": "test_suggestion",
                    "subject_type": "test_run",
                    "subject_id": catalog_run_id,
                    "evidence_refs": [f"log-analysis://{log_analysis_id}"],
                    "instructions": "Create an inactive reviewable draft only.",
                },
            )
            assert suggestion_request.status_code == 201, suggestion_request.text
            suggestion_id = f"test-suggestion-{uuid4().hex[:12]}"
            suggestion_payload = {
                "suggestion_id": suggestion_id,
                "requirement_refs": ["EV-F-THERMAL-001"],
                "evidence_refs": ["artifact://carsystemui-test-detail"],
                "name": "BMS thermal warning regression",
                "objective": "Raise battery temperature and verify warning evidence.",
                "domain": "electric_vehicle",
                "level": "system",
                "automation_mode": "hybrid",
                "timeout_seconds": 600,
            }
            suggestion = await client.post(
                f"/api/v1/ai/analysis-requests/{suggestion_request_id}/test-suggestions",
                headers=admin_headers,
                json=suggestion_payload,
            )
            assert suggestion.status_code == 201, suggestion.text
            assert suggestion.json()["status"] == "draft"
            replayed_suggestion = await client.post(
                f"/api/v1/ai/analysis-requests/{suggestion_request_id}/test-suggestions",
                headers=admin_headers,
                json=suggestion_payload,
            )
            assert replayed_suggestion.status_code == 200
            assert replayed_suggestion.json()["duplicate"] is True
            review = await client.post(
                f"/api/v1/ai/test-suggestions/{suggestion_id}/review",
                headers=admin_headers,
                json={
                    "expected_version": 1,
                    "decision": "approve",
                    "comment": "Requirement and evidence reviewed for catalog drafting.",
                },
            )
            assert review.status_code == 200, review.text
            assert review.json()["status"] == "approved"
            promoted_definition_id = f"ai-bms-thermal-{uuid4().hex[:12]}"
            promotion = await client.post(
                f"/api/v1/ai/test-suggestions/{suggestion_id}/promotion",
                headers=admin_headers,
                json={"expected_version": 2, "definition_id": promoted_definition_id},
            )
            assert promotion.status_code == 200, promotion.text
            assert promotion.json()["status"] == "promoted"
            promoted_definition = await client.get(
                f"/api/v1/test-definitions/{promoted_definition_id}",
                headers=admin_headers,
            )
            assert promoted_definition.status_code == 200, promoted_definition.text
            assert promoted_definition.json()["status"] == "draft"
            suggestion_page = await client.get(
                "/api/v1/ai/test-suggestions?status=promoted", headers=admin_headers
            )
            assert suggestion_page.status_code == 200
            assert suggestion_page.json()["total"] == 1

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
            fault_campaigns_denied = await expected_error(
                client, "GET", "/api/v1/fault-campaigns", 403, headers=user_headers
            )
            assert fault_campaigns_denied["code"] == "permission_denied"
            mutation_campaigns_denied = await expected_error(
                client, "GET", "/api/v1/mutation-campaigns", 403, headers=user_headers
            )
            assert mutation_campaigns_denied["code"] == "permission_denied"
            automation_reports_denied = await expected_error(
                client,
                "GET",
                "/api/v1/cross-platform-automation/reports",
                403,
                headers=user_headers,
            )
            assert automation_reports_denied["code"] == "permission_denied"
            performance_denied = await expected_error(
                client,
                "GET",
                "/api/v1/performance/profiles",
                403,
                headers=user_headers,
            )
            assert performance_denied["code"] == "permission_denied"
            ai_requests_denied = await expected_error(
                client,
                "GET",
                "/api/v1/ai/analysis-requests",
                403,
                headers=user_headers,
            )
            assert ai_requests_denied["code"] == "permission_denied"
            ai_executions_denied = await expected_error(
                client,
                "GET",
                f"/api/v1/ai/analysis-requests/{ai_request_id}/executions",
                403,
                headers=user_headers,
            )
            assert ai_executions_denied["code"] == "permission_denied"
            log_analyses_denied = await expected_error(
                client,
                "GET",
                "/api/v1/ai/log-analyses",
                403,
                headers=user_headers,
            )
            assert log_analyses_denied["code"] == "permission_denied"
            suggestions_denied = await expected_error(
                client,
                "GET",
                "/api/v1/ai/test-suggestions",
                403,
                headers=user_headers,
            )
            assert suggestions_denied["code"] == "permission_denied"
            root_risk_denied = await expected_error(
                client,
                "GET",
                "/api/v1/ai/root-cause-risk",
                403,
                headers=user_headers,
            )
            assert root_risk_denied["code"] == "permission_denied"
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
