#!/usr/bin/env python3
"""One-off verification of BetMGM odds vs. MLB Stats API gamePk matching.

NOT part of the pipeline — predict.py/tracker.py are untouched by this.
Makes exactly ONE live call to The Odds API; eyeball the output below
before trusting the real pipeline to log any of this to picks_log.csv.

Usage:
  export ODDS_API_KEY=your_key_here
  python3 verify_odds_match.py
"""
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from mlb_predictor import mlb_api as api
from mlb_predictor import odds

EASTERN = ZoneInfo("America/New_York")


def fmt_times(commence_time: str | None) -> tuple[str, str]:
    if not commence_time:
        return "?", "?"
    dt = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
    return (dt.strftime("%Y-%m-%d %H:%M UTC"),
            dt.astimezone(EASTERN).strftime("%Y-%m-%d %H:%M %Z"))


def main() -> None:
    if not os.environ.get(odds.API_KEY_ENV):
        print(f"{odds.API_KEY_ENV} is not set — export it first, e.g.:\n"
              f"  export {odds.API_KEY_ENV}=your_key_here")
        return

    today = datetime.now(EASTERN).strftime("%Y-%m-%d")
    print(f"Fetching MLB schedule for {today} (Eastern) from the Stats API ...")
    schedule_games = api.schedule(today)
    print(f"  {len(schedule_games)} scheduled game(s).")

    print("Making ONE live call to The Odds API ...")
    odds_list = odds.fetch_moneylines()
    if not odds_list:
        reason = odds.last_error()
        print("No odds returned." +
              (f" Reason: {reason}" if reason else " (empty response)"))
        return
    print(f"  {len(odds_list)} game(s) in the odds snapshot.\n")

    todays_odds = [g for g in odds_list
                  if fmt_times(g.get("commence_time"))[1].startswith(today)]
    print(f"{len(todays_odds)} of those fall on {today} Eastern:\n")
    print("-" * 100)

    for g in todays_odds:
        away_name = g.get("away_team", "?")
        home_name = g.get("home_team", "?")
        utc_str, eastern_str = fmt_times(g.get("commence_time"))

        gamepk = None
        for sg in schedule_games:
            sh = sg["teams"]["home"]["team"]["name"]
            sa = sg["teams"]["away"]["team"]["name"]
            if odds.match_game([g], sa, sh):
                gamepk = sg["gamePk"]
                break

        bm = odds.betmgm_moneyline(g)

        print(f"Odds API teams : {away_name} @ {home_name}")
        print(f"Commence time  : {utc_str}  /  {eastern_str}")
        print(f"gamePk match   : "
              f"{gamepk if gamepk is not None else 'MISSING (no schedule match)'}")
        if bm:
            print(f"BetMGM line    : home {bm['home_ml']:+}   away {bm['away_ml']:+}")
        else:
            print("BetMGM line    : MISSING (betmgm not offering this game)")
        print("-" * 100)


if __name__ == "__main__":
    main()
