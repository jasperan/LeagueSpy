"""Bundled offline sample data for LeagueSpy walkthroughs and demos."""

from __future__ import annotations

from src.models import MatchDetails, MatchParticipant, MatchResult, SummonerConfig


SAMPLE_SUMMONER = SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")


def sample_match_result() -> MatchResult:
    return MatchResult(
        match_id="EUW1-9001",
        champion="Jinx",
        win=True,
        kills=14,
        deaths=2,
        assists=9,
        game_duration="31:42",
        game_mode="Ranked Solo",
        played_at="2026-04-02 21:16 UTC",
        cs=241,
        gold=16750,
        kill_participation=68,
        vision_score=19,
        match_url="https://www.leagueofgraphs.com/match/euw/EUW1-9001",
    )


def sample_match_details() -> MatchDetails:
    team1 = [
        _player("jasper#1971", "Emerald II", "Jinx", 14, 2, 9, 241, 16750, 68, 19),
        _player("ally#top", "Platinum I", "Gnar", 6, 4, 11, 201, 13200, 54, 16),
        _player("ally#jg", "Emerald IV", "Viego", 8, 5, 12, 173, 14100, 59, 24),
        _player("ally#mid", "Diamond IV", "Ahri", 9, 3, 10, 210, 15440, 63, 20),
        _player("ally#sup", "Platinum II", "Nautilus", 1, 6, 18, 41, 9500, 70, 41),
    ]
    team2 = [
        _player("enemy#top", "Emerald IV", "Aatrox", 3, 7, 4, 198, 11600, 42, 12),
        _player("enemy#jg", "Emerald III", "Lee Sin", 5, 8, 5, 162, 12150, 51, 21),
        _player("enemy#mid", "Diamond IV", "Yone", 7, 6, 3, 224, 13800, 49, 14),
        _player("enemy#adc", "Emerald II", "Kai'Sa", 6, 7, 4, 236, 14320, 52, 16),
        _player("enemy#sup", "Platinum I", "Rakan", 1, 9, 11, 36, 8700, 48, 35),
    ]
    return MatchDetails(
        team1_players=team1,
        team2_players=team2,
        team1_result="VICTORY",
        team2_result="DEFEAT",
        team1_bans=["Blitzcrank", "Thresh", "Draven", "Leona", "Zed"],
        team2_bans=["Vi", "Ahri", "Sejuani", "Sona", "Lux"],
    )


def sample_summary_matches() -> list[dict]:
    return [
        _summary_row("jasper", "jasper-1971", "Jinx", 1, 14, 2, 9, 241, 16750, 68, 19, "Ranked Solo", "31:42", "2026-04-02 21:16 UTC", "EUW1-9001"),
        _summary_row("jasper", "jasper-1971", "Lux", 0, 4, 7, 8, 168, 11940, 58, 28, "Ranked Solo", "29:15", "2026-04-02 18:42 UTC", "EUW1-9000"),
        _summary_row("jasper", "jasper-1971", "Jinx", 1, 11, 3, 10, 228, 15810, 61, 17, "Ranked Solo", "30:08", "2026-04-02 16:07 UTC", "EUW1-8997"),
        _summary_row("friend1", "friend1-tag", "Leona", 1, 2, 4, 18, 39, 9900, 72, 44, "Flex", "32:11", "2026-04-02 20:05 UTC", "EUW1-8999"),
        _summary_row("friend1", "friend1-tag", "Rell", 0, 1, 8, 11, 28, 8420, 66, 38, "Flex", "27:52", "2026-04-02 17:11 UTC", "EUW1-8995"),
    ]


def sample_trend_matches() -> list[dict]:
    return [
        _trend_row("Jinx", 1, 12, 2, 9, "31:42", "Ranked Solo", "2026-04-02 21:16 UTC", 241, 16750, 68, 19, "EUW1-9001"),
        _trend_row("Lux", 0, 4, 7, 8, "29:15", "Ranked Solo", "2026-04-02 18:42 UTC", 168, 11940, 58, 28, "EUW1-9000"),
        _trend_row("Jinx", 1, 11, 3, 10, "30:08", "Ranked Solo", "2026-04-02 16:07 UTC", 228, 15810, 61, 17, "EUW1-8997"),
        _trend_row("Caitlyn", 1, 9, 1, 7, "28:55", "Ranked Solo", "2026-04-01 22:05 UTC", 219, 15100, 57, 15, "EUW1-8994"),
        _trend_row("Ashe", 0, 5, 6, 11, "33:19", "Ranked Solo", "2026-04-01 19:40 UTC", 231, 14020, 64, 22, "EUW1-8991"),
        _trend_row("Jinx", 1, 15, 4, 8, "34:50", "Ranked Solo", "2026-04-01 17:22 UTC", 248, 17120, 69, 18, "EUW1-8989"),
    ]


