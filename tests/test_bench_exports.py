import io
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import can
import cantools
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from atep.bench import router as bench_router
from atep.bench.export_service import export_dbc, load_trace_page
from atep.bench.reference import BMS_ID, VCU_ID, reference_spec
from atep.can_network.models import CanDbcCatalogue, CanFrameTransmission, CanNetwork
from atep.core.errors import CanNetworkContractError, install_exception_handlers
from atep.db.session import get_session
from atep.identity.dependencies import current_user
from atep.identity.permissions import PermissionName
from atep.vehicles.models import Vehicle

CREATED = datetime(2026, 11, 9, 8, 30, 0, 250_000, tzinfo=UTC)


class FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows

    def scalars(self) -> "FakeResult":
        return self


class FakeSession:
    def __init__(self, scalars: list[Any], results: list[list[Any]]) -> None:
        self.scalar_values = list(scalars)
        self.results = list(results)
        self.statements: list[Any] = []
        self.added: list[Any] = []

    async def scalar(self, statement: Any) -> Any:
        self.statements.append(statement)
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.results.pop(0) if self.results else [])

    def add(self, value: Any) -> None:
        self.added.append(value)


def _vehicle() -> Vehicle:
    return Vehicle(id=uuid4(), identifier="vehicle-001", display_name="Reference EV")


def _network(vehicle: Vehicle) -> CanNetwork:
    spec = reference_spec()
    return CanNetwork(
        id=uuid4(),
        vehicle_id=vehicle.id,
        identifier="powertrain-can",
        display_name="Powertrain CAN",
        bitrate_kbps=500,
        can_fd_enabled=True,
        data_bitrate_kbps=2000,
        nodes=[
            {"ecu_id": str(BMS_ID), "role": "participant"},
            {"ecu_id": str(VCU_ID), "role": "participant"},
        ],
        frame_contracts=[frame.model_dump(mode="json") for frame in spec.frames],
        version=7,
        created_at=CREATED,
    )


def _catalogue(network: CanNetwork) -> CanDbcCatalogue:
    return CanDbcCatalogue(
        network_id=network.id,
        identifier="reference-dbc",
        display_name="Reference DBC",
        revision="2.1.0",
        messages=[m.model_dump(mode="json") for m in reference_spec().messages.values()],
    )


def _transmission(network: CanNetwork, sequence: int, **overrides: Any) -> CanFrameTransmission:
    values: dict[str, Any] = {
        "network_id": network.id,
        "command_id": f"cmd-{sequence:08d}",
        "contract_id": "bms-status",
        "frame_id": 0x180,
        "frame_format": "standard",
        "protocol": "classic",
        "bitrate_switch": False,
        "payload": [sequence, 0, 0, 0],
        "sequence": sequence,
        "transmission_time_us": sequence * 10_000,
    }
    return CanFrameTransmission(**(values | overrides))


@pytest.mark.asyncio
async def test_dbc_export_uses_catalogue_revision_and_ecu_names() -> None:
    vehicle = _vehicle()
    network = _network(vehicle)
    session = FakeSession([_catalogue(network)], [[(BMS_ID, "bms-main"), (VCU_ID, "vcu")]])
    text = await export_dbc(cast(AsyncSession, session), network=network)
    assert text.startswith('VERSION "2.1.0"')
    assert "BU_: bms_main vcu" in text
    database = cantools.database.load_string(text, database_format="dbc")
    assert isinstance(database, cantools.database.can.Database)
    assert database.get_message_by_name("bms_status").senders == ["bms_main"]


@pytest.mark.asyncio
async def test_dbc_export_without_catalogue_or_ecu_records_still_lists_frames() -> None:
    network = _network(_vehicle())
    session = FakeSession([None], [[]])
    text = await export_dbc(cast(AsyncSession, session), network=network)
    assert text.startswith('VERSION "network-v7"')
    assert f"BU_: ECU_{BMS_ID.hex} ECU_{VCU_ID.hex}" in text
    assert " SG_ " not in text


@pytest.mark.asyncio
async def test_dbc_export_maps_collisions_to_contract_error() -> None:
    network = _network(_vehicle())
    session = FakeSession([None], [[(BMS_ID, "front-ecu"), (VCU_ID, "front_ecu")]])
    with pytest.raises(CanNetworkContractError):
        await export_dbc(cast(AsyncSession, session), network=network)


