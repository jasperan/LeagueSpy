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


def test_get_matches_since(mock_db):
    db, cursor = mock_db
    cursor.fetchall.return_value = [
        (1, "jasper", "jasper-1971", "euw", "EUW1-100", "Jinx", 1, 8, 2, 5, "32:15", "Ranked Solo", "2026-03-16 10:00 UTC"),
        (1, "jasper", "jasper-1971", "euw", "EUW1-101", "Lux", 0, 2, 7, 3, "28:10", "Normal", "2026-03-16 11:00 UTC"),
    ]
    results = db.get_matches_since("2026-03-16 08:00:00")
    cursor.execute.assert_called_once()
    assert len(results) == 2
    assert results[0]["player_name"] == "jasper"
    assert results[0]["champion"] == "Jinx"
    assert results[0]["win"] == 1
    assert results[1]["win"] == 0


def test_update_streak_after_win(mock_db):
    db, cursor = mock_db
    cursor.fetchone.return_value = (0,)
    db.update_streak(1, win=True)
    assert cursor.execute.call_count == 2


def test_update_streak_after_loss(mock_db):
    db, cursor = mock_db
    cursor.fetchone.return_value = (0,)
    db.update_streak(1, win=False)
    assert cursor.execute.call_count == 2


def test_get_streak(mock_db):
    db, cursor = mock_db
    cursor.fetchone.return_value = (-3, 5, 4)
    streak, longest_w, longest_l = db.get_streak(1)
    assert streak == -3
    assert longest_w == 5
    assert longest_l == 4


def test_get_player_stats(mock_db):
    db, cursor = mock_db
    cursor.fetchone.return_value = (50, 30, 20, 6.5, 3.2, 8.1)
    stats = db.get_player_stats(1)
    assert stats["total_games"] == 50
    assert stats["wins"] == 30


def test_get_player_stats_no_matches(mock_db):
    db, cursor = mock_db
    cursor.fetchone.return_value = None
    stats = db.get_player_stats(1)
    assert stats["total_games"] == 0


def test_get_champion_stats(mock_db):
    db, cursor = mock_db
    cursor.fetchall.return_value = [
        ("Jinx", 20, 14, 7.2, 2.1, 6.5),
        ("Lux", 10, 5, 3.1, 4.0, 8.2),
    ]
    result = db.get_champion_stats(1)
    assert len(result) == 2
    assert result[0]["champion"] == "Jinx"


def test_get_recent_matches(mock_db):
    db, cursor = mock_db
    cursor.fetchall.return_value = [
        ("EUW1-100", "Jinx", 1, 8, 2, 5, "32min 15s", "Ranked", "2026-03-16 10:00 UTC"),
    ]
    result = db.get_recent_matches(1, limit=5)
    assert len(result) == 1
    assert result[0]["match_id"] == "EUW1-100"
