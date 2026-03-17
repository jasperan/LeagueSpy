from src.models import SummonerConfig, MatchResult, MatchParticipant, MatchDetails


def test_summoner_config_creation():
    s = SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")
    assert s.player_name == "jasper"
    assert s.slug == "jasper-1971"
    assert s.region == "euw"
    assert s.profile_url == "https://www.leagueofgraphs.com/summoner/euw/jasper-1971"


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


def test_match_result_backward_compat_defaults():
    # New optional fields must not break existing construction.
    m = MatchResult(
        match_id="EUW1-000",
        champion="Thresh",
        win=False,
        kills=1,
        deaths=4,
        assists=12,
        game_duration="28:10",
        game_mode="Ranked Solo",
        played_at="2026-03-16 10:00",
    )
    assert m.match_url is None
    assert m.cs == 0
    assert m.gold == 0
    assert m.kill_participation == 0
    assert m.vision_score == 0
    assert m.details is None


def test_match_result_optional_fields():
    m = MatchResult(
        match_id="EUW1-111",
        champion="Jinx",
        win=True,
        kills=10,
        deaths=1,
        assists=6,
        game_duration="35:00",
        game_mode="Ranked Solo",
        played_at="2026-03-17 09:00",
        match_url="https://www.leagueofgraphs.com/match/euw/EUW1-111",
        cs=245,
        gold=18500,
        kill_participation=72,
        vision_score=31,
    )
    assert m.match_url == "https://www.leagueofgraphs.com/match/euw/EUW1-111"
    assert m.cs == 245
    assert m.gold == 18500
    assert m.kill_participation == 72
    assert m.vision_score == 31


# --- MatchParticipant tests ---

def _make_participant(kills=3, deaths=8, assists=7, gold=16318) -> MatchParticipant:
    return MatchParticipant(
        summoner_name="TestPlayer",
        rank="Gold II",
        champion="Yasuo",
        kills=kills,
        deaths=deaths,
        assists=assists,
        cs=180,
        gold=gold,
        kill_participation=55,
        vision_score=22,
    )


def test_match_participant_creation():
    p = _make_participant()
    assert p.summoner_name == "TestPlayer"
    assert p.rank == "Gold II"
    assert p.champion == "Yasuo"
    assert p.cs == 180
    assert p.kill_participation == 55
    assert p.vision_score == 22


def test_match_participant_kda():
    p = _make_participant(kills=3, deaths=8, assists=7)
    assert p.kda == "3/8/7"


def test_match_participant_kda_zero_deaths():
    p = _make_participant(kills=10, deaths=0, assists=5)
    assert p.kda == "10/0/5"


def test_match_participant_gold_display_thousands():
    p = _make_participant(gold=16318)
    assert p.gold_display == "16.3k"


def test_match_participant_gold_display_small():
    # Under 1000 — just show raw number as string.
    p = _make_participant(gold=850)
    assert p.gold_display == "850"


def test_match_participant_gold_display_exact_thousand():
    p = _make_participant(gold=10000)
    assert p.gold_display == "10.0k"


# --- MatchDetails tests ---

def _make_team(kills_list, deaths_list, assists_list):
    players = []
    for k, d, a in zip(kills_list, deaths_list, assists_list):
        players.append(MatchParticipant(
            summoner_name=f"P{k}",
            rank="Silver I",
            champion="Lux",
            kills=k,
            deaths=d,
            assists=a,
            cs=150,
            gold=12000,
            kill_participation=50,
            vision_score=20,
        ))
    return players


def test_match_details_creation():
    team1 = _make_team([5, 3, 8, 2, 1], [2, 4, 3, 5, 1], [10, 6, 4, 8, 3])
    team2 = _make_team([2, 4, 3, 5, 1], [5, 3, 8, 2, 1], [5, 7, 9, 3, 6])
    details = MatchDetails(
        team1_players=team1,
        team2_players=team2,
        team1_result="Victory",
        team2_result="Defeat",
        team1_bans=["Zed", "Yasuo", "Katarina", "Fizz", "LeBlanc"],
        team2_bans=["Jinx", "Thresh", "Lulu", "Soraka", "Janna"],
    )
    assert details.team1_result == "Victory"
    assert details.team2_result == "Defeat"
    assert len(details.team1_players) == 5
    assert len(details.team2_players) == 5
    assert details.team1_bans[0] == "Zed"
    assert details.team2_bans[-1] == "Janna"


def test_match_details_team1_kda():
    # team1: kills=[5,3,8,2,1]=19, deaths=[2,4,3,5,1]=15, assists=[10,6,4,8,3]=31
    team1 = _make_team([5, 3, 8, 2, 1], [2, 4, 3, 5, 1], [10, 6, 4, 8, 3])
    team2 = _make_team([1, 1, 1, 1, 1], [1, 1, 1, 1, 1], [1, 1, 1, 1, 1])
    details = MatchDetails(
        team1_players=team1,
        team2_players=team2,
        team1_result="Victory",
        team2_result="Defeat",
        team1_bans=[],
        team2_bans=[],
    )
    assert details.team1_kda == "19/15/31"


def test_match_details_team2_kda():
    # team2: kills=[2,4,3,5,1]=15, deaths=[5,3,8,2,1]=19, assists=[5,7,9,3,6]=30
    team1 = _make_team([1, 1, 1, 1, 1], [1, 1, 1, 1, 1], [1, 1, 1, 1, 1])
    team2 = _make_team([2, 4, 3, 5, 1], [5, 3, 8, 2, 1], [5, 7, 9, 3, 6])
    details = MatchDetails(
        team1_players=team1,
        team2_players=team2,
        team1_result="Defeat",
        team2_result="Victory",
        team1_bans=[],
        team2_bans=[],
    )
    assert details.team2_kda == "15/19/30"
