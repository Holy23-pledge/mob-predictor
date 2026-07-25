"""Market moneyline odds via The Odds API (the-odds-api.com) — BetMGM only.

Only BetMGM's own line is used. Deliberately not an average across books:
every number logged should trace back to one real, bettable price, and a
game BetMGM isn't pricing is reported as missing rather than filled in from
some other book.

Set the ODDS_API_KEY environment variable to enable this — read from the
environment only, never hardcoded. With no key set, every function below
returns nothing and costs nothing; the rest of the pick flow is unaffected.

The free tier only exposes the *current* line, not historical replays, so
"opening" vs "closing" (as used by tracker.py) means two live snapshots
taken at different times by the caller: once around prediction time, once
again near first pitch via `predict.py --closing`.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from . import mlb_api as api
from .fetch import get_text_nocache

API_KEY_ENV = "ODDS_API_KEY"
SPORT_KEY = "baseball_mlb"
BASE = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/odds"
REGIONS = "us"
MARKETS = "h2h"
BOOKMAKER_KEY = "betmgm"

# Team-name variants seen in the wild (sportsbook feeds, older branding)
# that don't literally match the MLB Stats API's current team name.
# Left: alternate name, normalized (lowercase, no periods). Right: the
# name the MLB Stats API uses for that team, same normalization.
TEAM_ALIASES = {
    "oakland athletics": "athletics",
    "los angeles angels of anaheim": "los angeles angels",
    "la angels": "los angeles angels",
    "arizona d-backs": "arizona diamondbacks",
    "arizona dbacks": "arizona diamondbacks",
}

_last_error: str | None = None
_last_unmatched: list[dict] = []
_last_missing_odds: list[dict] = []


def last_error() -> str | None:
    """Reason the most recent fetch_moneylines() call came back empty, if
    it was actually an error (as opposed to no API key being configured)."""
    return _last_error


def unmatched() -> list[dict]:
    """Odds-api events from the most recent key_by_gamepk() call that
    were present but couldn't be matched to a gamePk by name (empty list
    if none, or if key_by_gamepk() hasn't been called yet)."""
    return _last_unmatched


def missing_odds() -> list[dict]:
    """Scheduled games (gamePk/home/away) from the most recent
    key_by_gamepk() call that had no corresponding event in odds_list at
    all — as opposed to unmatched(), which is events that were present
    but failed to name-match. Empty list if none, or if key_by_gamepk()
    hasn't been called yet."""
    return _last_missing_odds


def american_to_prob(ml: float) -> float:
    return 100 / (ml + 100) if ml > 0 else -ml / (-ml + 100)


def devig_pair(ml_home: float, ml_away: float) -> tuple[float, float]:
    """Two-way de-vig: normalize raw implied probabilities so they sum to
    1, removing the bookmaker's overround."""
    p_home, p_away = american_to_prob(ml_home), american_to_prob(ml_away)
    total = p_home + p_away
    return (p_home / total, p_away / total) if total else (0.5, 0.5)


def implied_prob(odds: float) -> float:
    """Alias of american_to_prob — raw implied probability from American
    odds, vig included."""
    return american_to_prob(odds)


def devig_two_way(home_odds: float, away_odds: float) -> tuple[float, float]:
    """Alias of devig_pair — (vig_free_home, vig_free_away)."""
    return devig_pair(home_odds, away_odds)


def profit_for_win(ml: float, stake: float = 1.0) -> float:
    """Profit (excluding the returned stake) on a winning flat-stake bet
    at American odds `ml`."""
    return stake * (ml / 100 if ml > 0 else 100 / -ml)


def fetch_moneylines() -> list[dict]:
    """One live snapshot of The Odds API's MLB h2h market for every
    upcoming/in-progress game (raw per-event response, all bookmakers).
    Never raises: returns [] if ODDS_API_KEY isn't set, or if the request
    fails (see last_error() for why)."""
    global _last_error
    key = os.environ.get(API_KEY_ENV)
    if not key:
        _last_error = None
        return []
    url = f"{BASE}?apiKey={key}&regions={REGIONS}&markets={MARKETS}&oddsFormat=american"
    try:
        data = json.loads(get_text_nocache(url))
        _last_error = None
        return data
    except Exception as exc:
        _last_error = str(exc)
        return []


def _betmgm_prices(game_odds: dict) -> dict | None:
    """BetMGM's h2h outcome prices for this event, or None if BetMGM isn't
    listed (or hasn't posted a two-sided h2h market) for it."""
    home, away = game_odds.get("home_team"), game_odds.get("away_team")
    for book in game_odds.get("bookmakers", []):
        if book.get("key") != BOOKMAKER_KEY:
            continue
        for market in book.get("markets", []):
            if market.get("key") != MARKETS:
                continue
            home_ml = away_ml = None
            for outcome in market.get("outcomes", []):
                if outcome.get("name") == home:
                    home_ml = outcome.get("price")
                elif outcome.get("name") == away:
                    away_ml = outcome.get("price")
            if home_ml is not None and away_ml is not None:
                return {"home_ml": home_ml, "away_ml": away_ml}
    return None


