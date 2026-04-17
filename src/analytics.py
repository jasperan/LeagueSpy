"""Analytics computations for LeagueSpy."""

from src.commentary import parse_duration_minutes as _parse_duration_minutes


def compute_tilt_score(streak: int, recent_matches: list[dict]) -> int:
    """Compute a tilt score from 0 (zen) to 100 (keyboard-through-monitor)."""
    if not recent_matches or streak >= 0:
        return 0

    streak_factor = min(40, abs(streak) * 8)

    n = len(recent_matches)
    if n >= 2:
        def avg_kda(matches):
            total_ka = sum(m["kills"] + m["assists"] for m in matches)
            total_d = sum(m["deaths"] for m in matches) or 1
            return total_ka / total_d
        mid = n // 2
        older_kda = avg_kda(recent_matches[mid:])
        newer_kda = avg_kda(recent_matches[:mid])
        decay = max(0, older_kda - newer_kda)
        kda_decay_factor = min(25, int(decay * 8))
    else:
        kda_decay_factor = 0

    avg_deaths = sum(m["deaths"] for m in recent_matches) / n
    death_factor = min(20, max(0, int((avg_deaths - 4) * 5)))

    short_games = sum(
        1 for m in recent_matches
        if _parse_duration_minutes(m.get("game_duration", "30min 0s")) < 20
    )
    ff_ratio = short_games / n
    ff_factor = min(15, int(ff_ratio * 25))

    total = streak_factor + kda_decay_factor + death_factor + ff_factor
    return max(0, min(100, total))
