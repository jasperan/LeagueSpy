"""Compatibility data helpers for the legacy demo surface."""

from __future__ import annotations

from src.daily_summary import group_by_player
from src.sample_data import (
    SAMPLE_SUMMONER,
    sample_animated_summary_matches,
    sample_match_details,
    sample_match_result,
    sample_summary_matches,
    sample_trend_matches as _sample_trend_matches,
    sample_weekly_rankings,
)


def sample_summoner():
    return SAMPLE_SUMMONER


def sample_match():
    return sample_match_result()


def sample_grouped_matches():
    return group_by_player(sample_summary_matches())


def sample_trend_matches(_player_name: str = "jasper"):
    return _sample_trend_matches()


def sample_weekly_players():
    return sample_weekly_rankings()


def sample_animated_grouped_matches():
    return group_by_player(sample_animated_summary_matches())