@pytest.mark.asyncio
async def test_trace_page_is_bounded_and_reports_truncation() -> None:
    network = _network(_vehicle())
    rows = [_transmission(network, sequence) for sequence in (4, 5, 6)]
    session = FakeSession([], [rows])
    page = await load_trace_page(
        cast(AsyncSession, session), network=network, after_sequence=3, limit=2
    )
    assert [frame.timestamp_us for frame in page.frames] == [40_000, 50_000]
    assert (page.last_sequence, page.truncated) == (5, True)
    compiled = str(session.statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "sequence > 3" in compiled and "ORDER BY" in compiled and "LIMIT 3" in compiled

    with pytest.raises(ValueError):
        await load_trace_page(
            cast(AsyncSession, session), network=network, after_sequence=0, limit=0
        )


@pytest.mark.asyncio
async def test_trace_page_maps_extended_and_fd_evidence() -> None:
    network = _network(_vehicle())
    row = _transmission(
        network,
        1,
        frame_format="extended",
        protocol="fd",
        bitrate_switch=True,
        payload=list(range(12)),
    )
    page = await load_trace_page(
        cast(AsyncSession, FakeSession([], [[row]])), network=network, after_sequence=0, limit=10
    )
    frame = page.frames[0]
    assert (frame.is_extended_id, frame.is_fd, frame.bitrate_switch, len(frame.data)) == (
        True,
        True,
        True,
        12,
    )
    assert page.truncated is False


def _client(session: FakeSession, permissions: set[str]) -> Iterator[TestClient]:
    app = FastAPI()
    install_exception_handlers(app)
    app.include_router(bench_router.router, prefix="/api/v1")

    async def fake_session() -> FakeSession:
        return session

    app.dependency_overrides[get_session] = fake_session
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(permission_names=permissions)
    with TestClient(app) as client:
        yield client


READ = {PermissionName.CAN_NETWORKS_READ.value}


def test_dbc_endpoint_downloads_a_windows_1252_attachment() -> None:
    vehicle = _vehicle()
    network = _network(vehicle)
    session = FakeSession([vehicle, network, _catalogue(network)], [[]])
    client = next(_client(session, READ))
    response = client.get("/api/v1/vehicles/vehicle-001/can-networks/exports/dbc")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="vehicle-001-powertrain-can.dbc"'
    )
    assert response.content.startswith(b'VERSION "2.1.0"\r\n')
    assert session.added == []


def test_trace_endpoint_returns_asc_and_blf_with_paging_headers() -> None:
    vehicle = _vehicle()
    network = _network(vehicle)
    rows = [_transmission(network, sequence) for sequence in (1, 2)]
    session = FakeSession([vehicle, network], [rows])
    client = next(_client(session, READ))
    response = client.get(
        "/api/v1/vehicles/vehicle-001/can-networks/exports/trace", params={"limit": 1}
    )
    assert response.status_code == 200
    assert response.headers["x-atep-frame-count"] == "1"
    assert response.headers["x-atep-truncated"] == "true"
    assert response.headers["x-atep-last-sequence"] == "1"
    assert response.text.startswith("date Mon Nov 09 08:30:00.250 2026")
    assert [m.arbitration_id for m in can.ASCReader(io.StringIO(response.text))] == [0x180]

    session = FakeSession([vehicle, network], [rows])
    client = next(_client(session, READ))
    response = client.get(
        "/api/v1/vehicles/vehicle-001/can-networks/exports/trace", params={"format": "blf"}
    )
    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith('.blf"')
    assert response.headers["x-atep-truncated"] == "false"
    assert len(list(can.BLFReader(io.BytesIO(response.content)))) == 2


def test_exports_require_can_read_permission_and_validate_limits() -> None:
    vehicle = _vehicle()
    session = FakeSession([vehicle, _network(vehicle)], [[]])
    client = next(_client(session, set()))
    for path in ("dbc", "trace"):
        response = client.get(f"/api/v1/vehicles/vehicle-001/can-networks/exports/{path}")
        assert response.status_code == 403
    client = next(_client(FakeSession([], []), READ))
    response = client.get(
        "/api/v1/vehicles/vehicle-001/can-networks/exports/trace", params={"limit": 10_001}
    )
    assert response.status_code == 422


def test_unknown_vehicle_is_not_found() -> None:
    client = next(_client(FakeSession([None], []), READ))
    response = client.get("/api/v1/vehicles/missing/can-networks/exports/dbc")
    assert response.status_code == 404


def test_router_is_registered_in_the_core_app() -> None:
    from atep.main import app

    paths = app.openapi()["paths"]
    assert "/api/v1/vehicles/{vehicle_id}/can-networks/exports/dbc" in paths
    assert "/api/v1/vehicles/{vehicle_id}/can-networks/exports/trace" in paths
    assert UUID(int=1) != BMS_ID
