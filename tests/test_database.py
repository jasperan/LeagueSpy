import pytest
from unittest.mock import MagicMock, patch
from src.database import Database
from src.models import MatchResult


@pytest.fixture
def mock_db():
    with patch("src.database.oracledb") as mock_ora:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_ora.connect.return_value = mock_conn
        db = Database(user="test", password="test", dsn="localhost:1521/TEST")
        db.conn = mock_conn
        yield db, mock_cursor


def test_get_or_create_summoner_existing(mock_db):
    db, cursor = mock_db
    cursor.fetchone.return_value = (42,)
    result = db.get_or_create_summoner("jasper", "jasper-1971", "euw")
    assert result == 42


def test_get_or_create_summoner_new(mock_db):
    db, cursor = mock_db
    cursor.fetchone.side_effect = [None, (1,)]
    cursor.var.return_value = MagicMock(getvalue=MagicMock(return_value=[1]))
    result = db.get_or_create_summoner("jasper", "jasper-1971", "euw")
    assert result is not None


def test_is_match_known_true(mock_db):
    db, cursor = mock_db
    cursor.fetchone.return_value = (1,)
    assert db.is_match_known(1, "EUW1-123") is True


def test_is_match_known_false(mock_db):
    db, cursor = mock_db
    cursor.fetchone.return_value = None
    assert db.is_match_known(1, "EUW1-123") is False


def test_insert_match(mock_db):
    db, cursor = mock_db
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
    db.insert_match(1, match)
    cursor.execute.assert_called_once()
