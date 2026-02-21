"""Tests for pm_common.id_generator and pm_common.datetime_utils."""

from datetime import UTC, datetime

from src.pm_common.datetime_utils import utc_now
from src.pm_common.id_generator import SnowflakeIdGenerator


class TestSnowflakeIdGenerator:
    def test_returns_str(self) -> None:
        gen = SnowflakeIdGenerator(machine_id=1)
        result = gen.next_id()
        assert isinstance(result, str)

    def test_unique_ids(self) -> None:
        gen = SnowflakeIdGenerator(machine_id=1)
        ids = {gen.next_id() for _ in range(1000)}
        assert len(ids) == 1000

    def test_monotonically_increasing(self) -> None:
        gen = SnowflakeIdGenerator(machine_id=1)
        prev = int(gen.next_id())
        for _ in range(100):
            current = int(gen.next_id())
            assert current > prev
            prev = current


class TestUtcNow:
    def test_returns_aware_datetime(self) -> None:
        now = utc_now()
        assert isinstance(now, datetime)
        assert now.tzinfo is not None

    def test_is_utc(self) -> None:
        now = utc_now()
        assert now.tzinfo == UTC
