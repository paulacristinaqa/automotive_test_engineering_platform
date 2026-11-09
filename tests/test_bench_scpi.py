import pytest

from atep.bench.scpi import (
    DATA_OUT_OF_RANGE,
    ILLEGAL_PARAMETER_VALUE,
    MISSING_PARAMETER,
    OVERLOAD,
    Instrument,
    ScpiCommand,
    ScpiError,
    format_number,
    parse_channel_list,
    parse_command,
)


@pytest.mark.parametrize(
    ("text", "header", "query", "args"),
    [
        ("VOLT 12.5", "VOLT", False, ("12.5",)),
        (":VOLTage 12.5", "VOLT", False, ("12.5",)),
        ("meas:curr?", "MEAS:CURR", True, ()),
        ("MEASure:CURRent:DC?", "MEAS:CURR:DC", True, ()),
        ("SOUR:RES 1.6,(@1)", "SOUR:RES", False, ("1.6", "(@1)")),
        ("ROUT:CLOS (@1,3)", "ROUT:CLOS", False, ("(@1,3)",)),
        ("*idn?", "*IDN", True, ()),
        ("SYSTem:ERRor?", "SYST:ERR", True, ()),
    ],
)
def test_parse_command(text: str, header: str, query: bool, args: tuple[str, ...]) -> None:
    assert parse_command(text) == ScpiCommand(header, query, args)


@pytest.mark.parametrize("text", ["", "   ", ":"])
def test_empty_commands_are_errors(text: str) -> None:
    with pytest.raises(ScpiError):
        parse_command(text)


def test_channel_lists() -> None:
    assert parse_channel_list("(@1)", valid=range(1, 5)) == [1]
    assert parse_channel_list("(@1,3)", valid=range(1, 5)) == [1, 3]
    assert parse_channel_list("(@1:4)", valid=range(1, 5)) == [1, 2, 3, 4]
    with pytest.raises(ScpiError) as out_of_range:
        parse_channel_list("(@5)", valid=range(1, 5))
    assert out_of_range.value.code == DATA_OUT_OF_RANGE
    with pytest.raises(ScpiError) as bad:
        parse_channel_list("(@a)", valid=range(1, 5))
    assert bad.value.code == ILLEGAL_PARAMETER_VALUE


def test_parameters() -> None:
    command = parse_command("VOLT 12.5")
    assert command.number(minimum=0, maximum=60) == 12.5
    with pytest.raises(ScpiError) as high:
        command.number(minimum=0, maximum=10)
    assert high.value.code == DATA_OUT_OF_RANGE
    with pytest.raises(ScpiError) as missing:
        parse_command("VOLT").number(minimum=0, maximum=1)
    assert missing.value.code == MISSING_PARAMETER
    with pytest.raises(ScpiError):
        parse_command("VOLT abc").number(minimum=0, maximum=1)
    assert parse_command("OUTP on").boolean() is True
    assert parse_command("OUTP 0").boolean() is False
    with pytest.raises(ScpiError):
        parse_command("OUTP").boolean()
    with pytest.raises(ScpiError):
        parse_command("ROUT:CLOS").channels(valid=range(1, 2))


def test_number_format_and_overload() -> None:
    assert format_number(0.15) == "1.500000E-01"
    assert format_number(float("inf")) == OVERLOAD
    assert format_number(float("nan")) == OVERLOAD


def test_base_instrument_common_commands_and_error_queue() -> None:
    instrument = Instrument()
    assert instrument.execute("*IDN?", 0) == Instrument.identity
    assert instrument.execute("*OPC?", 0) == "1"
    assert instrument.execute("*RST", 0) is None
    assert instrument.execute("FOO", 0) is None
    assert instrument.execute("BAR?", 0) is None
    assert instrument.execute("SYST:ERR?", 0) == '-113,"Undefined header"'
    assert instrument.execute("*CLS", 0) is None
    assert instrument.execute("SYST:ERR?", 0) == '0,"No error"'
    for _ in range(30):
        instrument.execute("FOO", 0)
    assert len(instrument.errors) == 20
