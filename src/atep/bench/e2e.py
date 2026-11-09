"""End-to-end (E2E) protection modelled on AUTOSAR E2E Profile 1.

A sender writes a 4-bit alive counter and a CRC-8 (SAE J1850) computed over a
16-bit data ID and the payload. A receiver checks both and classifies every
frame. This is a teaching model of the profile, not a certified implementation.
"""

from dataclasses import dataclass
from enum import StrEnum

COUNTER_MODULO = 15  # Profile 1 counts 0..14; 15 is invalid.


def crc8_sae_j1850(data: bytes, *, initial: int = 0xFF) -> int:
    """CRC-8 SAE J1850: polynomial 0x1D, initial 0xFF, final XOR 0xFF."""
    crc = initial
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1D) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc ^ 0xFF


class E2EStatus(StrEnum):
    OK = "ok"
    OK_SOME_LOST = "ok_some_lost"
    INITIAL = "initial"
    REPEATED = "repeated"
    WRONG_SEQUENCE = "wrong_sequence"
    WRONG_CRC = "wrong_crc"
    INVALID_COUNTER = "invalid_counter"


@dataclass(frozen=True)
class E2EConfig:
    data_id: int
    length: int
    crc_byte: int = 0
    counter_byte: int = 1
    max_delta_counter: int = 2

    def __post_init__(self) -> None:
        if not 0 <= self.data_id <= 0xFFFF:
            raise ValueError("data ID is 16 bits")
        if self.crc_byte == self.counter_byte:
            raise ValueError("CRC and counter need separate bytes")
        if not (0 <= self.crc_byte < self.length and 0 <= self.counter_byte < self.length):
            raise ValueError("CRC and counter must lie inside the payload")
        if not 1 <= self.max_delta_counter < COUNTER_MODULO:
            raise ValueError("max delta counter must be between 1 and 14")


def compute_crc(config: E2EConfig, payload: bytes) -> int:
    covered = bytes(byte for index, byte in enumerate(payload) if index != config.crc_byte)
    return crc8_sae_j1850(config.data_id.to_bytes(2, "little") + covered)


class E2EProtector:
    """Sender side: stamps counter and CRC into each payload."""

    def __init__(self, config: E2EConfig) -> None:
        self.config = config
        self.counter = 0

    def protect(self, payload: bytes) -> bytes:
        if len(payload) != self.config.length:
            raise ValueError(f"protected payload must be {self.config.length} bytes")
        data = bytearray(payload)
        index = self.config.counter_byte
        data[index] = (data[index] & 0xF0) | self.counter
        data[self.config.crc_byte] = 0
        data[self.config.crc_byte] = compute_crc(self.config, bytes(data))
        self.counter = (self.counter + 1) % COUNTER_MODULO
        return bytes(data)


class E2EChecker:
    """Receiver side: verifies CRC and counter progression."""

    def __init__(self, config: E2EConfig) -> None:
        self.config = config
        self.last_counter: int | None = None

    def check(self, payload: bytes) -> E2EStatus:
        if len(payload) != self.config.length:
            return E2EStatus.WRONG_CRC
        if payload[self.config.crc_byte] != compute_crc(self.config, payload):
            return E2EStatus.WRONG_CRC
        counter = payload[self.config.counter_byte] & 0x0F
        if counter >= COUNTER_MODULO:
            return E2EStatus.INVALID_COUNTER
        previous = self.last_counter
        if previous is None:
            self.last_counter = counter
            return E2EStatus.INITIAL
        delta = (counter - previous) % COUNTER_MODULO
        if delta == 0:
            return E2EStatus.REPEATED
        self.last_counter = counter
        if delta == 1:
            return E2EStatus.OK
        if delta <= self.config.max_delta_counter:
            return E2EStatus.OK_SOME_LOST
        return E2EStatus.WRONG_SEQUENCE
