from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote


@dataclass
class MatchParticipant:
    summoner_name: str
    rank: str
    champion: str
    kills: int
    deaths: int
    assists: int
    cs: int
    gold: int
    kill_participation: int
    vision_score: int

    @property
    def kda(self) -> str:
        return f"{self.kills}/{self.deaths}/{self.assists}"

    @property
    def gold_display(self) -> str:
        if self.gold >= 1000:
            return f"{self.gold / 1000:.1f}k"
        return str(self.gold)


@dataclass
class MatchDetails:
    team1_players: list[MatchParticipant]
    team2_players: list[MatchParticipant]
    team1_result: str
    team2_result: str
    team1_bans: list[str]
    team2_bans: list[str]

    @property
    def team1_kda(self) -> str:
        k = sum(p.kills for p in self.team1_players)
        d = sum(p.deaths for p in self.team1_players)
        a = sum(p.assists for p in self.team1_players)
        return f"{k}/{d}/{a}"

    @property
    def team2_kda(self) -> str:
        k = sum(p.kills for p in self.team2_players)
        d = sum(p.deaths for p in self.team2_players)
        a = sum(p.assists for p in self.team2_players)
        return f"{k}/{d}/{a}"


def slug_to_riot_name(slug: str) -> str:
    """Reconstruct the lowercase, space-stripped ``name#tag`` from a LoG slug.

    leagueofgraphs encodes a Riot name+tag as ``name-tag`` in URL slugs, with the
    final ``-`` standing in for ``#``. This is the single source of truth for that
    invariant; compare against a player's display name with
    :func:`slug_matches_name`.
    """
    parts = slug.rsplit("-", 1)
    name = (parts[0] + "#" + parts[1]) if len(parts) == 2 else slug
    return name.lower().replace(" ", "")


def slug_matches_name(slug: str, summoner_name: str) -> bool:
    """Return True if ``summoner_name`` corresponds to ``slug``."""
    return summoner_name.lower().replace(" ", "") == slug_to_riot_name(slug)


@dataclass
class SummonerConfig:
    player_name: str
    slug: str
    region: str

    @property
    def profile_url(self) -> str:
        return f"https://www.leagueofgraphs.com/summoner/{self.region}/{quote(self.slug, safe='-')}"

    def matches_name(self, summoner_name: str) -> bool:
        """Return True if ``summoner_name`` corresponds to this summoner's slug."""
        return slug_matches_name(self.slug, summoner_name)


@dataclass
class MatchResult:
    match_id: str
    champion: str
    win: bool
    kills: int
    deaths: int
    assists: int
    game_duration: str
    game_mode: str
    played_at: str
    match_url: str | None = None
    cs: int = 0
    gold: int = 0
    kill_participation: int = 0
    vision_score: int = 0
    details: MatchDetails | None = field(default=None)

    @property
    def kda(self) -> str:
        return f"{self.kills}/{self.deaths}/{self.assists}"

    @property
    def kda_ratio(self) -> float:
        if self.deaths == 0:
            return float("inf")
        return round((self.kills + self.assists) / self.deaths, 2)
