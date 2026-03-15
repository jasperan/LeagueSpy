from src.models import SummonerConfig, MatchResult


def test_summoner_config_creation():
    s = SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")
    assert s.player_name == "jasper"
    assert s.slug == "jasper-1971"
    assert s.region == "euw"
    assert s.op_gg_url == "https://op.gg/lol/summoners/euw/jasper-1971"


def test_match_result_creation():
    m = MatchResult(
        match_id="EUW1-123456",
        champion="Jinx",
        win=True,
        kills=8,
        deaths=2,
        assists=5,
        game_duration="32:15",
        game_mode="Ranked Solo",
        played_at="2026-03-15 14:32",
    )
    assert m.match_id == "EUW1-123456"
    assert m.win is True
    assert m.kda == "8/2/5"
    assert m.kda_ratio == 6.5


def test_kda_ratio_zero_deaths():
    m = MatchResult(
        match_id="EUW1-999",
        champion="Lux",
        win=True,
        kills=5,
        deaths=0,
        assists=10,
        game_duration="25:00",
        game_mode="ARAM",
        played_at="2026-03-15 15:00",
    )
    assert m.kda_ratio == float("inf")
