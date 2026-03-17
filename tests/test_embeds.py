import discord
from src.embeds import build_match_announcement, build_match_embed
from src.models import MatchResult, SummonerConfig


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


def test_build_win_embed():
    summoner = _make_summoner()
    match = _make_match()
    embed = build_match_embed(summoner, match)
    assert isinstance(embed, discord.Embed)
    assert embed.colour == discord.Colour.green()
    assert "VICTORY" in embed.title


def test_build_loss_embed():
    summoner = _make_summoner()
    match = _make_match(win=False)
    embed = build_match_embed(summoner, match)
    assert embed.colour == discord.Colour.red()
    assert "DEFEAT" in embed.title


def test_embed_has_champion_thumbnail():
    summoner = _make_summoner()
    match = _make_match()
    embed = build_match_embed(summoner, match)
    assert embed.thumbnail is not None
    assert "Jinx" in embed.thumbnail.url


def test_embed_thumbnail_normalizes_champion_name():
    summoner = _make_summoner()
    match = _make_match(champion="Lee Sin")
    embed = build_match_embed(summoner, match)
    assert "LeeSin" in embed.thumbnail.url


def test_announcement_without_commentary():
    summoner = _make_summoner()
    match = _make_match()
    payload = build_match_announcement(summoner, match)
    assert "content" not in payload
    assert isinstance(payload["embed"], discord.Embed)


def test_announcement_with_commentary():
    summoner = _make_summoner()
    match = _make_match()
    payload = build_match_announcement(summoner, match, commentary="Menuda exhibicion.")
    assert payload["content"] == "Menuda exhibicion."
    assert isinstance(payload["embed"], discord.Embed)


def test_announcement_with_scoreboard_image():
    summoner = _make_summoner()
    match = _make_match()
    fake_png = b"\x89PNG fake image bytes"
    payload = build_match_announcement(summoner, match, scoreboard_image=fake_png)
    assert "file" in payload
    assert isinstance(payload["file"], discord.File)
    assert payload["embed"].image.url == "attachment://scoreboard.png"


def test_announcement_without_scoreboard_has_no_file():
    summoner = _make_summoner()
    match = _make_match()
    payload = build_match_announcement(summoner, match)
    assert "file" not in payload
