from typing import Annotated

from fastapi import Body, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from atep.core.errors import DuplicateEmailError, install_exception_handlers
from atep.main import app as core_app


class ExampleCommand(BaseModel):
    name: str = Field(min_length=3)


def test_application_errors_use_global_contract() -> None:
    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/duplicate")
    async def duplicate() -> None:
        raise DuplicateEmailError

    response = TestClient(app).get("/duplicate")
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "email_already_exists",
            "message": "A user with this email already exists.",
            "details": None,
        },
        "correlation_id": "unavailable",
    }


def test_request_validation_uses_global_contract() -> None:
    app = FastAPI()
    install_exception_handlers(app)

    @app.post("/commands")
    async def command(payload: Annotated[ExampleCommand, Body()]) -> ExampleCommand:
        return payload

    response = TestClient(app).post("/commands", json={"name": "x"})
    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"][0]["location"] == ["body", "name"]


def test_user_pagination_has_safe_openapi_limits() -> None:
    operation = core_app.openapi()["paths"]["/api/v1/users"]["get"]
    parameters = {item["name"]: item["schema"] for item in operation["parameters"]}
    assert parameters["limit"] == {
        "type": "integer",
        "maximum": 100,
        "minimum": 1,
        "default": 50,
        "title": "Limit",
    }
    assert parameters["offset"]["minimum"] == 0
    assert parameters["offset"]["maximum"] == 1_000_000
    assert parameters["offset"]["default"] == 0


def test_role_catalogue_contracts_and_safe_pagination_are_published() -> None:
    schema = core_app.openapi()
    paths = schema["paths"]
    assert "/api/v1/permissions" in paths
    assert "/api/v1/roles" in paths
    assert "/api/v1/roles/{role_id}" in paths
    assert "/api/v1/roles/{role_id}/permissions/{permission_name}" in paths
    parameters = {
        item["name"]: item["schema"] for item in paths["/api/v1/roles"]["get"]["parameters"]
    }
    assert parameters["limit"]["minimum"] == 1
    assert parameters["limit"]["maximum"] == 100
    assert parameters["offset"]["minimum"] == 0
    assert parameters["offset"]["maximum"] == 1_000_000


def test_refresh_and_logout_contracts_are_published() -> None:
    schema = core_app.openapi()
    paths = schema["paths"]
    assert "/api/v1/auth/refresh" in paths
    assert "/api/v1/auth/logout" in paths
    assert "/api/v1/auth/logout-all" in paths
    token_schema = schema["components"]["schemas"]["TokenResponse"]
    assert set(token_schema["required"]) == {
        "access_token",
        "refresh_token",
        "expires_in",
        "refresh_expires_in",
    }


def test_audit_query_and_export_contracts_have_safe_limits() -> None:
    paths = core_app.openapi()["paths"]
    assert "/api/v1/audit-records" in paths
    assert "/api/v1/audit-records/export" in paths
    assert "/api/v1/audit-records/{record_id}" in paths

    list_parameters = {
        item["name"]: item["schema"] for item in paths["/api/v1/audit-records"]["get"]["parameters"]
    }
    assert list_parameters["limit"]["maximum"] == 100
    assert list_parameters["offset"]["maximum"] == 1_000_000

    export_parameters = {
        item["name"]: item["schema"]
        for item in paths["/api/v1/audit-records/export"]["get"]["parameters"]
    }
    assert export_parameters["limit"]["maximum"] == 10_000
    assert export_parameters["limit"]["default"] == 1_000


