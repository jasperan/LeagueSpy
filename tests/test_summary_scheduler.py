"""Tests for the 8-hour summary scheduler boundary logic."""

from datetime import datetime, time
from src.bot import should_fire_summary


class TestShouldFireSummary:
    def test_fires_at_0800(self):
        now = datetime(2026, 3, 16, 8, 0, 30)
        last = datetime(2026, 3, 16, 7, 59, 0)
        assert should_fire_summary(now, last) is True

    def test_fires_at_1600(self):
        now = datetime(2026, 3, 16, 16, 0, 30)
        last = datetime(2026, 3, 16, 15, 59, 0)
        assert should_fire_summary(now, last) is True

    def test_fires_at_0000(self):
        now = datetime(2026, 3, 17, 0, 0, 30)
        last = datetime(2026, 3, 16, 23, 59, 0)
        assert should_fire_summary(now, last) is True

    def test_does_not_fire_between_boundaries(self):
        now = datetime(2026, 3, 16, 10, 30, 0)
        last = datetime(2026, 3, 16, 10, 29, 0)
        assert should_fire_summary(now, last) is False

    def test_does_not_double_fire(self):
        now = datetime(2026, 3, 16, 8, 1, 0)
        last = datetime(2026, 3, 16, 8, 0, 30)
        assert should_fire_summary(now, last) is False
