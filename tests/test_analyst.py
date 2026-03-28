import pytest
from src.cogs.analyst import build_analysis_context, ANALYST_SYSTEM_PROMPT


class TestBuildAnalysisContext:
    def test_includes_player_and_champion(self):
        ctx = build_analysis_context(
            player_name="jasper", champion="Jinx", win=True,
            kills=8, deaths=2, assists=10, cs=220, gold=14500,
            kill_participation=65, vision_score=12,
            game_duration="28min 30s", game_mode="Ranked Solo",
            averages=None,
        )
        assert "jasper" in ctx
        assert "Jinx" in ctx
        assert "VICTORIA" in ctx

    def test_loss_shows_derrota(self):
        ctx = build_analysis_context(
            player_name="jasper", champion="Yasuo", win=False,
            kills=2, deaths=8, assists=1, cs=150, gold=9000,
            kill_participation=20, vision_score=4,
            game_duration="22min 10s", game_mode="Ranked Solo",
            averages=None,
        )
        assert "DERROTA" in ctx

    def test_includes_averages_comparison(self):
        avgs = {
            "games": 15, "avg_kills": 6.2, "avg_deaths": 3.1,
            "avg_assists": 8.4, "avg_cs": 190.5, "avg_gold": 12800,
            "avg_kp": 58.3, "avg_vision": 10.2,
        }
        ctx = build_analysis_context(
            player_name="jasper", champion="Jinx", win=True,
            kills=8, deaths=2, assists=10, cs=220, gold=14500,
            kill_participation=65, vision_score=12,
            game_duration="28min 30s", game_mode="Ranked Solo",
            averages=avgs,
        )
        assert "15 partidas" in ctx
        assert "6.2" in ctx

    def test_no_averages_first_game(self):
        ctx = build_analysis_context(
            player_name="jasper", champion="NewChamp", win=True,
            kills=5, deaths=3, assists=7, cs=180, gold=11000,
            kill_participation=50, vision_score=8,
            game_duration="25min", game_mode="Ranked Solo",
            averages=None,
        )
        assert "sin medias historicas" in ctx

    def test_single_game_averages_treated_as_insufficient(self):
        avgs = {
            "games": 1, "avg_kills": 5.0, "avg_deaths": 3.0,
            "avg_assists": 7.0, "avg_cs": 180.0, "avg_gold": 11000,
            "avg_kp": 50.0, "avg_vision": 8.0,
        }
        ctx = build_analysis_context(
            player_name="jasper", champion="Jinx", win=True,
            kills=5, deaths=3, assists=7, cs=180, gold=11000,
            kill_participation=50, vision_score=8,
            game_duration="25min", game_mode="Ranked Solo",
            averages=avgs,
        )
        assert "sin medias historicas" in ctx

    def test_perfect_kda_zero_deaths(self):
        ctx = build_analysis_context(
            player_name="jasper", champion="Lux", win=True,
            kills=10, deaths=0, assists=5, cs=200, gold=13000,
            kill_participation=70, vision_score=15,
            game_duration="20min", game_mode="Ranked Solo",
            averages=None,
        )
        assert "PERFECTO" in ctx

    def test_all_stats_present(self):
        ctx = build_analysis_context(
            player_name="jasper", champion="Jinx", win=True,
            kills=8, deaths=2, assists=10, cs=220, gold=14500,
            kill_participation=65, vision_score=12,
            game_duration="28min 30s", game_mode="Ranked Solo",
            averages=None,
        )
        assert "220" in ctx  # CS
        assert "14500" in ctx  # gold
        assert "65" in ctx  # KP
        assert "12" in ctx  # vision


def test_analyst_system_prompt_is_spanish():
    assert "espanol" in ANALYST_SYSTEM_PROMPT.lower() or "español" in ANALYST_SYSTEM_PROMPT.lower()


def test_analyst_system_prompt_mentions_analyst():
    assert "analista" in ANALYST_SYSTEM_PROMPT.lower()
