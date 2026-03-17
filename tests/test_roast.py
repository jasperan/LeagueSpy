import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.cogs.roast import build_roast_context, classify_trigger, SYSTEM_PROMPT


class TestClassifyTrigger:
    def test_single_loss(self):
        assert classify_trigger(win=False, streak=-1, kills=3) == "single_loss"

    def test_streak_2(self):
        assert classify_trigger(win=False, streak=-2, kills=3) == "streak"

    def test_streak_5(self):
        assert classify_trigger(win=False, streak=-5, kills=3) == "streak"

    def test_zero_kills(self):
        assert classify_trigger(win=False, streak=-1, kills=0) == "zero_kills"

    def test_perfect_kda_win(self):
        assert classify_trigger(win=True, streak=1, kills=10, deaths=0) == "perfect_kda"

    def test_normal_win_no_trigger(self):
        assert classify_trigger(win=True, streak=1, kills=5, deaths=3) is None


class TestBuildRoastContext:
    def test_single_loss_context(self):
        ctx = build_roast_context(
            player_name="jasper", champion="Yasuo", kda="2/8/1",
            duration="19min 48s", streak=-1, recent_roasts=[],
        )
        assert "jasper" in ctx
        assert "Yasuo" in ctx
        assert "2/8/1" in ctx

    def test_streak_context_includes_count(self):
        ctx = build_roast_context(
            player_name="jasper", champion="Yasuo", kda="0/7/2",
            duration="15min 20s", streak=-4, recent_roasts=[],
        )
        assert "4" in ctx

    def test_dedup_section_present(self):
        ctx = build_roast_context(
            player_name="jasper", champion="Lux", kda="1/5/3",
            duration="28min", streak=-1, recent_roasts=["Roast one", "Roast two"],
        )
        assert "No repitas" in ctx
        assert "Roast one" in ctx

    def test_dedup_section_absent_when_no_history(self):
        ctx = build_roast_context(
            player_name="jasper", champion="Lux", kda="1/5/3",
            duration="28min", streak=-1, recent_roasts=[],
        )
        assert "No repitas" not in ctx


def test_system_prompt_is_spanish():
    assert "espanol" in SYSTEM_PROMPT.lower() or "español" in SYSTEM_PROMPT.lower()
