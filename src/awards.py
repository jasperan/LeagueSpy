"""Daily social awards computed from recorded match data."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class DailyAward:
    title: str
    player_name: str
    reason: str
    champion: str | None = None


def compute_daily_awards(matches: list[dict], *, max_awards: int = 5) -> list[DailyAward]:
    """Return deterministic daily awards from a flat list of match rows."""
    if not matches or max_awards <= 0:
        return []

    awards: list[DailyAward] = []

    mvp = max(matches, key=_mvp_score)
    awards.append(
        DailyAward(
            title="MVP",
            player_name=_player(mvp),
            champion=_champion(mvp),
            reason=(
                f"{_kda(mvp)} with {_num(mvp, 'kill_participation')}% kill participation "
                f"in a {_result(mvp)}"
            ),
        )
    )

    losses = [match for match in matches if not _won(match)]
    if losses:
        toughest = max(losses, key=lambda match: (_num(match, "deaths"), _num(match, "kills") + _num(match, "assists")))
        awards.append(
            DailyAward(
                title="Tilt Watch",
                player_name=_player(toughest),
                champion=_champion(toughest),
                reason=f"{_num(toughest, 'deaths')} deaths in a {_duration(toughest)} loss",
            )
        )

    wins = [match for match in matches if _won(match)]
    clean_games = [match for match in wins if _num(match, "deaths") <= 2]
    if clean_games:
        clean = max(clean_games, key=lambda match: (_num(match, "kills") + _num(match, "assists"), -_num(match, "deaths")))
        awards.append(
            DailyAward(
                title="Cleanest Game",
                player_name=_player(clean),
                champion=_champion(clean),
                reason=f"{_kda(clean)} with only {_num(clean, 'deaths')} death(s)",
            )
        )

    player_counts = Counter(_player(match) for match in matches)
    grinder, games = player_counts.most_common(1)[0]
    if games > 1:
        awards.append(
            DailyAward(
                title="Grinder",
                player_name=grinder,
                reason=f"{games} games logged in the last 24 hours",
            )
        )

    vision_matches = [match for match in matches if _num(match, "vision_score") > 0]
    if vision_matches:
        vision = max(vision_matches, key=lambda match: _num(match, "vision_score"))
        awards.append(
            DailyAward(
                title="Vision Lead",
                player_name=_player(vision),
                champion=_champion(vision),
                reason=f"{_num(vision, 'vision_score')} vision score",
            )
        )

    return awards[:max_awards]


def format_daily_awards(awards: list[DailyAward]) -> str:
    """Render awards as concise Discord markdown."""
    if not awards:
        return ""

    lines = ["**Daily Awards**"]
    for award in awards:
        target = award.player_name
        if award.champion:
            target = f"{target} on {award.champion}"
        lines.append(f"- **{award.title}:** {target} - {award.reason}")
    return "\n".join(lines)


def _mvp_score(match: dict) -> float:
    return (
        (_num(match, "kills") * 3)
        + (_num(match, "assists") * 2)
        + (_num(match, "kill_participation") / 5)
        + (12 if _won(match) else 0)
        - (_num(match, "deaths") * 2)
    )


def _num(match: dict, key: str) -> int:
    value = match.get(key, 0)
    if value is None:
        return 0
    return int(value)


def _won(match: dict) -> bool:
    return bool(match.get("win"))


def _player(match: dict) -> str:
    return str(match.get("player_name") or "unknown")


def _champion(match: dict) -> str:
    return str(match.get("champion") or "Unknown")


def _kda(match: dict) -> str:
    return f"{_num(match, 'kills')}/{_num(match, 'deaths')}/{_num(match, 'assists')}"


def _result(match: dict) -> str:
    return "win" if _won(match) else "loss"


def _duration(match: dict) -> str:
    return str(match.get("game_duration") or "unknown-duration")
