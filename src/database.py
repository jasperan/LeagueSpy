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
                    game_duration, game_mode, played_at, announced,
                    cs, gold, kill_participation, vision_score, match_url)
                   VALUES (:sid, :mid, :champ, :win, :kills, :deaths, :assists,
                           :dur, :gmode, :played, 0,
                           :cs, :gold, :kp, :vs, :murl)""",
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
                    "cs": match.cs,
                    "gold": match.gold,
                    "kp": match.kill_participation,
                    "vs": match.vision_score,
                    "murl": match.match_url,
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
                          m.assists, m.game_duration, m.game_mode, m.played_at,
                          m.cs, m.gold, m.kill_participation, m.vision_score
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
                "cs", "gold", "kill_participation", "vision_score",
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
                "avg_kills": float(row[3] or 0), "avg_deaths": float(row[4] or 0), "avg_assists": float(row[5] or 0),
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

    def get_leaderboard(self, min_games: int = 10) -> list[dict]:
        """Return leaderboard sorted by win rate, filtered by minimum games."""
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT s.id, s.player_name, COUNT(*) as games, SUM(m.win) as wins,
                          ROUND(AVG(m.kills), 1), ROUND(AVG(m.deaths), 1),
                          ROUND(AVG(m.assists), 1), s.current_streak
                   FROM matches m JOIN summoners s ON s.id = m.summoner_id
                   GROUP BY s.id, s.player_name, s.current_streak
                   HAVING COUNT(*) >= :min_g
                   ORDER BY SUM(m.win) / COUNT(*) DESC""",
                {"min_g": min_games},
            )
            cols = ["summoner_id", "player_name", "total_games", "wins",
                    "avg_kills", "avg_deaths", "avg_assists", "current_streak"]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_weekly_stats(self) -> list[dict]:
        """Return per-player stats for the last 7 days."""
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT s.id, s.player_name, s.summoner_slug,
                          COUNT(*) as games, SUM(m.win) as wins,
                          ROUND(AVG(m.kills), 1), ROUND(AVG(m.deaths), 1),
                          ROUND(AVG(m.assists), 1),
                          (SELECT champion FROM matches m2
                           WHERE m2.summoner_id = s.id
                             AND m2.created_at >= SYSTIMESTAMP - INTERVAL '7' DAY
                           GROUP BY champion ORDER BY COUNT(*) DESC
                           FETCH FIRST 1 ROWS ONLY) as top_champ
                   FROM matches m JOIN summoners s ON s.id = m.summoner_id
                   WHERE m.created_at >= SYSTIMESTAMP - INTERVAL '7' DAY
                   GROUP BY s.id, s.player_name, s.summoner_slug
                   ORDER BY SUM(m.win) / COUNT(*) DESC""",
            )
            cols = ["summoner_id", "player_name", "summoner_slug", "games", "wins",
                    "avg_kills", "avg_deaths", "avg_assists", "top_champion"]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_summoner_id_by_slug(self, slug: str) -> int | None:
        """Look up a summoner ID by their slug."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT id FROM summoners WHERE summoner_slug = :slug", {"slug": slug})
            row = cur.fetchone()
            return row[0] if row else None

    def get_all_summoner_ids_for_player(self, player_name: str) -> list[int]:
        """Return all summoner IDs belonging to a player (main + smurfs)."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT id FROM summoners WHERE player_name = :name", {"name": player_name})
            return [row[0] for row in cur.fetchall()]

    def deactivate_summoner(self, summoner_id: int) -> None:
        """Remove a summoner from tracking."""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM summoners WHERE id = :sid", {"sid": summoner_id})
            self.conn.commit()

    def truncate_live_games(self) -> None:
        """Clear all live game records."""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM live_games")
            self.conn.commit()

    def is_live_game(self, summoner_id: int) -> bool:
        """Check if a summoner is currently in a live game."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM live_games WHERE summoner_id = :sid", {"sid": summoner_id})
            return cur.fetchone() is not None

    def set_live_game(self, summoner_id: int, champion: str | None, game_mode: str | None) -> None:
        """Record that a summoner is in a live game."""
        with self.conn.cursor() as cur:
            cur.execute(
                """MERGE INTO live_games lg USING (SELECT :sid as sid FROM dual) src
                   ON (lg.summoner_id = src.sid)
                   WHEN NOT MATCHED THEN INSERT (summoner_id, champion, game_mode) VALUES (:sid, :champ, :gm)""",
                {"sid": summoner_id, "champ": champion, "gm": game_mode},
            )
            self.conn.commit()

    def clear_live_game(self, summoner_id: int) -> None:
        """Remove the live game record for a summoner."""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM live_games WHERE summoner_id = :sid", {"sid": summoner_id})
            self.conn.commit()

    def close(self):
        self.conn.close()
