from decimal import Decimal
from uuid import UUID

import cantools
import pytest

from atep.bench.reference import BMS_ID, VCU_ID, build_schedule, reference_spec
from atep.bench.vector_dbc import (
    DbcExportError,
    DbcNode,
    VectorNetworkSpec,
    dbc_identifier,
    encode_dbc,
    render_dbc,
)
from atep.can_network.dbc_service import decode_message, encode_message
from atep.can_network.schemas import CanDbcMessage, CanFrameContract


def _database(spec: VectorNetworkSpec) -> cantools.database.can.Database:
    database = cantools.database.load_string(render_dbc(spec), database_format="dbc")
    assert isinstance(database, cantools.database.can.Database)
    return database


def test_network_attributes_and_nodes_are_exported() -> None:
    spec = reference_spec()
    text = render_dbc(spec)
    database = _database(spec)

    assert [node.name for node in database.nodes] == ["BMS", "VCU"]
    assert 'BA_ "BusType" "CAN FD";' in text
    assert 'BA_ "Baudrate" 500000;' in text
    assert 'BA_ "BaudrateCANFD" 2000000;' in text
    assert 'BA_ "DBName" "bench_powertrain_can";' in text
    assert text.startswith('VERSION "XI-1"')


def test_frame_formats_map_to_dbc_ids_and_vframeformat() -> None:
    database = _database(reference_spec())

    status = database.get_message_by_name("bms_status")
    assert (status.frame_id, status.is_extended_frame, status.is_fd, status.length) == (
        0x180,
        False,
        False,
        4,
    )
    assert status.senders == ["BMS"]
    command = database.get_message_by_name("vcu_command")
    assert (command.frame_id, command.is_extended_frame, command.is_fd) == (0x18FF5010, True, False)
    cells = database.get_message_by_name("bms_cells")
    assert (cells.frame_id, cells.is_fd, cells.length) == (0x200, True, 16)
    assert 'BA_ "CANFD_BRS" BO_ 512 1;' in render_dbc(reference_spec())


def test_signal_layout_receivers_and_ranges_are_exported() -> None:
    database = _database(reference_spec())
    status = database.get_message_by_name("bms_status")

    voltage = status.get_signal_by_name("PackVoltage")
    assert (voltage.start, voltage.length, voltage.byte_order, voltage.is_signed) == (
        0,
        12,
        "little_endian",
        False,
    )
    assert (voltage.scale, voltage.offset, voltage.minimum, voltage.maximum) == (0.1, 0, 0, 409.5)
    assert (voltage.unit, voltage.receivers) == ("V", ["VCU"])

    current = status.get_signal_by_name("PackCurrent")
    assert (current.start, current.byte_order, current.is_signed) == (23, "big_endian", True)
    # No declared range: derived from the 12-bit signed raw range, 0.5 A per bit, -100 A offset.
    assert (current.minimum, current.maximum) == (-1124, 923.5)


def test_cantools_reproduces_atep_codec_for_every_scheduled_frame() -> None:
    spec = reference_spec()
    database = _database(spec)
    for item in build_schedule(spec, duration_ms=200):
        message = database.get_message_by_frame_id(item.frame.arbitration_id)
        encoded = message.encode({name: float(value) for name, value in item.values.items()})
        assert bytes(encoded) == item.frame.data
        decoded = message.decode(item.frame.data, decode_choices=False)
        assert isinstance(decoded, dict)
        _, atep_physical = decode_message(
            spec.messages[item.contract_id], payload=list(item.frame.data)
        )
        for name, value in atep_physical.items():
            actual = decoded[name]
            assert isinstance(actual, (int, float))
            assert float(value) == pytest.approx(float(actual), abs=1e-9)


