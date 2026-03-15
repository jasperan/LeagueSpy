import discord
from src.embeds import build_match_embed
from src.models import MatchResult, SummonerConfig


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
