import pytest
from unittest.mock import AsyncMock, MagicMock
from src.cogs.commands import SpyCog


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.db = MagicMock()
    bot.summoners = []
    bot.summoner_db_ids = {}
    bot.scraper = MagicMock()
    bot.config = {"scraping": {"region": "euw"}}
    bot.channel_id = 12345
    bot.wait_until_ready = AsyncMock()
    bot.tree = MagicMock()
    return bot


@pytest.fixture
def cog(mock_bot):
    return SpyCog(mock_bot)


def test_cog_has_spy_group(cog):
    assert hasattr(cog, "spy")


@pytest.mark.asyncio
async def test_add_summoner_success(cog, mock_bot):
    mock_bot.db.get_summoner_id_by_slug.return_value = None
    mock_bot.db.get_or_create_summoner.return_value = 42

    interaction = AsyncMock()
    interaction.response = AsyncMock()

    await cog._add_summoner.callback(cog, interaction, slug="new-player-123", player_name="newguy", region="euw")

    mock_bot.db.get_or_create_summoner.assert_called_once_with("newguy", "new-player-123", "euw")
    assert len(mock_bot.summoners) == 1
    interaction.response.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_add_summoner_already_tracked(cog, mock_bot):
    mock_bot.db.get_summoner_id_by_slug.return_value = 42

    interaction = AsyncMock()
    interaction.response = AsyncMock()

    await cog._add_summoner.callback(cog, interaction, slug="jasper-1971", player_name="jasper", region="euw")

    mock_bot.db.get_or_create_summoner.assert_not_called()


@pytest.mark.asyncio
async def test_remove_summoner_success(cog, mock_bot):
    from src.models import SummonerConfig
    s = SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")
    mock_bot.summoners = [s]
    mock_bot.summoner_db_ids = {"jasper-1971": 42}
    mock_bot.db.get_summoner_id_by_slug.return_value = 42

    interaction = AsyncMock()
    interaction.response = AsyncMock()

    await cog._remove_summoner.callback(cog, interaction, slug="jasper-1971")

    mock_bot.db.deactivate_summoner.assert_called_once_with(42)
    assert len(mock_bot.summoners) == 0


@pytest.mark.asyncio
async def test_remove_summoner_not_found(cog, mock_bot):
    mock_bot.db.get_summoner_id_by_slug.return_value = None

    interaction = AsyncMock()
    interaction.response = AsyncMock()

    await cog._remove_summoner.callback(cog, interaction, slug="nonexistent")

    mock_bot.db.deactivate_summoner.assert_not_called()


@pytest.mark.asyncio
async def test_trends_player_not_found(cog, mock_bot):
    mock_bot.db.get_all_summoner_ids_for_player.return_value = []

    interaction = AsyncMock()
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()

    await cog._trends.callback(cog, interaction, player="unknown")

    interaction.followup.send.assert_called_once()
    call_kwargs = interaction.followup.send.call_args
    assert "No conozco" in str(call_kwargs)


@pytest.mark.asyncio
async def test_trends_no_matches(cog, mock_bot):
    mock_bot.db.get_all_summoner_ids_for_player.return_value = [42]
    mock_bot.db.get_recent_matches_extended.return_value = []

    interaction = AsyncMock()
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()

    await cog._trends.callback(cog, interaction, player="jasper")

    interaction.followup.send.assert_called_once()
    call_kwargs = interaction.followup.send.call_args
    assert "no tiene partidas" in str(call_kwargs)


@pytest.mark.asyncio
async def test_health_command_reports_runtime_snapshot(cog, mock_bot):
    mock_bot.features = {"analytics": True, "slash_commands": True}
    mock_bot.llm_config = {"model": "qwen3.5:9b"}
    mock_bot.db.ping.return_value = True
    mock_bot.scraper._browser = object()

    interaction = AsyncMock()
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()

    await cog._health.callback(cog, interaction)

    interaction.followup.send.assert_called_once()
    embed = interaction.followup.send.call_args.kwargs["embed"]
    field_names = [field.name for field in embed.fields]
    assert "Database" in field_names
    assert "Browser" in field_names
    assert "LLM" in field_names


@pytest.mark.asyncio
async def test_help_command_mentions_health(cog):
    interaction = AsyncMock()
    interaction.response = AsyncMock()

    await cog._help.callback(cog, interaction)

    interaction.response.send_message.assert_called_once()
    embed = interaction.response.send_message.call_args.kwargs["embed"]
    assert any(field.name == "/spy health" for field in embed.fields)