def test_frames_without_signals_and_receivers_are_still_exported() -> None:
    spec = reference_spec()
    frame = CanFrameContract.model_validate(
        {"identifier": "diag-request", "frame_id": 0x7E0, "dlc": 8, "producer_node_id": str(VCU_ID)}
    )
    text = render_dbc(VectorNetworkSpec(**{**spec.__dict__, "frames": [*spec.frames, frame]}))
    assert "BO_ 2016 diag_request: 8 VCU\n\n" in text
    database = cantools.database.load_string(text, database_format="dbc")
    assert isinstance(database, cantools.database.can.Database)
    assert database.get_message_by_frame_id(0x7E0).signals == []


def test_receiverless_signals_use_vector_placeholder() -> None:
    spec = reference_spec()
    frame = CanFrameContract.model_validate(
        {"identifier": "bms-status", "frame_id": 0x180, "dlc": 4, "producer_node_id": str(BMS_ID)}
    )
    frames = [frame if item.identifier == "bms-status" else item for item in spec.frames]
    text = render_dbc(VectorNetworkSpec(**{**spec.__dict__, "frames": frames}))
    assert '"V" Vector__XXX' in text


def test_name_collisions_after_conversion_are_rejected() -> None:
    spec = reference_spec()
    clash = CanFrameContract.model_validate(
        {"identifier": "bms_status", "frame_id": 0x181, "dlc": 1, "producer_node_id": str(BMS_ID)}
    )
    with pytest.raises(DbcExportError, match="bms_status"):
        render_dbc(VectorNetworkSpec(**{**spec.__dict__, "frames": [*spec.frames, clash]}))

    nodes = [DbcNode(BMS_ID, "front-ecu"), DbcNode(VCU_ID, "front_ecu")]
    with pytest.raises(DbcExportError, match="Node"):
        render_dbc(VectorNetworkSpec(**{**spec.__dict__, "nodes": nodes}))


def test_unknown_references_are_rejected() -> None:
    spec = reference_spec()
    orphan = CanDbcMessage.model_validate(
        {
            "contract_id": "missing-frame",
            "signals": [
                {"identifier": "X", "start_bit": 0, "bit_length": 1, "byte_order": "intel"}
            ],
        }
    )
    with pytest.raises(DbcExportError, match="unknown frame"):
        render_dbc(
            VectorNetworkSpec(
                **{**spec.__dict__, "messages": {**spec.messages, "missing-frame": orphan}}
            )
        )

    stranger = CanFrameContract.model_validate(
        {
            "identifier": "stray",
            "frame_id": 0x300,
            "dlc": 1,
            "producer_node_id": "00000000-0000-4000-8000-000000000999",
        }
    )
    with pytest.raises(DbcExportError, match="unknown node"):
        render_dbc(VectorNetworkSpec(**{**spec.__dict__, "frames": [*spec.frames, stranger]}))


def test_output_is_byte_identical_and_encoded_for_vector_tools() -> None:
    first = render_dbc(reference_spec())
    assert first == render_dbc(reference_spec())
    encoded = encode_dbc(first + 'CM_ "25 °C";\n')
    assert b"\r\n" in encoded and b"\n" not in encoded.replace(b"\r\n", b"")
    assert "25 °C".encode("cp1252") in encoded


def test_identifier_conversion() -> None:
    assert dbc_identifier("bms-status") == "bms_status"
    assert dbc_identifier("9lives", fallback_prefix="ECU") == "ECU_9lives"
    assert dbc_identifier("front ecu") == "front_ecu"


def test_encode_matches_atep_round_trip_for_extended_signed_signal() -> None:
    spec = reference_spec()
    message = spec.messages["vcu-command"]
    values = {
        "TorqueRequest": Decimal("-3276.8"),
        "ContactorClose": Decimal(0),
        "AliveCounter": Decimal(15),
    }
    payload, _, _ = encode_message(message, dlc=8, values=values)
    database = _database(spec)
    decoded = database.decode_message(0x18FF5010, bytes(payload), decode_choices=False)
    assert decoded == {"TorqueRequest": -3276.8, "ContactorClose": 0, "AliveCounter": 15}
    assert UUID(int=0) != BMS_ID
