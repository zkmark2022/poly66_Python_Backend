"""Snowflake-style ID generator for business IDs (trade_id, etc.).

Generates monotonically increasing, unique string IDs.
Not a full Twitter Snowflake — simplified for single-process MVP.
"""

import threading
import time


class SnowflakeIdGenerator:
    """Simple snowflake ID generator.

    Layout (64 bits):
      - 41 bits: millisecond timestamp (since custom epoch)
      - 10 bits: machine_id (0-1023)
      - 12 bits: sequence (0-4095 per millisecond)
    """

    _EPOCH_MS = 1_700_000_000_000  # 2023-11-14 approx
    _MACHINE_BITS = 10
    _SEQUENCE_BITS = 12
    _MAX_SEQUENCE = (1 << _SEQUENCE_BITS) - 1

    def __init__(self, machine_id: int = 0) -> None:
        if not (0 <= machine_id < (1 << self._MACHINE_BITS)):
            raise ValueError(f"machine_id must be 0-{(1 << self._MACHINE_BITS) - 1}")
        self._machine_id = machine_id
        self._sequence = 0
        self._last_timestamp_ms = -1
        self._lock = threading.Lock()

    def next_id(self) -> str:
        with self._lock:
            ts = self._current_ms()
            if ts == self._last_timestamp_ms:
                self._sequence = (self._sequence + 1) & self._MAX_SEQUENCE
                if self._sequence == 0:
                    ts = self._wait_next_ms(ts)
            else:
                self._sequence = 0

            self._last_timestamp_ms = ts
            id_int = (
                ((ts - self._EPOCH_MS) << (self._MACHINE_BITS + self._SEQUENCE_BITS))
                | (self._machine_id << self._SEQUENCE_BITS)
                | self._sequence
            )
            return str(id_int)

    def _current_ms(self) -> int:
        return int(time.time() * 1000)

    def _wait_next_ms(self, last_ts: int) -> int:
        ts = self._current_ms()
        while ts <= last_ts:
            ts = self._current_ms()
        return ts


_default_generator = SnowflakeIdGenerator()


def generate_id() -> str:
    """Generate a unique snowflake-style string ID using the module-level default generator."""
    return _default_generator.next_id()
