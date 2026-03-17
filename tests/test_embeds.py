import discord
from src.embeds import build_match_announcement
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


def test_win_announcement():
    payload = build_match_announcement(_make_summoner(), _make_match())
    embed = payload["embed"]
    assert embed.colour == discord.Colour.green()
    assert "VICTORY" in embed.title
    assert "jasper" in embed.title
    assert "Jinx" in embed.description
    assert "8/2/5" in embed.description


def test_loss_announcement():
    payload = build_match_announcement(_make_summoner(), _make_match(win=False))
    embed = payload["embed"]
    assert embed.colour == discord.Colour.red()
    assert "DEFEAT" in embed.title


def test_no_scoreboard_uses_thumbnail():
    payload = build_match_announcement(_make_summoner(), _make_match())
    embed = payload["embed"]
    assert embed.thumbnail is not None
    assert "Jinx" in embed.thumbnail.url
    assert "file" not in payload


def test_scoreboard_replaces_thumbnail():
    payload = build_match_announcement(
        _make_summoner(), _make_match(), scoreboard_image=b"\x89PNG fake",
    )
    embed = payload["embed"]
    assert embed.image.url == "attachment://scoreboard.png"
    assert embed.thumbnail.url is discord.utils.MISSING or embed.thumbnail.url is None
    assert isinstance(payload["file"], discord.File)


def test_commentary_included():
    payload = build_match_announcement(
        _make_summoner(), _make_match(), commentary="Nice game!",
    )
    assert payload["content"] == "Nice game!"


def test_no_commentary_no_content():
    payload = build_match_announcement(_make_summoner(), _make_match())
    assert "content" not in payload


def test_footer_shows_played_at():
    payload = build_match_announcement(_make_summoner(), _make_match())
    assert "2026-03-15 14:32" in payload["embed"].footer.text


def test_embed_links_to_profile():
    payload = build_match_announcement(_make_summoner(), _make_match())
    assert "leagueofgraphs.com" in payload["embed"].url