def test_module_registry_contracts_and_safe_pagination_are_published() -> None:
    paths = core_app.openapi()["paths"]
    assert "/api/v1/modules" in paths
    assert "/api/v1/modules/{module_id}" in paths
    capability_path = "/api/v1/modules/{module_id}/capabilities/{capability_name}"
    assert capability_path in paths
    assert {"put", "delete"} <= set(paths[capability_path])
    assert "/api/v1/modules/{module_id}/credentials" in paths
    assert "/api/v1/modules/{module_id}/heartbeat" in paths
    assert "/api/v1/modules/health-summary" in paths
    heartbeat = paths["/api/v1/modules/{module_id}/heartbeat"]["post"]
    heartbeat_headers = {
        item["name"]: item for item in heartbeat["parameters"] if item["in"] == "header"
    }
    assert "X-ATEP-Module-Token" in heartbeat_headers
    assert "X-Forwarded-Client-Cert" in heartbeat_headers
    assert heartbeat_headers["X-ATEP-Module-Token"]["required"] is False
    assert heartbeat_headers["X-Forwarded-Client-Cert"]["required"] is False

    parameters = {
        item["name"]: item["schema"] for item in paths["/api/v1/modules"]["get"]["parameters"]
    }
    assert parameters["limit"]["minimum"] == 1
    assert parameters["limit"]["maximum"] == 100
    assert parameters["offset"]["maximum"] == 1_000_000
    assert "status" in parameters
    assert "capability" in parameters


