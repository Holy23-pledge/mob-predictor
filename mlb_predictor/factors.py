"""The nine model factors. Each returns a Factor with edge (weighted, capped
log-odds toward home), raw signal, numbers, explanation, and detail rows."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import LEAGUE, SHRINK, WEIGHTS


@dataclass
class Factor:
    key: str
    name: str
    edge: float
    raw: float
    explanation: str
    numbers: list = field(default_factory=list)
    detail: list | None = None


def logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _apply(key: str, raw: float) -> float:
    w = WEIGHTS[key]
    return max(-w["cap"], min(w["cap"], w["w"] * raw))


def _shrink_wpct(wins: int, losses: int, pseudo_games: int) -> float:
    return (wins + pseudo_games / 2) / (wins + losses + pseudo_games) \
        if (wins + losses + pseudo_games) else 0.5


def _num(label, home, away):
    return {"label": label, "home": home, "away": away}


def season_strength(home: dict, away: dict) -> Factor:
    exp = LEAGUE["pyth_exponent"]

    def pyth(rec):
        rs, ra = rec.get("runsScored", 0), rec.get("runsAllowed", 0)
        if not rs or not ra:
            return 0.5
        return rs ** exp / (rs ** exp + ra ** exp)

    ph, pa = pyth(home), pyth(away)
    raw = logit(ph) - logit(pa)
    edge = _apply("season", raw)
    h_w, h_l = home.get("wins", 0), home.get("losses", 0)
    a_w, a_l = away.get("wins", 0), away.get("losses", 0)
    expl = (f"Season quality via run differential. Home is {h_w}-{h_l} "
            f"(RS {home.get('runsScored')}, RA {home.get('runsAllowed')}, "
            f"Pythagorean {ph:.3f}); Away is {a_w}-{a_l} "
            f"(RS {away.get('runsScored')}, RA {away.get('runsAllowed')}, "
            f"Pythagorean {pa:.3f}). "
            + ("The home side has been the stronger run-differential team."
               if raw > 0 else
               "The away side has been the stronger run-differential team."))
    nums = [_num("Record", f"{h_w}-{h_l}", f"{a_w}-{a_l}"),
            _num("Runs scored / allowed",
                 f"{home.get('runsScored')}/{home.get('runsAllowed')}",
                 f"{away.get('runsScored')}/{away.get('runsAllowed')}"),
            _num("Pythagorean W%", f"{ph:.3f}", f"{pa:.3f}")]
    return Factor("season", "Season performance", edge, raw, expl, nums)


def home_away(home_rec: dict, away_rec: dict, split_fn) -> Factor:
    g = SHRINK["team_wpct_games"]
    hh_w, hh_l = split_fn(home_rec, "home")
    ar_w, ar_l = split_fn(away_rec, "away")
    h_all = _shrink_wpct(home_rec.get("wins", 0), home_rec.get("losses", 0), g)
    a_all = _shrink_wpct(away_rec.get("wins", 0), away_rec.get("losses", 0), g)
    h_home = _shrink_wpct(hh_w, hh_l, g)
    a_road = _shrink_wpct(ar_w, ar_l, g)
    rel = (logit(h_home) - logit(h_all)) - (logit(a_road) - logit(a_all))
    base = WEIGHTS["home_away"]["base_hfa"]
    edge = base + _apply("home_away", rel)
    expl = (f"MLB home teams win ~{LEAGUE['home_win_pct']:.0%} of games "
            f"(baseline edge). On top of that: home club is {hh_w}-{hh_l} "
            f"at home this year, and the visitors are {ar_w}-{ar_l} on the "
            f"road. "
            + ("The home club over-performs at home and/or the visitors "
               "under-perform on the road, widening the edge."
               if rel > 0.02 else
               "The visitors travel well, trimming the usual home edge."
               if rel < -0.02 else
               "Neither club deviates much from its norm home/away."))
    nums = [_num("Home record", f"{hh_w}-{hh_l}", "—"),
            _num("Road record", "—", f"{ar_w}-{ar_l}"),
            _num("Regressed split W%", f"{h_home:.3f}", f"{a_road:.3f}")]
    return Factor("home_away", "Home-field advantage", edge, rel, expl, nums)


def starting_pitching(h_name: str, a_name: str,
                      h_stats: dict, a_stats: dict, parse_ip) -> Factor:
    def fip(st):
        ip = parse_ip(st.get("inningsPitched", 0))
        if ip < 10:
            return None, ip
        hr, bb = st.get("homeRuns", 0), st.get("baseOnBalls", 0)
        hbp, k = st.get("hitBatsmen", 0), st.get("strikeOuts", 0)
        return (13 * hr + 3 * (bb + hbp) - 2 * k) / ip + LEAGUE["fip_constant"], ip

    fh, ip_h = fip(h_stats)
    fa, ip_a = fip(a_stats)
    fh_eff = fh if fh is not None else LEAGUE["avg_fip"]
    fa_eff = fa if fa is not None else LEAGUE["avg_fip"]
    runs_per_game = (fa_eff - fh_eff) * (6.0 / 9.0)
    raw = 0.40 * runs_per_game
    cap = WEIGHTS["pitching"]["cap"]
    edge = max(-cap, min(cap, raw))
    small = []
    if fh is None:
        small.append(f"{h_name} has <10 IP this year — league-average FIP assumed.")
    if fa is None:
        small.append(f"{a_name} has <10 IP this year — league-average FIP assumed.")
    expl = (f"{h_name} (home): {h_stats.get('era','—')} ERA, "
            f"FIP {fh_eff:.2f} over {ip_h:.0f} IP. "
            f"{a_name} (away): {a_stats.get('era','—')} ERA, "
            f"FIP {fa_eff:.2f} over {ip_a:.0f} IP. "
            f"FIP gap of {abs(fa_eff-fh_eff):.2f} runs/9 over a ~6-inning start "
            f"is worth ~{abs(runs_per_game):.2f} runs, favoring the "
            + ("home" if raw > 0 else "away") + " starter. " + " ".join(small))
    nums = [_num("Starter", h_name, a_name),
            _num("ERA", h_stats.get("era", "—"), a_stats.get("era", "—")),
            _num("FIP", f"{fh_eff:.2f}", f"{fa_eff:.2f}"),
            _num("IP", f"{ip_h:.1f}", f"{ip_a:.1f}"),
            _num("K / BB", f"{h_stats.get('strikeOuts','—')}/{h_stats.get('baseOnBalls','—')}",
                 f"{a_stats.get('strikeOuts','—')}/{a_stats.get('baseOnBalls','—')}")]
    return Factor("pitching", "Starting pitching matchup", edge, raw, expl, nums)


def bvp_history(h_lineup: list, a_lineup: list,
                h_bvp: dict, a_bvp: dict,
                h_pitcher: str, a_pitcher: str) -> Factor:
    k = SHRINK["bvp_pa"]
    lg = LEAGUE["ops"]

    def team_bvp(lineup, bvp_map):
        tot_pa, wsum, rows = 0, 0.0, []
        for b in lineup:
            st = bvp_map.get(b["id"])
            if not st:
                continue
            pa = st.get("plateAppearances", 0)
            try:
                ops = float(st.get("ops", "0") or 0)
            except ValueError:
                ops = 0.0
            if pa > 0:
                tot_pa += pa
                wsum += pa * ops
                rows.append({"name": b["name"], "pa": pa,
                             "avg": st.get("avg", "—"), "ops": st.get("ops", "—"),
                             "hr": st.get("homeRuns", 0),
                             "so": st.get("strikeOuts", 0)})
        agg = (wsum / tot_pa) if tot_pa else lg
        shrunk = (tot_pa / (tot_pa + k))
        return agg, tot_pa, shrunk, sorted(rows, key=lambda r: -r["pa"])

    h_agg, h_pa, h_sh, h_rows = team_bvp(h_lineup, h_bvp)
    a_agg, a_pa, a_sh, a_rows = team_bvp(a_lineup, a_bvp)
    raw = (h_agg - lg) * h_sh - (a_agg - lg) * a_sh
    edge = _apply("bvp", raw)
    expl = (f"Career history: home lineup vs {a_pitcher}: {h_pa} PA, "
            f"weighted OPS {h_agg:.3f}; away lineup vs {h_pitcher}: {a_pa} PA, "
            f"weighted OPS {a_agg:.3f} (league ~{lg:.3f}). Samples are shrunk "
            f"toward league average by PA (weights {h_sh:.0%} / {a_sh:.0%}). "
            + ("Home hitters have the better track record in this matchup."
               if raw > 0.005 else
               "Away hitters have the better track record in this matchup."
               if raw < -0.005 else "No meaningful BvP edge either way."))
    nums = [_num("Lineup PA vs opposing starter", h_pa, a_pa),
            _num("Weighted OPS in matchup", f"{h_agg:.3f}", f"{a_agg:.3f}"),
            _num("Sample weight", f"{h_sh:.0%}", f"{a_sh:.0%}")]
    detail = [{"title": f"Home hitters vs {a_pitcher} (career)", "rows": h_rows},
              {"title": f"Away hitters vs {h_pitcher} (career)", "rows": a_rows}]
    return Factor("bvp", "Batter vs pitcher history", edge, raw, expl, nums, detail)


def arsenal_matchup(h_lineup: list, a_lineup: list,
                    h_arsenal: list, a_arsenal: list,
                    h_vs_pitch: dict, a_vs_pitch: dict,
                    h_pitcher: str, a_pitcher: str,
                    code_alias: dict) -> Factor:
    lg = LEAGUE["woba"]

    def expected_woba(lineup, arsenal, vs_pitch):
        if not arsenal:
            return None, []
        rows = []
        total_usage = sum(p["pct"] for p in arsenal) or 1.0
        exp_woba = 0.0
        for p in arsenal:
            code = code_alias.get(p["code"], p["code"])
            pa_sum, wsum = 0, 0.0
            for b in lineup:
                d = vs_pitch.get(b["id"], {}).get(code)
                if d and d["woba"] is not None and d["pa"] > 0:
                    pa_sum += d["pa"]
                    wsum += d["pa"] * d["woba"]
            lw = (wsum / pa_sum) if pa_sum else lg
            adj = 0.0
            if p["code"] in ("FF", "SI") and p["velo"]:
                adj = -0.004 * (p["velo"] - 93.5)
            eff = lw + adj
            share = p["pct"] / total_usage
            exp_woba += share * eff
            rows.append({"pitch": p["description"], "usage": f"{p['pct']:.0%}",
                         "velo": f"{p['velo']:.1f}", "lineup_woba": f"{lw:.3f}",
                         "velo_adj": f"{adj:+.3f}", "pa": pa_sum})
        return exp_woba, rows

    h_exp, h_rows = expected_woba(h_lineup, a_arsenal, h_vs_pitch)
    a_exp, a_rows = expected_woba(a_lineup, h_arsenal, a_vs_pitch)
    h_eff = h_exp if h_exp is not None else lg
    a_eff = a_exp if a_exp is not None else lg
    raw = (h_eff - lg) - (a_eff - lg)
    edge = _apply("arsenal", raw)
    expl = (f"Each lineup is scored against the opposing starter's pitch mix "
            f"and velocity (Statcast). Home lineup projects to a {h_eff:.3f} "
            f"wOBA vs {a_pitcher}'s arsenal; away lineup projects to "
            f"{a_eff:.3f} vs {h_pitcher}'s (league ~{lg:.3f}). "
            + ("The home lineup profiles better against this pitch mix."
               if raw > 0.004 else
               "The away lineup profiles better against this pitch mix."
               if raw < -0.004 else
               "Both lineups profile about evenly against these arsenals."))
    nums = [_num("Projected wOBA vs opposing arsenal",
                 f"{h_eff:.3f}", f"{a_eff:.3f}"),
            _num("vs league average", f"{h_eff - lg:+.3f}", f"{a_eff - lg:+.3f}")]
    detail = [{"title": f"Home lineup vs {a_pitcher}'s arsenal",
               "rows": h_rows, "kind": "arsenal"},
              {"title": f"Away lineup vs {h_pitcher}'s arsenal",
               "rows": a_rows, "kind": "arsenal"}]
    return Factor("arsenal", "Lineup vs pitch-mix profile", edge, raw, expl,
                  nums, detail)


def weather_factor(wx: dict | None, roof: str,
                   h_hr_pa: float, a_hr_pa: float) -> Factor:
    lg_hr = LEAGUE["hr_per_pa"]
    if roof and roof.lower() not in ("open", "open air", ""):
        expl = (f"Roofed/indoor park ({roof}): weather is controlled, "
                "no wind or temperature effect applied.")
        return Factor("weather", "Weather & wind", 0.0, 0.0, expl,
                      [_num("Roof", roof, roof)])
    if not wx:
        return Factor("weather", "Weather & wind", 0.0, 0.0,
                      "Forecast unavailable; factor skipped.", [])
    temp_mult = 1 + 0.025 * (wx["temp_f"] - 70) / 10
    wind_mult = 1 + 0.004 * wx["wind_out_mph"]
    env = temp_mult * wind_mult
    hr_gap = (h_hr_pa - a_hr_pa) / lg_hr
    raw = (env - 1.0) * hr_gap * 0.5
    edge = _apply("weather", raw)
    wind_desc = (f"blowing OUT to center at {abs(wx['wind_out_mph']):.0f} mph"
                 if wx["wind_out_mph"] > 3 else
                 f"blowing IN from center at {abs(wx['wind_out_mph']):.0f} mph"
                 if wx["wind_out_mph"] < -3 else "roughly neutral (crosswind/calm)")
    expl = (f"First pitch ~{wx['local_time']}: {wx['temp_f']:.0f}°F, "
            f"wind {wx['wind_mph']:.0f} mph "
            f"from the {wx['wind_dir_label']} — {wind_desc}. "
            f"Estimated run environment {env:.0%} of normal. "
            f"Precip chance {wx['precip_prob']:.0f}%. "
            + ("A livelier ball favors the more power-based lineup ("
               + ("home" if hr_gap > 0 else "away") + ")."
               if (env > 1.02 and abs(hr_gap) > 0.05) else
               "A deadened ball hurts the more power-based lineup ("
               + ("home" if hr_gap > 0 else "away") + ")."
               if (env < 0.98 and abs(hr_gap) > 0.05) else
               "Conditions are close to neutral for both offenses."))
    nums = [_num("HR per PA", f"{h_hr_pa:.3f}", f"{a_hr_pa:.3f}"),
            _num("Temp / wind out", f"{wx['temp_f']:.0f}°F",
                 f"{wx['wind_out_mph']:+.0f} mph"),
            _num("Run environment", f"{env:.0%}", f"{env:.0%}")]
    return Factor("weather", "Weather & wind", edge, raw, expl, nums)


def day_night(day_night_code: str, home_rec: dict, away_rec: dict,
              split_fn) -> Factor:
    g = SHRINK["team_wpct_games"]
    st = "day" if day_night_code == "day" else "night"
    h_w, h_l = split_fn(home_rec, st)
    a_w, a_l = split_fn(away_rec, st)
    h_all = _shrink_wpct(home_rec.get("wins", 0), home_rec.get("losses", 0), g)
    a_all = _shrink_wpct(away_rec.get("wins", 0), away_rec.get("losses", 0), g)
    h_sp = _shrink_wpct(h_w, h_l, g)
    a_sp = _shrink_wpct(a_w, a_l, g)
    raw = (logit(h_sp) - logit(h_all)) - (logit(a_sp) - logit(a_all))
    edge = _apply("day_night", raw)
    expl = (f"This is a {st} game. Home club is {h_w}-{h_l} in {st} games "
            f"this year; visitors are {a_w}-{a_l}. Relative to overall level "
            + ("the home side has been better in this time slot."
               if raw > 0.02 else
               "the visitors have been better in this time slot."
               if raw < -0.02 else "neither team shows a real split."))
    nums = [_num(f"{st.title()} record", f"{h_w}-{h_l}", f"{a_w}-{a_l}"),
            _num("Regressed W%", f"{h_sp:.3f}", f"{a_sp:.3f}")]
    return Factor("day_night", f"Time of day ({st} game)", edge, raw, expl, nums)


def park_factor(pf: int, venue_name: str, h_ops: float, a_ops: float,
                home_venue_rec: tuple) -> Factor:
    lg = LEAGUE["ops"]
    ops_gap = (h_ops - a_ops)
    raw = (pf - 100) / 100 * ops_gap * 4.0
    edge = _apply("park", raw)
    w, l = home_venue_rec
    kind = ("a strong hitters' park" if pf >= 104 else
            "a hitter-leaning park" if pf >= 102 else
            "a strong pitchers' park" if pf <= 96 else
            "a pitcher-leaning park" if pf <= 98 else "roughly neutral")
    expl = (f"{venue_name} is {kind} (park factor {pf}; 100 = neutral). "
            f"Home offense OPS {h_ops:.3f} vs away {a_ops:.3f} "
            f"(league ~{lg:.3f}) — "
            + ("the park amplifies the home club's offensive edge."
               if raw > 0.005 else
               "the park amplifies the away club's offensive edge."
               if raw < -0.005 else
               "the park doesn't meaningfully favor either lineup.")
            + f" Home club is {w}-{l} in this building this season.")
    nums = [_num("Park factor", pf, pf),
            _num("Team OPS", f"{h_ops:.3f}", f"{a_ops:.3f}"),
            _num("Record at venue", f"{w}-{l}", "—")]
    return Factor("park", f"Stadium: {venue_name}", edge, raw, expl, nums)


def injuries(h_il: list, a_il: list, h_il_value: float, a_il_value: float,
             h_rows: list, a_rows: list) -> Factor:
    raw = a_il_value - h_il_value
    edge = _apply("injuries", raw)
    expl = (f"Injured list: home club has {len(h_il)} players on the IL "
            f"(impact score {h_il_value:.2f}), visitors have {len(a_il)} "
            f"(impact score {a_il_value:.2f}). Impact weights each injured "
            f"player by current-season playing time. "
            + ("The visitors are more shorthanded."
               if raw > 0.02 else
               "The home club is more shorthanded."
               if raw < -0.02 else
               "Injury burdens are roughly even."))
    nums = [_num("Players on IL", len(h_il), len(a_il)),
            _num("Weighted impact", f"{h_il_value:.2f}", f"{a_il_value:.2f}")]
    detail = [{"title": "Home injured list", "rows": h_rows, "kind": "il"},
              {"title": "Away injured list", "rows": a_rows, "kind": "il"}]
    return Factor("injuries", "Injury report", edge, raw, expl, nums, detail)


def il_impact(il_list: list, stats_by_id: dict) -> tuple[float, list]:
    total, rows = 0.0, []
    for p in il_list:
        st = stats_by_id.get(p["id"], {})
        pa = st.get("plateAppearances", 0) or 0
        ip = st.get("ip", 0.0) or 0.0
        val = 0.02
        if pa >= 200 or ip >= 50:
            val = 0.06
        elif pa >= 80 or ip >= 20:
            val = 0.04
        total += val
        usage = f"{pa} PA" if pa else (f"{ip:.0f} IP" if ip else "no playing time")
        rows.append({"name": p["name"], "pos": p["position"],
                     "status": p["status"], "usage": usage, "impact": f"{val:.2f}"})
    return total, rows
