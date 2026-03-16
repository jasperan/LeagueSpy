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

    def close(self):
        self.conn.close()