def test_vehicle_gateway_contracts_and_safe_pagination_are_published() -> None:
    paths = core_app.openapi()["paths"]
    assert "/api/v1/vehicles" in paths
    assert "/api/v1/vehicles/{vehicle_id}" in paths
    assert "/api/v1/vehicles/{vehicle_id}/status" in paths
    telemetry_path = paths["/api/v1/vehicles/{vehicle_id}/telemetry"]
    assert {"get", "post"} <= set(telemetry_path)
    headers = {
        item["name"]: item
        for item in telemetry_path["post"]["parameters"]
        if item["in"] == "header"
    }
    assert {"X-ATEP-Module-ID", "X-ATEP-Module-Token", "X-Forwarded-Client-Cert"} <= set(headers)
    list_parameters = {
        item["name"]: item["schema"] for item in paths["/api/v1/vehicles"]["get"]["parameters"]
    }
    assert list_parameters["limit"]["maximum"] == 100
    telemetry_parameters = {
        item["name"]: item["schema"] for item in telemetry_path["get"]["parameters"]
    }
    assert telemetry_parameters["limit"]["maximum"] == 500
    assert telemetry_parameters["offset"]["maximum"] == 1_000_000

    state_path = paths["/api/v1/vehicles/{vehicle_id}/state"]
    assert {"get", "put"} <= set(state_path)
    replace_schema = state_path["put"]["requestBody"]["content"]["application/json"]["schema"]
    assert replace_schema["$ref"].endswith("/DigitalVehicleStateReplace")
    transition_path = paths["/api/v1/vehicles/{vehicle_id}/simulation/transitions"]
    assert "post" in transition_path
    transition_schema = transition_path["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]
    assert transition_schema["$ref"].endswith("/VehicleSimulationTransitionCommand")
    step_path = paths["/api/v1/vehicles/{vehicle_id}/simulation/steps"]
    assert "post" in step_path
    step_schema = step_path["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert step_schema["$ref"].endswith("/VehicleSimulationStepCommand")


def test_vehicle_gateway_vhal_mapping_contract_is_published() -> None:
    operation = core_app.openapi()["paths"]["/api/v1/vehicle-gateway/vhal-mappings"]["get"]
    headers = {item["name"]: item for item in operation["parameters"] if item["in"] == "header"}

    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/VhalMappingCatalog"
    )
    assert {"X-ATEP-Module-ID", "X-ATEP-Module-Token", "X-Forwarded-Client-Cert"} <= set(headers)


def test_vehicle_command_delivery_contracts_are_published() -> None:
    paths = core_app.openapi()["paths"]
    command_path = paths["/api/v1/vehicles/{vehicle_id}/commands"]
    assert {"get", "post"} <= set(command_path)
    claim = paths["/api/v1/vehicles/{vehicle_id}/commands/claim"]["post"]
    acknowledgement = paths["/api/v1/vehicles/{vehicle_id}/commands/{command_id}/acknowledgement"][
        "post"
    ]
    for operation in (claim, acknowledgement):
        headers = {item["name"]: item for item in operation["parameters"] if item["in"] == "header"}
        assert {
            "X-ATEP-Module-ID",
            "X-ATEP-Module-Token",
            "X-Forwarded-Client-Cert",
        } <= set(headers)
    command_parameters = {
        item["name"]: item["schema"] for item in command_path["get"]["parameters"]
    }
    assert command_parameters["limit"]["maximum"] == 200
    assert command_parameters["offset"]["maximum"] == 1_000_000


def test_multi_vehicle_simulation_session_contracts_are_published() -> None:
    paths = core_app.openapi()["paths"]
    assert "post" in paths["/api/v1/simulation-sessions"]
    assert "get" in paths["/api/v1/simulation-sessions/{session_id}"]
    assert "post" in paths["/api/v1/simulation-sessions/{session_id}/snapshots"]
    restore = "/api/v1/simulation-sessions/{session_id}/snapshots/{snapshot_id}/restore"
    assert "post" in paths[restore]


def test_ecu_aggregate_contracts_and_safe_pagination_are_published() -> None:
    paths = core_app.openapi()["paths"]
    collection = paths["/api/v1/vehicles/{vehicle_id}/ecus"]
    assert {"get", "post"} <= set(collection)
    assert "get" in paths["/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}"]
    state = paths["/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/state"]
    assert "put" in state
    state_schema = state["put"]["requestBody"]["content"]["application/json"]["schema"]
    assert state_schema["$ref"].endswith("/EcuStateReplace")
    parameters = {item["name"]: item["schema"] for item in collection["get"]["parameters"]}
    assert parameters["limit"]["maximum"] == 100
    assert parameters["offset"]["maximum"] == 1_000_000
    assert "ecu_type" in parameters
    advance = paths["/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/simulation/advance"]
    reset = paths["/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/reset"]
    assert "post" in advance
    assert "post" in reset
    advance_schema = advance["post"]["requestBody"]["content"]["application/json"]["schema"]
    reset_schema = reset["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert advance_schema["$ref"].endswith("/EcuAdvanceCommand")
    assert reset_schema["$ref"].endswith("/EcuResetCommand")
    profiles = paths["/api/v1/ecu-profiles"]
    profile = paths["/api/v1/ecu-profiles/{ecu_type}"]
    assert "get" in profiles
    assert "get" in profile
    snapshots = paths["/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/memory/snapshots"]
    restore = paths[
        "/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/memory/snapshots/{snapshot_id}/restore"
    ]
    corruption = paths["/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/memory/corrupt"]
    assert {"get", "post"} <= set(snapshots)
    assert "post" in restore
    assert "post" in corruption
    observe_fault = paths["/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/faults/observe"]
    clear_fault = paths["/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/faults/{fault_code}/clear"]
    dtc_candidates = paths["/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/faults/dtc-candidates"]
    assert "post" in observe_fault
    assert "post" in clear_fault
    assert "get" in dtc_candidates
    signal_publish = paths[
        "/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/signals/{signal_name}/publish"
    ]
    signal_routes = paths["/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/signal-routes"]
    route_transfer = paths[
        "/api/v1/vehicles/{vehicle_id}/ecus/{ecu_id}/signal-routes/{route_id}/transfer"
    ]
    assert "post" in signal_publish
    assert {"get", "post"} <= set(signal_routes)
    assert "post" in route_transfer
    route_parameters = {item["name"]: item["schema"] for item in signal_routes["get"]["parameters"]}
    assert route_parameters["limit"]["maximum"] == 100
    assert route_parameters["offset"]["maximum"] == 1_000_000
    scenario_execute = paths["/api/v1/vehicles/{vehicle_id}/ecu-scenarios/execute"]
    scenario_list = paths["/api/v1/vehicles/{vehicle_id}/ecu-scenarios"]
    scenario_detail = paths["/api/v1/vehicles/{vehicle_id}/ecu-scenarios/{execution_id}"]
    assert "post" in scenario_execute
    assert "get" in scenario_list
    assert "get" in scenario_detail
    scenario_parameters = {
        item["name"]: item["schema"] for item in scenario_list["get"]["parameters"]
    }
    assert scenario_parameters["limit"]["maximum"] == 50
    assert scenario_parameters["offset"]["maximum"] == 1_000_000


def test_can_network_baseline_contracts_and_safe_pagination_are_published() -> None:
    paths = core_app.openapi()["paths"]
    collection = paths["/api/v1/vehicles/{vehicle_id}/can-networks"]
    frames = paths["/api/v1/vehicles/{vehicle_id}/can-networks/frames"]
    arbitrations = paths["/api/v1/vehicles/{vehicle_id}/can-networks/arbitrations"]
    execute = paths["/api/v1/vehicles/{vehicle_id}/can-networks/arbitrations/execute"]
    detail = paths["/api/v1/vehicles/{vehicle_id}/can-networks/arbitrations/{command_id}"]
    dbc_catalogue = paths["/api/v1/vehicles/{vehicle_id}/can-networks/dbc-catalogues"]
    dbc_encode = paths["/api/v1/vehicles/{vehicle_id}/can-networks/dbc/encode"]
    dbc_decode = paths["/api/v1/vehicles/{vehicle_id}/can-networks/dbc/decode"]
    codec_executions = paths["/api/v1/vehicles/{vehicle_id}/can-networks/dbc/executions"]
    codec_detail = paths["/api/v1/vehicles/{vehicle_id}/can-networks/dbc/executions/{command_id}"]
    faults = paths["/api/v1/vehicles/{vehicle_id}/can-networks/faults"]
    inject_fault = paths["/api/v1/vehicles/{vehicle_id}/can-networks/faults/inject"]
    recover_fault = paths["/api/v1/vehicles/{vehicle_id}/can-networks/faults/recover"]
    fault_detail = paths["/api/v1/vehicles/{vehicle_id}/can-networks/faults/{command_id}"]
    multibus_configure = paths["/api/v1/vehicles/{vehicle_id}/can-networks/multibus/configure"]
    gateway_execute = paths["/api/v1/vehicles/{vehicle_id}/can-networks/gateway/routes/execute"]
    gateway_executions = paths["/api/v1/vehicles/{vehicle_id}/can-networks/gateway/executions"]
    gateway_detail = paths[
        "/api/v1/vehicles/{vehicle_id}/can-networks/gateway/executions/{command_id}"
    ]
    assert {"get", "post"} <= set(collection)
    assert {"get", "post"} <= set(frames)
    assert "get" in arbitrations
    assert "post" in execute
    assert "get" in detail
    assert {"get", "post"} <= set(dbc_catalogue)
    assert "post" in dbc_encode
    assert "post" in dbc_decode
    assert "get" in codec_executions
    assert "get" in codec_detail
    assert "get" in faults
    assert "post" in inject_fault
    assert "post" in recover_fault
    assert "get" in fault_detail
    assert "post" in multibus_configure
    assert "post" in gateway_execute
    assert "get" in gateway_executions
    assert "get" in gateway_detail
    create_schema = collection["post"]["requestBody"]["content"]["application/json"]["schema"]
    submit_schema = frames["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert create_schema["$ref"].endswith("/CanNetworkCreate")
    assert submit_schema["$ref"].endswith("/CanFrameSubmitCommand")
    execute_schema = execute["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert execute_schema["$ref"].endswith("/CanArbitrationCommand")
    catalogue_schema = dbc_catalogue["post"]["requestBody"]["content"]["application/json"]["schema"]
    encode_schema = dbc_encode["post"]["requestBody"]["content"]["application/json"]["schema"]
    decode_schema = dbc_decode["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert catalogue_schema["$ref"].endswith("/CanDbcCatalogueCreate")
    assert encode_schema["$ref"].endswith("/CanSignalEncodeCommand")
    assert decode_schema["$ref"].endswith("/CanSignalDecodeCommand")
    inject_schema = inject_fault["post"]["requestBody"]["content"]["application/json"]["schema"]
    recover_schema = recover_fault["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert inject_schema["$ref"].endswith("/CanFaultInjectionCommand")
    assert recover_schema["$ref"].endswith("/CanBusRecoveryCommand")
    multibus_schema = multibus_configure["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]
    gateway_schema = gateway_execute["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert multibus_schema["$ref"].endswith("/MultiBusConfigurationCommand")
    assert gateway_schema["$ref"].endswith("/GatewayRouteCommand")
    schemas = core_app.openapi()["components"]["schemas"]
    network_properties = schemas["CanNetworkCreate"]["properties"]
    assert network_properties["can_fd_enabled"]["default"] is False
    assert network_properties["data_bitrate_kbps"]["anyOf"][0]["maximum"] == 8000
    frame_contract = schemas["CanFrameContract"]["properties"]
    assert frame_contract["protocol"]["$ref"].endswith("/CanFrameProtocol")
    assert frame_contract["dlc"]["maximum"] == 64
    submit_payload = schemas["CanFrameSubmitCommand"]["properties"]["payload"]
    assert submit_payload["maxItems"] == 64
    parameters = {item["name"]: item["schema"] for item in frames["get"]["parameters"]}
    assert parameters["limit"]["maximum"] == 200
    assert parameters["offset"]["maximum"] == 1_000_000
    arbitration_parameters = {
        item["name"]: item["schema"] for item in arbitrations["get"]["parameters"]
    }
    assert arbitration_parameters["limit"]["maximum"] == 200
    assert arbitration_parameters["offset"]["maximum"] == 1_000_000
    codec_parameters = {
        item["name"]: item["schema"] for item in codec_executions["get"]["parameters"]
    }
    assert codec_parameters["limit"]["maximum"] == 200
    assert codec_parameters["offset"]["maximum"] == 1_000_000
    fault_parameters = {item["name"]: item["schema"] for item in faults["get"]["parameters"]}
    assert fault_parameters["limit"]["maximum"] == 200
    assert fault_parameters["offset"]["maximum"] == 1_000_000
    gateway_parameters = {
        item["name"]: item["schema"] for item in gateway_executions["get"]["parameters"]
    }
    assert gateway_parameters["limit"]["maximum"] == 200
    assert gateway_parameters["offset"]["maximum"] == 1_000_000


def test_test_job_scheduler_contracts_and_safe_pagination_are_published() -> None:
    paths = core_app.openapi()["paths"]
    collection = paths["/api/v1/test-jobs"]
    assert {"get", "post"} <= set(collection)
    assert "/api/v1/test-jobs/{job_id}" in paths
    assert "patch" in paths["/api/v1/test-jobs/{job_id}/cancel"]
    parameters = {item["name"]: item["schema"] for item in collection["get"]["parameters"]}
    assert parameters["limit"]["maximum"] == 200
    assert parameters["offset"]["maximum"] == 1_000_000
    assert "status" in parameters
    assert "vehicle_id" in parameters


def test_test_artifact_contracts_and_safe_pagination_are_published() -> None:
    paths = core_app.openapi()["paths"]
    collection = paths["/api/v1/test-runs/{run_id}/artifacts"]
    assert {"get", "post"} <= set(collection)
    detail = "/api/v1/test-runs/{run_id}/artifacts/{artifact_id}"
    assert "get" in paths[detail]
    assert "get" in paths[f"{detail}/content"]
    upload_content = collection["post"]["requestBody"]["content"]
    assert "multipart/form-data" in upload_content
    parameters = {item["name"]: item["schema"] for item in collection["get"]["parameters"]}
    assert parameters["limit"]["maximum"] == 200
    assert parameters["offset"]["maximum"] == 1_000_000
    assert "kind" in parameters


def test_metrics_endpoint_is_operational_but_not_part_of_public_openapi() -> None:
    assert "/metrics" not in core_app.openapi()["paths"]
    response = TestClient(core_app).get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "atep_build_info" in response.text
    assert len(response.headers["x-trace-id"]) == 32
