from collections.abc import Mapping
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

log = structlog.get_logger()


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
    correlation_id: str


class ApplicationError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: Any | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        self.headers = headers


class DuplicateEmailError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="email_already_exists",
            message="A user with this email already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )


class DuplicateRoleNameError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="role_name_already_exists",
            message="A role with this name already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )


class DuplicateModuleNameError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="module_name_already_exists",
            message="A module with this name already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )


class DuplicateVehicleIdentifierError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="vehicle_identifier_already_exists",
            message="A vehicle with this identifier already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )


class DuplicateEcuIdentifierError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="ecu_identifier_already_exists",
            message="An ECU with this identifier already exists in the vehicle.",
            status_code=status.HTTP_409_CONFLICT,
        )


class EcuStateVersionConflictError(ApplicationError):
    def __init__(self, *, current_version: int) -> None:
        super().__init__(
            code="ecu_state_version_conflict",
            message="The ECU state was changed by another operation.",
            status_code=status.HTTP_409_CONFLICT,
            details={"current_version": current_version},
        )


class EcuSimulationCommandConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="ecu_simulation_command_conflict",
            message="The ECU simulation command identifier was already used differently.",
            status_code=status.HTTP_409_CONFLICT,
        )


class EcuExecutionStateError(ApplicationError):
    def __init__(self, *, current_state: str) -> None:
        super().__init__(
            code="ecu_execution_state_conflict",
            message="The ECU cannot execute cyclic tasks from its current state.",
            status_code=status.HTTP_409_CONFLICT,
            details={"current_state": current_state},
        )


class EcuProfileContractError(ApplicationError):
    def __init__(self, *, reason: str) -> None:
        super().__init__(
            code="ecu_profile_contract_invalid",
            message="The ECU state does not conform to its behavior profile.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"reason": reason},
        )


class EcuMemoryContractError(ApplicationError):
    def __init__(self, *, reason: str) -> None:
        super().__init__(
            code="ecu_memory_contract_invalid",
            message="The ECU memory operation is invalid.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"reason": reason},
        )


class EcuFaultContractError(ApplicationError):
    def __init__(self, *, reason: str) -> None:
        super().__init__(
            code="ecu_fault_contract_invalid",
            message="The ECU fault lifecycle operation is invalid.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"reason": reason},
        )


class EcuSignalContractError(ApplicationError):
    def __init__(self, *, reason: str) -> None:
        super().__init__(
            code="ecu_signal_contract_invalid",
            message="The ECU signal operation is invalid.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"reason": reason},
        )


class DuplicateEcuSignalRouteError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="ecu_signal_route_already_exists",
            message="A signal route with this identifier already exists for the gateway ECU.",
            status_code=status.HTTP_409_CONFLICT,
        )


class EcuScenarioExecutionConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="ecu_scenario_execution_conflict",
            message="The scenario execution identifier is already used by another request.",
            status_code=409,
        )


class CanNetworkAlreadyExistsError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="can_network_already_exists",
            message="The vehicle already has a CAN network.",
            status_code=status.HTTP_409_CONFLICT,
        )


class CanNetworkVersionConflictError(ApplicationError):
    def __init__(self, *, current_version: int) -> None:
        super().__init__(
            code="can_network_version_conflict",
            message="The CAN network was changed by another operation.",
            status_code=status.HTTP_409_CONFLICT,
            details={"current_version": current_version},
        )


class CanFrameCommandConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="can_frame_command_conflict",
            message="The CAN frame command identifier was already used differently.",
            status_code=status.HTTP_409_CONFLICT,
        )


class CanNetworkContractError(ApplicationError):
    def __init__(self, *, reason: str) -> None:
        super().__init__(
            code="can_network_contract_invalid",
            message="The CAN network operation violates its contract.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"reason": reason},
        )


class CanArbitrationCommandConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="can_arbitration_command_conflict",
            message="The CAN arbitration command identifier was already used differently.",
            status_code=status.HTTP_409_CONFLICT,
        )


class CanFaultCommandConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="can_fault_command_conflict",
            message="The CAN fault command identifier was already used differently.",
            status_code=status.HTTP_409_CONFLICT,
        )


class CanNodeBusOffError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="can_node_bus_off",
            message="The CAN node cannot transmit while it is bus-off.",
            status_code=status.HTTP_409_CONFLICT,
        )


class CanFaultStateError(ApplicationError):
    def __init__(self, *, reason: str) -> None:
        super().__init__(
            code="can_fault_state_invalid",
            message="The CAN fault operation is invalid for the current state.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"reason": reason},
        )


class CanDbcCatalogueAlreadyExistsError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="can_dbc_catalogue_already_exists",
            message="A DBC catalogue already exists for this CAN network.",
            status_code=status.HTTP_409_CONFLICT,
        )


class CanSignalCodecCommandConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="can_signal_codec_command_conflict",
            message="The CAN signal codec command identifier was already used differently.",
            status_code=status.HTTP_409_CONFLICT,
        )


class ModuleCapabilityRequiredError(ApplicationError):
    def __init__(self, capability: str) -> None:
        super().__init__(
            code="module_capability_required",
            message="The module is not authorized for this operation.",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"required_capability": capability},
        )


class TelemetryEventConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="telemetry_event_conflict",
            message="The event identifier was already used for different telemetry data.",
            status_code=status.HTTP_409_CONFLICT,
        )


class VehicleCommandConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="vehicle_command_conflict",
            message="The command identifier was already used for a different command.",
            status_code=status.HTTP_409_CONFLICT,
        )


class VehicleCommandStateError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="vehicle_command_state_conflict",
            message="The command cannot transition from its current state.",
            status_code=status.HTTP_409_CONFLICT,
        )


class VehicleStateVersionConflictError(ApplicationError):
    def __init__(self, *, current_version: int) -> None:
        super().__init__(
            code="vehicle_state_version_conflict",
            message="The digital vehicle state was changed by another operation.",
            status_code=status.HTTP_409_CONFLICT,
            details={"current_version": current_version},
        )


class VehicleSimulationTransitionConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="vehicle_simulation_transition_conflict",
            message="The simulation command identifier was already used differently.",
            status_code=status.HTTP_409_CONFLICT,
        )


class VehicleSimulationStepConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="vehicle_simulation_step_conflict",
            message="The simulation step command ID is already associated with another request.",
            status_code=status.HTTP_409_CONFLICT,
        )


class VehicleSimulationStateError(ApplicationError):
    def __init__(self, *, current_mode: str, requested_mode: str) -> None:
        super().__init__(
            code="vehicle_simulation_state_conflict",
            message="The requested deterministic simulation transition is not allowed.",
            status_code=status.HTTP_409_CONFLICT,
            details={"current_mode": current_mode, "requested_mode": requested_mode},
        )


class TestRunConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="test_run_conflict",
            message="The test-run identifier was already used for a different test run.",
            status_code=status.HTTP_409_CONFLICT,
        )


class TestRunVersionConflictError(ApplicationError):
    def __init__(self, *, current_version: int) -> None:
        super().__init__(
            code="test_run_version_conflict",
            message="The test run was changed by another operation.",
            status_code=status.HTTP_409_CONFLICT,
            details={"current_version": current_version},
        )


class TestRunStateError(ApplicationError):
    def __init__(self, *, current_status: str, requested_status: str) -> None:
        super().__init__(
            code="test_run_state_conflict",
            message="The requested test-run state transition is not allowed.",
            status_code=status.HTTP_409_CONFLICT,
            details={"current_status": current_status, "requested_status": requested_status},
        )


class EnvironmentProfileConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="environment_profile_conflict",
            message="The profile identifier was already used for a different environment profile.",
            status_code=status.HTTP_409_CONFLICT,
        )


class EnvironmentProfileVersionConflictError(ApplicationError):
    def __init__(self, *, current_version: int) -> None:
        super().__init__(
            code="environment_profile_version_conflict",
            message="The environment profile was changed by another operation.",
            status_code=status.HTTP_409_CONFLICT,
            details={"current_version": current_version},
        )