def games_with_moneylines() -> list[dict]:
    """Every MLB game in the current odds snapshot, BetMGM's line only.
    One dict per game: home_team, away_team, commence_time, home_ml,
    away_ml. If BetMGM has no line for a game, home_ml/away_ml are None
    and missing=True — never backfilled from another book."""
    out = []
    for g in fetch_moneylines():
        prices = _betmgm_prices(g)
        out.append({
            "home_team": g.get("home_team"),
            "away_team": g.get("away_team"),
            "commence_time": g.get("commence_time"),
            "home_ml": prices["home_ml"] if prices else None,
            "away_ml": prices["away_ml"] if prices else None,
            "missing": prices is None,
        })
    return out


def _norm(name: str) -> str:
    return name.lower().replace(".", "").strip()


def match_game(odds_list: list[dict], away_name: str, home_name: str) -> dict | None:
    an, hn = _norm(away_name), _norm(home_name)
    for g in odds_list:
        gh, ga = _norm(g.get("home_team", "")), _norm(g.get("away_team", ""))
        if (hn in gh or gh in hn) and (an in ga or ga in an):
            return g
    return None


def _canonical(name: str) -> str:
    n = _norm(name)
    return TEAM_ALIASES.get(n, n)


def _gamepk_map(schedule_games: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for g in schedule_games:
        pk = g["gamePk"]
        out[_canonical(g["teams"]["home"]["team"]["name"])] = pk
        out[_canonical(g["teams"]["away"]["team"]["name"])] = pk
    return out


def build_gamepk_map(date: str) -> dict[str, int]:
    """canonical team name -> gamePk, for every game on `date` (MLB Stats
    API schedule via mlb_api.schedule()). Each game contributes two
    entries, one per side. Note: on a doubleheader day a team plays two
    gamePks, so its second entry here just overwrites the first — this
    map alone can't disambiguate a doubleheader; treat that as a known
    gap rather than something key_by_gamepk() silently gets right."""
    return _gamepk_map(api.schedule(date))


def key_by_gamepk(odds_list: list[dict], date: str) -> dict[int, dict]:
    """Re-key an odds-api event list (as returned by fetch_moneylines())
    by MLB gamePk — the odds feed only knows team names, our model only
    knows gamePk. Uses the schedule for `date` plus TEAM_ALIASES to
    resolve names. Every scheduled game ends up in exactly one of three
    buckets, so none can silently vanish:
      - matched (returned in the result dict)
      - present in odds_list but failed to name-match -> unmatched()
      - a scheduled gamePk with no corresponding odds_list event at all
        (BetMGM/the feed simply hasn't posted it) -> missing_odds()
    All failures are printed as well as recorded; nothing is raised."""
    global _last_unmatched, _last_missing_odds
    schedule_games = api.schedule(date)
    name_to_pk = _gamepk_map(schedule_games)

    out: dict[int, dict] = {}
    failed: list[dict] = []
    for g in odds_list:
        home_pk = name_to_pk.get(_canonical(g.get("home_team", "")))
        away_pk = name_to_pk.get(_canonical(g.get("away_team", "")))
        if home_pk is None or away_pk is None or home_pk != away_pk:
            print(f"(odds match failed for {date}: "
                  f"{g.get('away_team')!r} @ {g.get('home_team')!r} — "
                  f"no matching gamePk)")
            failed.append(g)
            continue
        out[home_pk] = g
    _last_unmatched = failed

    missing = []
    for g in schedule_games:
        pk = g["gamePk"]
        if pk in out:
            continue
        home = g["teams"]["home"]["team"]["name"]
        away = g["teams"]["away"]["team"]["name"]
        print(f"(no odds event at all for gamePk {pk}: {away} @ {home} on {date})")
        missing.append({"gamePk": pk, "home": home, "away": away})
    _last_missing_odds = missing

    return out


def betmgm_moneyline(game_odds: dict) -> dict | None:
    """BetMGM moneyline plus the two-way de-vigged home win probability
    derived from it, for one raw event entry. None if BetMGM has no line
    for this game (never substitutes another book)."""
    prices = _betmgm_prices(game_odds)
    if not prices:
        return None
    p_home_vigfree, _ = devig_pair(prices["home_ml"], prices["away_ml"])
    return {
        "home_ml": prices["home_ml"], "away_ml": prices["away_ml"],
        "p_home_vigfree": p_home_vigfree,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def snapshot(games: list[dict]) -> dict[str, dict]:
    """Market snapshot for a slate, keyed by gamePk (str), BetMGM only.
    Call once around prediction time (opening) and again near first pitch
    (closing) — same function, two different call times. Games BetMGM
    isn't pricing are simply absent from the result, never substituted."""
    odds_list = fetch_moneylines()
    out = {}
    if not odds_list:
        return out
    for g in games:
        match = match_game(odds_list, g["teams"]["away"]["team"]["name"],
                           g["teams"]["home"]["team"]["name"])
        bm = betmgm_moneyline(match) if match else None
        if bm:
            out[str(g["gamePk"])] = bm
    return out


if __name__ == "__main__":
    raw_home = implied_prob(-150)
    raw_away = implied_prob(130)
    assert abs(raw_home - 0.600) < 0.001, raw_home
    assert abs(raw_away - 0.435) < 0.001, raw_away

    vf_home, vf_away = devig_two_way(-150, 130)
    assert abs(vf_home - 0.580) < 0.001, vf_home
    assert abs(vf_away - 0.420) < 0.001, vf_away

    print(f"raw implied:      home {raw_home:.3f}  away {raw_away:.3f}")
    print(f"vig-free implied: home {vf_home:.3f}  away {vf_away:.3f}")
    print("All assertions passed.")