def sample_weekly_rankings() -> list[dict]:
    return [
        {"player_name": "jasper", "games": 18, "wins": 12, "avg_kills": 9.2, "avg_deaths": 3.8, "avg_assists": 8.6, "top_champion": "Jinx"},
        {"player_name": "friend1", "games": 16, "wins": 9, "avg_kills": 3.1, "avg_deaths": 4.7, "avg_assists": 12.4, "top_champion": "Leona"},
        {"player_name": "grinder", "games": 22, "wins": 10, "avg_kills": 7.4, "avg_deaths": 5.9, "avg_assists": 6.3, "top_champion": "Lee Sin"},
    ]


def sample_animated_summary_matches() -> list[dict]:
    """Return 5-player sample data so build_summary_image emits an animated GIF."""
    return [
        *_summary_rows_for("jasper", "jasper-1971", [("Jinx", 1, 14, 2, 9), ("Lux", 0, 4, 7, 8)]),
        *_summary_rows_for("friend1", "friend1-tag", [("Leona", 1, 2, 4, 18), ("Rell", 0, 1, 8, 11)]),
        *_summary_rows_for("grinder", "grinder-4444", [("Lee Sin", 1, 9, 5, 7), ("Viego", 0, 5, 7, 6)]),
        *_summary_rows_for("tiltedtop", "tiltedtop-0001", [("Gnar", 0, 3, 8, 4), ("Ornn", 1, 4, 2, 13)]),
        *_summary_rows_for("midgod", "midgod-2222", [("Ahri", 1, 11, 3, 10), ("Orianna", 1, 8, 2, 12)]),
    ]


def _player(name: str, rank: str, champion: str, kills: int, deaths: int, assists: int, cs: int, gold: int, kp: int, vision: int) -> MatchParticipant:
    return MatchParticipant(
        summoner_name=name,
        rank=rank,
        champion=champion,
        kills=kills,
        deaths=deaths,
        assists=assists,
        cs=cs,
        gold=gold,
        kill_participation=kp,
        vision_score=vision,
    )


def _summary_row(player_name: str, slug: str, champion: str, win: int, kills: int, deaths: int, assists: int, cs: int, gold: int, kp: int, vision: int, game_mode: str, game_duration: str, played_at: str, match_id: str) -> dict:
    return {
        "player_name": player_name,
        "summoner_slug": slug,
        "region": "euw",
        "match_id": match_id,
        "champion": champion,
        "win": win,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "game_duration": game_duration,
        "game_mode": game_mode,
        "played_at": played_at,
        "cs": cs,
        "gold": gold,
        "kill_participation": kp,
        "vision_score": vision,
    }


def _trend_row(champion: str, win: int, kills: int, deaths: int, assists: int, game_duration: str, game_mode: str, played_at: str, cs: int, gold: int, kp: int, vision: int, match_id: str) -> dict:
    return {
        "match_id": match_id,
        "champion": champion,
        "win": win,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "game_duration": game_duration,
        "game_mode": game_mode,
        "played_at": played_at,
        "cs": cs,
        "gold": gold,
        "kill_participation": kp,
        "vision_score": vision,
    }


def _summary_rows_for(player_name: str, slug: str, rows: list[tuple[str, int, int, int, int]]) -> list[dict]:
    generated: list[dict] = []
    base_match_id = 7000 + sum(ord(ch) for ch in f"{player_name}:{slug}") % 1000
    for index, (champion, win, kills, deaths, assists) in enumerate(rows, start=1):
        generated.append(
            _summary_row(
                player_name,
                slug,
                champion,
                win,
                kills,
                deaths,
                assists,
                150 + (index * 12),
                9000 + (kills * 450),
                45 + (index * 6),
                12 + (index * 5),
                "Ranked Solo",
                f"2{7 + index}:1{index}",
                f"2026-04-0{index} 1{index}:00 UTC",
                f"EUW1-{base_match_id + index}",
            )
        )
    return generated
