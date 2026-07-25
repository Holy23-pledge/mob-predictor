"""Combines the nine factors: P(home win) = sigmoid(GLOBAL_SHRINK * sum)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import factors as F
from . import mlb_api as api
from . import savant, weather
from .config import (DEFAULT_CF_BEARING, DEFAULT_PARK_FACTOR, GLOBAL_SHRINK,
                     PARKS)


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


@dataclass
class Prediction:
    game: dict
    home: dict
    away: dict
    factors: list
    p_home: float
    winner: str
    confidence: str
    lineups: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    def contributions(self) -> list[tuple]:
        total = GLOBAL_SHRINK * sum(f.edge for f in self.factors)
        out = []
        for f in self.factors:
            delta = sigmoid(total) - sigmoid(total - GLOBAL_SHRINK * f.edge)
            out.append((f, 100 * delta))
        return out


def projected_lineup(team_id: int, season: int, n: int = 9) -> list[dict]:
    hitters = [r["person"]["id"] for r in api.roster(team_id, season, "active")
               if r.get("position", {}).get("abbreviation") not in ("P",)]
    people = api.people_stats(hitters, season, "hitting")
    out = []
    for p in people:
        pa, ops, hr = 0, 0.0, 0
        for block in p.get("stats", []):
            if block.get("group", {}).get("displayName") == "hitting":
                for s in block.get("splits", []):
                    st = s.get("stat", {})
                    pa = max(pa, st.get("plateAppearances", 0))
                    hr = max(hr, st.get("homeRuns", 0))
                    try:
                        ops = max(ops, float(st.get("ops", 0) or 0))
                    except ValueError:
                        pass
        out.append({"id": p["id"], "name": p["fullName"], "pa": pa,
                    "ops": ops, "hr": hr})
    out.sort(key=lambda x: -x["pa"])
    return out[:n]


def il_stats(il_list: list, season: int) -> dict:
    people = api.people_stats([p["id"] for p in il_list], season,
                              "hitting,pitching")
    out = {}
    for p in people:
        rec = {"plateAppearances": 0, "ip": 0.0}
        for block in p.get("stats", []):
            grp = block.get("group", {}).get("displayName")
            for s in block.get("splits", []):
                st = s.get("stat", {})
                if grp == "hitting":
                    rec["plateAppearances"] = max(rec["plateAppearances"],
                                                  st.get("plateAppearances", 0))
                elif grp == "pitching":
                    rec["ip"] = max(rec["ip"],
                                    api.parse_ip(st.get("inningsPitched", 0)))
        out[p["id"]] = rec
    return out


def predict_game(game: dict, season: int) -> Prediction:
    home_t = game["teams"]["home"]["team"]
    away_t = game["teams"]["away"]["team"]
    hid, aid = home_t["id"], away_t["id"]
    venue = game.get("venue", {})
    vid = venue.get("id")

    stand = api.standings(season)
    h_rec, a_rec = stand.get(hid, {}), stand.get(aid, {})
    h_hit = api.team_stats(hid, season, "hitting")
    a_hit = api.team_stats(aid, season, "hitting")

    h_sp = game["teams"]["home"].get("probablePitcher")
    a_sp = game["teams"]["away"].get("probablePitcher")
    h_sp_name = h_sp["fullName"] if h_sp else "TBD"
    a_sp_name = a_sp["fullName"] if a_sp else "TBD"
    h_sp_stats = api.pitcher_season(h_sp["id"], season) if h_sp else {}
    a_sp_stats = api.pitcher_season(a_sp["id"], season) if a_sp else {}

    h_lineup = projected_lineup(hid, season)
    a_lineup = projected_lineup(aid, season)

    h_bvp = api.bvp([b["id"] for b in h_lineup], a_sp["id"]) if a_sp else {}
    a_bvp = api.bvp([b["id"] for b in a_lineup], h_sp["id"]) if h_sp else {}

    h_ars = api.pitch_arsenal(h_sp["id"], season) if h_sp else []
    a_ars = api.pitch_arsenal(a_sp["id"], season) if a_sp else []
    teams_by_id = {t["id"]: t for t in api.teams(season)}
    h_abbr = teams_by_id.get(hid, {}).get("abbreviation", "")
    a_abbr = teams_by_id.get(aid, {}).get("abbreviation", "")
    h_vs_pitch = savant.batter_vs_pitchtype(h_abbr, season) if a_ars else {}
    a_vs_pitch = savant.batter_vs_pitchtype(a_abbr, season) if h_ars else {}

    pf, bearing = PARKS.get(vid, (DEFAULT_PARK_FACTOR, DEFAULT_CF_BEARING))
    vinfo = api.venue_info(vid) if vid else {}
    roof = (vinfo.get("fieldInfo", {}) or {}).get("roofType", "Open")
    coords = ((vinfo.get("location", {}) or {}).get("defaultCoordinates", {})
              or {})
    tz = ((vinfo.get("timeZone", {}) or {}).get("id") or "America/New_York")
    wx = None
    if coords.get("latitude") and str(roof).lower().startswith("open"):
        wx = weather.game_weather(coords["latitude"], coords["longitude"],
                                  tz, game["gameDate"], bearing)

    h_il = api.il_players(hid, season)
    a_il = api.il_players(aid, season)
    h_il_st = il_stats(h_il, season)
    a_il_st = il_stats(a_il, season)
    h_il_val, h_il_rows = F.il_impact(h_il, h_il_st)
    a_il_val, a_il_rows = F.il_impact(a_il, a_il_st)

    def rate(st, key, denom="plateAppearances"):
        d = st.get(denom, 0)
        return (st.get(key, 0) / d) if d else 0.0

    h_hr_pa = rate(h_hit, "homeRuns")
    a_hr_pa = rate(a_hit, "homeRuns")

    def team_ops(st):
        try:
            return float(st.get("ops", 0) or 0)
        except ValueError:
            return 0.0

    home_venue_rec = api.split_record(h_rec, "home")

    fs = [
        F.season_strength(h_rec, a_rec),
        F.home_away(h_rec, a_rec, api.split_record),
        F.starting_pitching(h_sp_name, a_sp_name, h_sp_stats, a_sp_stats,
                            api.parse_ip),
        F.bvp_history(h_lineup, a_lineup, h_bvp, a_bvp, h_sp_name, a_sp_name),
        F.arsenal_matchup(h_lineup, a_lineup, h_ars, a_ars,
                          h_vs_pitch, a_vs_pitch, h_sp_name, a_sp_name,
                          savant.CODE_ALIAS),
        F.weather_factor(wx, roof, h_hr_pa, a_hr_pa),
        F.day_night(game.get("dayNight", "night"), h_rec, a_rec,
                    api.split_record),
        F.park_factor(pf, venue.get("name", "?"), team_ops(h_hit),
                      team_ops(a_hit), home_venue_rec),
        F.injuries(h_il, a_il, h_il_val, a_il_val, h_il_rows, a_il_rows),
    ]

    total = GLOBAL_SHRINK * sum(f.edge for f in fs)
    p_home = sigmoid(total)
    winner = home_t["name"] if p_home >= 0.5 else away_t["name"]
    p_win = max(p_home, 1 - p_home)
    confidence = ("strong" if p_win >= 0.62 else
                  "moderate" if p_win >= 0.55 else "slight")

    return Prediction(
        game=game, home=home_t, away=away_t, factors=fs,
        p_home=p_home, winner=winner, confidence=confidence,
        lineups={"home": h_lineup, "away": a_lineup},
        meta={"venue": venue.get("name"), "roof": roof, "park_factor": pf,
              "cf_bearing": bearing, "weather": wx,
              "home_sp": h_sp_name, "away_sp": a_sp_name,
              "day_night": game.get("dayNight"),
              "game_date": game.get("gameDate"), "season": season,
              "total_logodds": total},
    )
