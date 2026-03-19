#!/usr/bin/env python3
"""Generate test summary images for before/after comparison."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.daily_summary import group_by_player, build_summary_image


def make_test_matches():
    """Create sample match data mimicking DB rows."""
    return [
        # Player 1: jasperan - 3 games, 2W 1L
        {"player_name": "jasperan", "champion": "Jinx", "win": True,
         "kills": 8, "deaths": 2, "assists": 12, "cs": 312, "gold": 16300,
         "kill_participation": 68, "vision_score": 42},
        {"player_name": "jasperan", "champion": "Kai'Sa", "win": True,
         "kills": 5, "deaths": 3, "assists": 9, "cs": 289, "gold": 14800,
         "kill_participation": 52, "vision_score": 28},
        {"player_name": "jasperan", "champion": "Jinx", "win": False,
         "kills": 3, "deaths": 7, "assists": 4, "cs": 198, "gold": 10200,
         "kill_participation": 35, "vision_score": 18},
        # Player 2: ShadowMid - 4 games, 1W 3L
        {"player_name": "ShadowMid", "champion": "Thresh", "win": False,
         "kills": 1, "deaths": 5, "assists": 8, "cs": 28, "gold": 7200,
         "kill_participation": 55, "vision_score": 72},
        {"player_name": "ShadowMid", "champion": "Nautilus", "win": False,
         "kills": 2, "deaths": 6, "assists": 10, "cs": 32, "gold": 7800,
         "kill_participation": 60, "vision_score": 88},
        {"player_name": "ShadowMid", "champion": "Thresh", "win": True,
         "kills": 1, "deaths": 2, "assists": 15, "cs": 25, "gold": 8500,
         "kill_participation": 72, "vision_score": 95},
        {"player_name": "ShadowMid", "champion": "Leona", "win": False,
         "kills": 0, "deaths": 8, "assists": 6, "cs": 18, "gold": 6100,
         "kill_participation": 40, "vision_score": 55},
        # Player 3: YoneMain99 - 2 games, 2W 0L
        {"player_name": "YoneMain99", "champion": "Yone", "win": True,
         "kills": 12, "deaths": 3, "assists": 5, "cs": 278, "gold": 15600,
         "kill_participation": 58, "vision_score": 15},
        {"player_name": "YoneMain99", "champion": "Yasuo", "win": True,
         "kills": 9, "deaths": 4, "assists": 7, "cs": 245, "gold": 14100,
         "kill_participation": 52, "vision_score": 18},
    ]


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "/tmp/summary_test.png"
    matches = make_test_matches()
    grouped = group_by_player(matches)

    result = build_summary_image(grouped)
    if result:
        buf, filename = result
        with open(output, "wb") as f:
            f.write(buf.read())
        print(f"Saved {output}")
    else:
        print("Failed to build summary")
