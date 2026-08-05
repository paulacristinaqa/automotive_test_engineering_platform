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
    assert {"X-ATEP-Module-ID", "X-ATEP-Module-Token"} <= set(headers)
    list_parameters = {
        item["name"]: item["schema"] for item in paths["/api/v1/vehicles"]["get"]["parameters"]
    }
    assert list_parameters["limit"]["maximum"] == 100
    telemetry_parameters = {
        item["name"]: item["schema"] for item in telemetry_path["get"]["parameters"]
    }
    assert telemetry_parameters["limit"]["maximum"] == 500
    assert telemetry_parameters["offset"]["maximum"] == 1_000_000


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
        assert {"X-ATEP-Module-ID", "X-ATEP-Module-Token"} <= set(headers)
    command_parameters = {
        item["name"]: item["schema"] for item in command_path["get"]["parameters"]
    }
    assert command_parameters["limit"]["maximum"] == 200
    assert command_parameters["offset"]["maximum"] == 1_000_000


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
