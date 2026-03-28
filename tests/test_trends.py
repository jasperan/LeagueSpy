import pytest
from io import BytesIO
from PIL import Image
from src.trends import render_trends_chart, compute_rolling_win_rate, compute_kda_ratios


def _make_match(win=True, kills=5, deaths=2, assists=7, champion="Jinx", cs=200, gold=12000, kp=60, vs=10):
    return {
        "match_id": "test123",
        "champion": champion,
        "win": win,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "game_duration": "25min",
        "game_mode": "Ranked Solo",
        "played_at": "2h ago",
        "cs": cs,
        "gold": gold,
        "kill_participation": kp,
        "vision_score": vs,
    }


class TestComputeRollingWinRate:
    def test_empty(self):
        assert compute_rolling_win_rate([]) == []

    def test_single_win(self):
        assert compute_rolling_win_rate([_make_match(win=True)]) == [100.0]

    def test_single_loss(self):
        assert compute_rolling_win_rate([_make_match(win=False)]) == [0.0]

    def test_alternating(self):
        matches = [_make_match(win=bool(i % 2)) for i in range(4)]
        rates = compute_rolling_win_rate(matches, window=2)
        # Game 1: L -> 0%, Game 2: W -> 50%, Game 3: L -> 50%, Game 4: W -> 50%
        assert rates[0] == 0.0
        assert rates[1] == 50.0

    def test_all_wins(self):
        matches = [_make_match(win=True) for _ in range(10)]
        rates = compute_rolling_win_rate(matches)
        assert all(r == 100.0 for r in rates)

    def test_window_size(self):
        matches = [_make_match(win=False)] * 10 + [_make_match(win=True)] * 10
        rates = compute_rolling_win_rate(matches, window=10)
        assert rates[9] == 0.0  # first 10 losses
        assert rates[19] == 100.0  # last 10 wins


class TestComputeKDARatios:
    def test_empty(self):
        assert compute_kda_ratios([]) == []

    def test_normal_kda(self):
        ratios = compute_kda_ratios([_make_match(kills=5, deaths=2, assists=7)])
        assert ratios[0] == 6.0

    def test_zero_deaths_capped(self):
        ratios = compute_kda_ratios([_make_match(kills=10, deaths=0, assists=5)])
        assert ratios[0] == 10.0  # capped at 10

    def test_high_deaths(self):
        ratios = compute_kda_ratios([_make_match(kills=1, deaths=10, assists=2)])
        assert ratios[0] == pytest.approx(0.3, abs=0.01)


class TestRenderTrendsChart:
    def test_returns_none_for_empty(self):
        assert render_trends_chart([], "jasper") is None

    def test_returns_bytesio_for_single_match(self):
        result = render_trends_chart([_make_match()], "jasper")
        assert isinstance(result, BytesIO)

    def test_returns_valid_png(self):
        matches = [_make_match(win=bool(i % 2)) for i in range(20)]
        result = render_trends_chart(matches, "jasper")
        assert result is not None
        img = Image.open(result)
        assert img.format == "PNG"
        assert img.size == (800, 580)

    def test_50_matches(self):
        matches = [_make_match(win=bool(i % 3), champion=f"Champ{i%5}") for i in range(50)]
        result = render_trends_chart(matches, "jasper")
        assert result is not None
        img = Image.open(result)
        assert img.size == (800, 580)

    def test_all_losses(self):
        matches = [_make_match(win=False) for _ in range(10)]
        result = render_trends_chart(matches, "jasper")
        assert result is not None

    def test_player_name_in_image(self):
        """Just verify it doesn't crash with special characters."""
        result = render_trends_chart([_make_match()], "jasper#1971")
        assert result is not None
