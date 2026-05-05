from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from src.match_actions import (
    ACTION_TIMEOUT_SECONDS,
    MatchActionView,
    describe_match_actions,
)
from src.models import MatchResult, SummonerConfig


def _make_summoner():
    return SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")


def _make_match(**overrides):
    defaults = dict(
        match_id="EUW1-123",
        champion="Jinx",
        win=False,
        kills=2,
        deaths=9,
        assists=5,
        game_duration="32:15",
        game_mode="Ranked Solo",
        played_at="2026-03-15 14:32",
        cs=180,
        gold=9200,
        kill_participation=42,
        vision_score=18,
    )
    defaults.update(overrides)
    return MatchResult(**defaults)


def _make_bot():
    bot = MagicMock()
    bot.get_cog.return_value = None
    bot.db = MagicMock()
    return bot


def _make_interaction():
    interaction = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def test_match_action_view_has_expected_controls():
    view = MatchActionView(_make_bot(), _make_summoner(), _make_match(), db_id=42)

    assert view.timeout == ACTION_TIMEOUT_SECONDS
    assert [child.label for child in view.children] == ["Ask", "Roast", "Analyze", "Trends", "Profile"]
    assert view.profile_button.style is discord.ButtonStyle.link
    assert view.profile_button.url.endswith("/euw/jasper-1971")
    assert view.ask_button.custom_id.startswith("leaguespy:match:ask:EUW1-123")


def test_describe_match_actions_is_showcase_friendly():
    actions = describe_match_actions(_make_summoner(), _make_match())

    assert [action["label"] for action in actions] == ["Ask", "Roast", "Analyze", "Trends", "Profile"]
    assert actions[-1]["kind"] == "link"
    assert "url" in actions[-1]


@pytest.mark.asyncio
async def test_ask_button_falls_back_when_ask_cog_is_unavailable():
    view = MatchActionView(_make_bot(), _make_summoner(), _make_match())
    interaction = _make_interaction()

    await view.ask_button.callback(interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    interaction.followup.send.assert_awaited_once()
    args, kwargs = interaction.followup.send.await_args
    assert "sistema de preguntas no esta activo" in args[0]
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_roast_button_uses_deterministic_fallback_without_roast_cog():
    view = MatchActionView(_make_bot(), _make_summoner(), _make_match())
    interaction = _make_interaction()

    await view.roast_button.callback(interaction)

    args, kwargs = interaction.followup.send.await_args
    assert "cementerio" in args[0]
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_analyze_button_falls_back_to_registered_match_data():
    view = MatchActionView(_make_bot(), _make_summoner(), _make_match())
    interaction = _make_interaction()

    await view.analyze_button.callback(interaction)

    _, kwargs = interaction.followup.send.await_args
    embed = kwargs["embed"]
    assert "Analisis" in embed.title
    assert "lectura rapida" in embed.description
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_trends_button_reports_insufficient_data():
    bot = _make_bot()
    bot.db.get_all_summoner_ids_for_player.return_value = [42]
    bot.db.get_recent_matches_extended.return_value = []
    view = MatchActionView(bot, _make_summoner(), _make_match())
    interaction = _make_interaction()

    await view.trends_button.callback(interaction)

    args, kwargs = interaction.followup.send.await_args
    assert "suficientes partidas" in args[0]
    assert kwargs["ephemeral"] is True
