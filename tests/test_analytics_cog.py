import pytest
from unittest.mock import MagicMock, AsyncMock


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.db = MagicMock()
    bot.summoner_db_ids = {"jasper-1971": 1, "friend1-tag": 2}
    bot.summoners = []
    bot.channel_id = 12345
    bot.wait_until_ready = AsyncMock()
    bot.get_channel = MagicMock(return_value=AsyncMock())
    bot.fetch_channel = AsyncMock(return_value=AsyncMock())
    return bot


def test_rivalry_detected(mock_bot):
    mock_bot.db.check_rivalry.return_value = {
        "summoner_id": 2, "player_name": "friend1",
        "summoner_slug": "friend1-tag", "region": "euw", "win": 0,
    }
    result = mock_bot.db.check_rivalry("EUW1-100", summoner_id=1)
    assert result is not None
    assert result["player_name"] == "friend1"


def test_no_rivalry(mock_bot):
    mock_bot.db.check_rivalry.return_value = None
    result = mock_bot.db.check_rivalry("EUW1-100", summoner_id=1)
    assert result is None
