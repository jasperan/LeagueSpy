import discord
from src.embeds import build_match_announcement, build_match_embed, build_scoreboard_embed
from src.models import MatchDetails, MatchParticipant, MatchResult, SummonerConfig


def test_build_win_embed():
    summoner = SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")
    match = MatchResult(
        match_id="EUW1-123",
        champion="Jinx",
        win=True,
        kills=8,
        deaths=2,
        assists=5,
        game_duration="32:15",
        game_mode="Ranked Solo",
        played_at="2026-03-15 14:32",
    )
    embed = build_match_embed(summoner, match)
    assert isinstance(embed, discord.Embed)
    assert embed.colour == discord.Colour.green()
    assert "VICTORY" in embed.title


def test_build_loss_embed():
    summoner = SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")
    match = MatchResult(
        match_id="EUW1-456",
        champion="Lux",
        win=False,
        kills=2,
        deaths=7,
        assists=3,
        game_duration="28:10",
        game_mode="Normal",
        played_at="2026-03-15 15:00",
    )
    embed = build_match_embed(summoner, match)
    assert embed.colour == discord.Colour.red()
    assert "DEFEAT" in embed.title


def test_embed_has_champion_thumbnail():
    summoner = SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")
    match = MatchResult(
        match_id="EUW1-123",
        champion="Jinx",
        win=True,
        kills=8,
        deaths=2,
        assists=5,
        game_duration="32:15",
        game_mode="Ranked Solo",
        played_at="2026-03-15 14:32",
    )
    embed = build_match_embed(summoner, match)
    assert embed.thumbnail is not None
    assert "Jinx" in embed.thumbnail.url


def test_embed_thumbnail_normalizes_champion_name():
    summoner = SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")
    match = MatchResult(
        match_id="EUW1-789",
        champion="Lee Sin",
        win=False,
        kills=3,
        deaths=5,
        assists=7,
        game_duration="28:00",
        game_mode="Normal",
        played_at="2026-03-15 16:00",
    )
    embed = build_match_embed(summoner, match)
    assert "LeeSin" in embed.thumbnail.url


def test_build_match_announcement_without_commentary_uses_embed_only():
    summoner = SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")
    match = MatchResult(
        match_id="EUW1-123",
        champion="Jinx",
        win=True,
        kills=8,
        deaths=2,
        assists=5,
        game_duration="32:15",
        game_mode="Ranked Solo",
        played_at="2026-03-15 14:32",
    )

    payload = build_match_announcement(summoner, match)

    assert "content" not in payload
    assert isinstance(payload["embed"], discord.Embed)


def test_build_match_announcement_with_commentary_includes_content_and_embed():
    summoner = SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")
    match = MatchResult(
        match_id="EUW1-123",
        champion="Jinx",
        win=True,
        kills=8,
        deaths=2,
        assists=5,
        game_duration="32:15",
        game_mode="Ranked Solo",
        played_at="2026-03-15 14:32",
    )

    payload = build_match_announcement(
        summoner,
        match,
        commentary="Menuda exhibición, colega.",
    )

    assert payload["content"] == "Menuda exhibición, colega."
    assert isinstance(payload["embed"], discord.Embed)


def _make_summoner():
    return SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")


def _make_match(**overrides):
    defaults = dict(
        match_id="EUW1-123",
        champion="Jinx",
        win=True,
        kills=8,
        deaths=2,
        assists=5,
        game_duration="32:15",
        game_mode="Ranked Solo",
        played_at="2026-03-15 14:32",
    )
    defaults.update(overrides)
    return MatchResult(**defaults)


def _make_details():
    team1 = [
        MatchParticipant("Player1", "Gold II", "Jinx", 8, 2, 5, 200, 12000, 60, 30),
        MatchParticipant("Player2", "Plat IV", "Thresh", 1, 3, 12, 30, 8000, 45, 55),
        MatchParticipant("Player3", "Gold I", "Ahri", 7, 4, 6, 180, 13000, 50, 20),
        MatchParticipant("Player4", "Silver I", "Lee Sin", 5, 5, 8, 150, 11000, 55, 25),
        MatchParticipant("Player5", "Gold III", "Ornn", 2, 3, 10, 170, 10000, 40, 35),
    ]
    team2 = [
        MatchParticipant("Enemy1", "Plat III", "Zed", 6, 5, 4, 210, 14000, 55, 18),
        MatchParticipant("Enemy2", "Gold II", "Leona", 0, 6, 10, 25, 7000, 40, 60),
        MatchParticipant("Enemy3", "Plat I", "Syndra", 5, 4, 3, 190, 12500, 45, 22),
        MatchParticipant("Enemy4", "Gold IV", "Graves", 4, 4, 5, 160, 11500, 50, 28),
        MatchParticipant("Enemy5", "Silver II", "Sion", 2, 4, 8, 180, 9500, 35, 32),
    ]
    return MatchDetails(
        team1_players=team1,
        team2_players=team2,
        team1_result="Victory",
        team2_result="Defeat",
        team1_bans=["Yasuo", "Yone"],
        team2_bans=["Vayne", "Kaisa"],
    )


def test_embed_with_enhanced_stats():
    summoner = _make_summoner()
    match = _make_match(cs=352, gold=16300, kill_participation=68, vision_score=42)
    embed = build_match_embed(summoner, match)
    field_names = [f.name for f in embed.fields]
    assert "CS" in field_names
    assert "Gold" in field_names
    assert "Kill P. / Vision" in field_names
    # Verify values
    cs_field = next(f for f in embed.fields if f.name == "CS")
    assert cs_field.value == "352"
    gold_field = next(f for f in embed.fields if f.name == "Gold")
    assert gold_field.value == "16.3k"
    kp_field = next(f for f in embed.fields if f.name == "Kill P. / Vision")
    assert kp_field.value == "68% / 42"


def test_embed_without_enhanced_stats():
    summoner = _make_summoner()
    match = _make_match()  # cs=0, gold=0 by default
    embed = build_match_embed(summoner, match)
    field_names = [f.name for f in embed.fields]
    assert "CS" not in field_names
    assert "Gold" not in field_names
    assert "Kill P. / Vision" not in field_names


def test_scoreboard_embed_has_both_teams():
    details = _make_details()
    embed = build_scoreboard_embed(details)
    assert isinstance(embed, discord.Embed)
    assert embed.colour == discord.Colour.dark_grey()
    field_names = [f.name for f in embed.fields]
    # Should have team fields containing result strings
    assert any("Victory" in name for name in field_names)
    assert any("Defeat" in name for name in field_names)
    # Should have ban fields
    assert field_names.count("Bans") == 2


def test_announcement_with_details_uses_embeds_list():
    summoner = _make_summoner()
    details = _make_details()
    match = _make_match(details=details)
    payload = build_match_announcement(summoner, match)
    assert "embeds" in payload
    assert "embed" not in payload
    assert len(payload["embeds"]) == 2
    assert isinstance(payload["embeds"][0], discord.Embed)
    assert isinstance(payload["embeds"][1], discord.Embed)


def test_announcement_without_details_uses_embed_single():
    summoner = _make_summoner()
    match = _make_match()  # no details
    payload = build_match_announcement(summoner, match)
    assert "embed" in payload
    assert "embeds" not in payload
    assert isinstance(payload["embed"], discord.Embed)
