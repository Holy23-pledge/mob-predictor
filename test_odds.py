#!/usr/bin/env python3
"""Standalone check of the BetMGM odds fetch — not wired into the pick flow.

Usage:
  export ODDS_API_KEY=your_key_here
  python3 test_odds.py
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from mlb_predictor import odds


def main() -> None:
    if not os.environ.get(odds.API_KEY_ENV):
        print(f"{odds.API_KEY_ENV} is not set — export it first, e.g.:\n"
              f"  export {odds.API_KEY_ENV}=your_key_here")
        return

    games = odds.games_with_moneylines()
    if not games:
        reason = odds.last_error()
        print("No games returned." +
              (f" Reason: {reason}" if reason else " (empty response)"))
        return

    today = datetime.now(timezone.utc).date()
    todays_games = [
        g for g in games
        if g["commence_time"] and
        datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00")).date() == today
    ]

    print(f"{len(games)} game(s) in the current odds snapshot, "
          f"{len(todays_games)} with a commence_time today (UTC {today}).\n")

    for g in todays_games or games:
        local = datetime.fromisoformat(
            g["commence_time"].replace("Z", "+00:00")).astimezone()
        matchup = f"{g['away_team']} @ {g['home_team']}"
        if g["missing"]:
            print(f"{local:%Y-%m-%d %H:%M %Z}  {matchup:<45}  MISSING (no BetMGM line)")
        else:
            print(f"{local:%Y-%m-%d %H:%M %Z}  {matchup:<45}  "
                  f"home {g['home_ml']:+d}   away {g['away_ml']:+d}")


if __name__ == "__main__":
    main()