class EnvironmentProfileStateError(ApplicationError):
    def __init__(self, *, current_status: str, requested_status: str) -> None:
        super().__init__(
            code="environment_profile_state_conflict",
            message="The requested environment-profile operation is not allowed in its state.",
            status_code=status.HTTP_409_CONFLICT,
            details={"current_status": current_status, "requested_status": requested_status},
        )


class TestJobConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="test_job_conflict",
            message="The job or target test-run identifier was already used differently.",
            status_code=status.HTTP_409_CONFLICT,
        )


class TestJobVersionConflictError(ApplicationError):
    def __init__(self, *, current_version: int) -> None:
        super().__init__(
            code="test_job_version_conflict",
            message="The test job was changed by another operation.",
            status_code=status.HTTP_409_CONFLICT,
            details={"current_version": current_version},
        )


class TestJobStateError(ApplicationError):
    def __init__(self, *, current_status: str, requested_status: str) -> None:
        super().__init__(
            code="test_job_state_conflict",
            message="The requested test-job state transition is not allowed.",
            status_code=status.HTTP_409_CONFLICT,
            details={"current_status": current_status, "requested_status": requested_status},
        )


class TestArtifactConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="test_artifact_conflict",
            message="The artifact identifier was already used for different evidence.",
            status_code=status.HTTP_409_CONFLICT,
        )


class TestArtifactTooLargeError(ApplicationError):
    def __init__(self, *, max_bytes: int) -> None:
        super().__init__(
            code="test_artifact_too_large",
            message="The test artifact exceeds the configured size limit.",
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            details={"max_bytes": max_bytes},
        )


class EmptyTestArtifactError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="empty_test_artifact",
            message="A test artifact must contain at least one byte.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


class TestArtifactUnavailableError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="test_artifact_unavailable",
            message="The artifact metadata exists but its content is temporarily unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class InvalidCommandClaimError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="invalid_command_claim",
            message="The command claim is invalid or has expired.",
            status_code=status.HTTP_409_CONFLICT,
        )


class ProtectedRoleError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="protected_role",
            message="The protected platform role cannot be changed in this way.",
            status_code=status.HTTP_409_CONFLICT,
        )


class RoleInUseError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="role_in_use",
            message="The role cannot be deleted while it is assigned to users.",
            status_code=status.HTTP_409_CONFLICT,
        )


class ResourceNotFoundError(ApplicationError):
    def __init__(self, resource: str) -> None:
        super().__init__(
            code=f"{resource}_not_found",
            message=f"The requested {resource} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidRefreshTokenError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="invalid_refresh_token",
            message="The refresh token is invalid or expired.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class InvalidModuleCredentialError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="invalid_module_credential",
            message="The module credential is invalid or has been rotated.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class RateLimitExceededError(ApplicationError):
    def __init__(self, *, limit: int, remaining: int, reset_after: int) -> None:
        headers = {
            "Retry-After": str(reset_after),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_after),
        }
        super().__init__(
            code="rate_limit_exceeded",
            message="Too many requests. Retry later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"limit": limit, "remaining": remaining, "reset_after": reset_after},
            headers=headers,
        )


class RateLimitUnavailableError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="rate_limit_unavailable",
            message="Request protection is temporarily unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": "1"},
        )


def _correlation_id(request: Request) -> str:
    return str(getattr(request.state, "correlation_id", "unavailable"))


def _response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details),
        correlation_id=_correlation_id(request),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        return _response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            headers=exc.headers,
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict):
            code = str(detail.get("code", "http_error"))
            message = str(detail.get("message", "The request could not be completed."))
            details = detail.get("details")
        else:
            code = "http_error"
            message = str(detail)
            details = None
        return _response(
            request,
            status_code=exc.status_code,
            code=code,
            message=message,
            details=details,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "location": [str(part) for part in error["loc"]],
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return _response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message="The request contains invalid data.",
            details=details,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_request_error", error_type=type(exc).__name__)
        return _response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="An unexpected error occurred.",
        )
