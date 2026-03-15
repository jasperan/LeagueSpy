from dataclasses import dataclass


@dataclass
class SummonerConfig:
    player_name: str
    slug: str
    region: str

    @property
    def op_gg_url(self) -> str:
        return f"https://op.gg/lol/summoners/{self.region}/{self.slug}"


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

    @property
    def kda(self) -> str:
        return f"{self.kills}/{self.deaths}/{self.assists}"

    @property
    def kda_ratio(self) -> float:
        if self.deaths == 0:
            return float("inf")
        return round((self.kills + self.assists) / self.deaths, 2)
