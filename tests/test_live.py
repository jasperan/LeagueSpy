import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.cogs.live import LiveCog
from src.models import SummonerConfig


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.db = MagicMock()
    bot.scraper = MagicMock()
    bot.summoners = []
    bot.summoner_db_ids = {}
    bot.channel_id = 12345
    bot.config = {"scraping": {"live_check_minutes": 2}}
    bot.wait_until_ready = AsyncMock()
    bot.get_channel = MagicMock(return_value=AsyncMock())
    bot.fetch_channel = AsyncMock(return_value=AsyncMock())
    return bot


def test_live_cog_has_check_loop():
    assert hasattr(LiveCog, "live_check")


@pytest.mark.asyncio
async def test_detects_new_game(mock_bot):
    s = SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")
    mock_bot.summoners = [s]
    mock_bot.summoner_db_ids = {"jasper-1971": 1}
    mock_bot.scraper.check_in_game = AsyncMock(return_value={"in_game": True, "champion": "Yasuo"})
    mock_bot.db.is_live_game.return_value = False

    with patch.object(LiveCog, '__init__', lambda self, bot: None):
        cog = LiveCog.__new__(LiveCog)
        cog.bot = mock_bot

    channel = AsyncMock()
    mock_bot.get_channel.return_value = channel

    await cog._check_summoner(s, 1)

    mock_bot.db.set_live_game.assert_called_once()
    channel.send.assert_called_once()


@pytest.mark.asyncio
async def test_no_alert_if_already_live(mock_bot):
    s = SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")
    mock_bot.scraper.check_in_game = AsyncMock(return_value={"in_game": True, "champion": "Yasuo"})
    mock_bot.db.is_live_game.return_value = True

    with patch.object(LiveCog, '__init__', lambda self, bot: None):
        cog = LiveCog.__new__(LiveCog)
        cog.bot = mock_bot

    channel = AsyncMock()
    mock_bot.get_channel.return_value = channel

    await cog._check_summoner(s, 1)

    mock_bot.db.set_live_game.assert_not_called()
    channel.send.assert_not_called()


@pytest.mark.asyncio
async def test_clears_live_when_game_ends(mock_bot):
    s = SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")
    mock_bot.scraper.check_in_game = AsyncMock(return_value={"in_game": False, "champion": None})
    mock_bot.db.is_live_game.return_value = True

    with patch.object(LiveCog, '__init__', lambda self, bot: None):
        cog = LiveCog.__new__(LiveCog)
        cog.bot = mock_bot

    await cog._check_summoner(s, 1)

    mock_bot.db.clear_live_game.assert_called_once_with(1)
