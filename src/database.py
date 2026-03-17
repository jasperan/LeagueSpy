import logging
import oracledb
from src.models import MatchResult

logger = logging.getLogger("leaguespy.database")


class Database:
    def __init__(self, user: str, password: str, dsn: str):
        self.conn = oracledb.connect(user=user, password=password, dsn=dsn)
        logger.info("Connected to Oracle DB at %s", dsn)

    def get_or_create_summoner(self, player_name: str, slug: str, region: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM summoners WHERE summoner_slug = :slug AND region = :region",
                {"slug": slug, "region": region},
            )
            row = cur.fetchone()
            if row:
                return row[0]
            id_var = cur.var(oracledb.NUMBER)
            cur.execute(
                """INSERT INTO summoners (player_name, summoner_slug, region)
                   VALUES (:name, :slug, :region)
                   RETURNING id INTO :id""",
                {"name": player_name, "slug": slug, "region": region, "id": id_var},
            )
            self.conn.commit()
            return int(id_var.getvalue()[0])

    def is_match_known(self, summoner_id: int, match_id: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM matches WHERE summoner_id = :sid AND match_id = :mid",
                {"sid": summoner_id, "mid": match_id},
            )
            return cur.fetchone() is not None

    def insert_match(self, summoner_id: int, match: MatchResult) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO matches
                   (summoner_id, match_id, champion, win, kills, deaths, assists,
                    game_duration, game_mode, played_at, announced)
                   VALUES (:sid, :mid, :champ, :win, :kills, :deaths, :assists,
                           :dur, :gmode, :played, 0)""",
                {
                    "sid": summoner_id,
                    "mid": match.match_id,
                    "champ": match.champion,
                    "win": 1 if match.win else 0,
                    "kills": match.kills,
                    "deaths": match.deaths,
                    "assists": match.assists,
                    "dur": match.game_duration,
                    "gmode": match.game_mode,
                    "played": match.played_at,
                },
            )
            self.conn.commit()

    def mark_announced(self, summoner_id: int, match_id: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE matches SET announced = 1 WHERE summoner_id = :sid AND match_id = :mid",
                {"sid": summoner_id, "mid": match_id},
            )
            self.conn.commit()

    def get_matches_since(self, since_timestamp: str) -> list[dict]:
        """Return all matches inserted after *since_timestamp*.

        Parameters
        ----------
        since_timestamp:
            Format ``"YYYY-MM-DD HH24:MI:SS"`` (Oracle TO_TIMESTAMP format).
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT s.id, s.player_name, s.summoner_slug, s.region,
                          m.match_id, m.champion, m.win, m.kills, m.deaths,
                          m.assists, m.game_duration, m.game_mode, m.played_at
                   FROM matches m
                   JOIN summoners s ON s.id = m.summoner_id
                   WHERE m.created_at >= TO_TIMESTAMP(:ts, 'YYYY-MM-DD HH24:MI:SS')
                   ORDER BY s.player_name, m.created_at""",
                {"ts": since_timestamp},
            )
            columns = [
                "summoner_id", "player_name", "summoner_slug", "region",
                "match_id", "champion", "win", "kills", "deaths",
                "assists", "game_duration", "game_mode", "played_at",
            ]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def update_streak(self, summoner_id: int, win: bool) -> int:
        """Update streak counters after a match. Returns the new current_streak."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT current_streak FROM summoners WHERE id = :sid",
                {"sid": summoner_id},
            )
            row = cur.fetchone()
            current = row[0] if row else 0

            if win:
                new_streak = current + 1 if current > 0 else 1
            else:
                new_streak = current - 1 if current < 0 else -1

            abs_streak = abs(new_streak)
            if win:
                cur.execute(
                    """UPDATE summoners
                       SET current_streak = :streak,
                           longest_win_streak = GREATEST(longest_win_streak, :abs)
                       WHERE id = :sid""",
                    {"streak": new_streak, "abs": abs_streak, "sid": summoner_id},
                )
            else:
                cur.execute(
                    """UPDATE summoners
                       SET current_streak = :streak,
                           longest_loss_streak = GREATEST(longest_loss_streak, :abs)
                       WHERE id = :sid""",
                    {"streak": new_streak, "abs": abs_streak, "sid": summoner_id},
                )
            self.conn.commit()
            return new_streak

    def get_streak(self, summoner_id: int) -> tuple[int, int, int]:
        """Return (current_streak, longest_win_streak, longest_loss_streak)."""
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT current_streak, longest_win_streak, longest_loss_streak
                   FROM summoners WHERE id = :sid""",
                {"sid": summoner_id},
            )
            row = cur.fetchone()
            return (row[0], row[1], row[2]) if row else (0, 0, 0)

    def get_player_stats(self, summoner_id: int) -> dict:
        """Return aggregate stats for a summoner."""
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*), SUM(win), COUNT(*) - SUM(win),
                          ROUND(AVG(kills), 1), ROUND(AVG(deaths), 1), ROUND(AVG(assists), 1)
                   FROM matches WHERE summoner_id = :sid""",
                {"sid": summoner_id},
            )
            row = cur.fetchone()
            if not row or row[0] is None or row[0] == 0:
                return {"total_games": 0, "wins": 0, "losses": 0,
                        "avg_kills": 0, "avg_deaths": 0, "avg_assists": 0}
            return {
                "total_games": int(row[0]), "wins": int(row[1]), "losses": int(row[2]),
                "avg_kills": float(row[3]), "avg_deaths": float(row[4]), "avg_assists": float(row[5]),
            }

    def get_champion_stats(self, summoner_id: int, limit: int = 10) -> list[dict]:
        """Return per-champion stats sorted by games played."""
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT champion, COUNT(*) as games, SUM(win) as wins,
                          ROUND(AVG(kills), 1), ROUND(AVG(deaths), 1), ROUND(AVG(assists), 1)
                   FROM matches WHERE summoner_id = :sid
                   GROUP BY champion ORDER BY games DESC
                   FETCH FIRST :lim ROWS ONLY""",
                {"sid": summoner_id, "lim": limit},
            )
            cols = ["champion", "games", "wins", "avg_kills", "avg_deaths", "avg_assists"]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_recent_matches(self, summoner_id: int, limit: int = 10) -> list[dict]:
        """Return the N most recent matches for a summoner."""
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT match_id, champion, win, kills, deaths, assists,
                          game_duration, game_mode, played_at
                   FROM matches WHERE summoner_id = :sid
                   ORDER BY created_at DESC
                   FETCH FIRST :lim ROWS ONLY""",
                {"sid": summoner_id, "lim": limit},
            )
            cols = ["match_id", "champion", "win", "kills", "deaths", "assists",
                    "game_duration", "game_mode", "played_at"]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def check_rivalry(self, match_id: str, summoner_id: int) -> dict | None:
        """Check if another tracked summoner was in this match."""
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT s.id, s.player_name, s.summoner_slug, s.region, m.win
                   FROM matches m JOIN summoners s ON s.id = m.summoner_id
                   WHERE m.match_id = :mid AND m.summoner_id != :sid
                   FETCH FIRST 1 ROWS ONLY""",
                {"mid": match_id, "sid": summoner_id},
            )
            row = cur.fetchone()
            if not row:
                return None
            return {"summoner_id": row[0], "player_name": row[1],
                    "summoner_slug": row[2], "region": row[3], "win": row[4]}

    def get_h2h_record(self, summoner_id_a: int, summoner_id_b: int) -> list[dict]:
        """Return all matches where both summoners participated."""
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT ma.match_id, ma.win as a_win, mb.win as b_win,
                          ma.champion as a_champ, mb.champion as b_champ
                   FROM matches ma JOIN matches mb ON ma.match_id = mb.match_id
                   WHERE ma.summoner_id = :a AND mb.summoner_id = :b
                   ORDER BY ma.created_at DESC""",
                {"a": summoner_id_a, "b": summoner_id_b},
            )
            cols = ["match_id", "a_win", "b_win", "a_champ", "b_champ"]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def store_roast(self, summoner_id: int, match_id: str, roast_text: str, trigger_type: str) -> None:
        """Insert a roast into history."""
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO roast_history (summoner_id, match_id, roast_text, trigger_type)
                   VALUES (:sid, :mid, :txt, :ttype)""",
                {"sid": summoner_id, "mid": match_id, "txt": roast_text, "ttype": trigger_type},
            )
            self.conn.commit()

    def get_recent_roasts(self, summoner_id: int, limit: int = 5) -> list[str]:
        """Return the most recent roast texts for a summoner."""
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT roast_text FROM roast_history WHERE summoner_id = :sid
                   ORDER BY created_at DESC FETCH FIRST :lim ROWS ONLY""",
                {"sid": summoner_id, "lim": limit},
            )
            return [row[0] for row in cur.fetchall()]

    def close(self):
        self.conn.close()
