"""Automatic pick logging, settling, and calibration/market reporting."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from . import mlb_api as api
from . import odds

FIELDS = ["date", "gamePk", "away", "home", "pick", "win_prob", "p_home",
          "confidence", "top_factor", "actual_winner", "correct",
          "entry_home_ml", "entry_away_ml", "entry_p_home_vigfree",
          "close_home_ml", "close_away_ml", "close_p_home_vigfree",
          "close_mins_before_start",
          "clv", "edge_vs_close", "pnl_flat"]

BUCKETS = [("50-55%", 0.50, 0.55), ("55-60%", 0.55, 0.60),
           ("60-65%", 0.60, 0.65), ("65-70%", 0.65, 0.70),
           ("70-75%", 0.70, 0.75), ("75%+", 0.75, 1.01)]


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _save(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def record(path: Path, date: str, preds: list) -> None:
    """Add/replace today's picks (re-running the same day just updates
    them). Also captures each game's entry (prediction-time) BetMGM
    moneyline and vig-free home probability, via odds.key_by_gamepk() —
    which fetches its own MLB schedule for `date` and prints/records both
    name-match failures (odds.unmatched()) and games BetMGM hasn't lined
    at all (odds.missing_odds()). A game in either of those buckets still
    gets its pick logged here (date, gamePk, pick, p_home, ...) — it's
    just the entry_* odds fields that stay blank; capture_closing() can
    backfill the line later if BetMGM posts one before first pitch. With
    no ODDS_API_KEY configured, odds.fetch_moneylines() returns [] and
    this whole step is skipped — no extra network call, no odds columns.

    Once an entry line is logged for a game it's kept on later same-day
    reruns rather than replaced (the point is the *first* number seen);
    closing-line fields carried over from a prior row are preserved the
    same way — only capture_closing() should touch them."""
    odds_list = odds.fetch_moneylines()
    entry_by_pk: dict[int, dict] = {}
    if odds_list:
        matched = odds.key_by_gamepk(odds_list, date)
        entry_by_pk = {pk: bm for pk, ev in matched.items()
                       if (bm := odds.betmgm_moneyline(ev))}
        print(f"Captured entry BetMGM odds for {len(entry_by_pk)}/"
              f"{len(matched)} matched game(s).")
    elif odds.last_error():
        print(f"(entry odds capture skipped: {odds.last_error()})")

    rows = _load(path)
    prior = {(r.get("date"), str(r.get("gamePk"))): r for r in rows}
    pks = {str(p.game.get("gamePk")) for p in preds}
    rows = [r for r in rows if not (r.get("date") == date
                                    and str(r.get("gamePk")) in pks)]
    for p in preds:
        pk = p.game.get("gamePk")
        gp = str(pk or "")
        prev = prior.get((date, gp), {})
        bm = entry_by_pk.get(pk)
        entry_home_ml = prev.get("entry_home_ml") or (
            str(bm["home_ml"]) if bm else "")
        entry_away_ml = prev.get("entry_away_ml") or (
            str(bm["away_ml"]) if bm else "")
        entry_p_home_vigfree = prev.get("entry_p_home_vigfree") or (
            f"{bm['p_home_vigfree']:.4f}" if bm else "")
        top = max(p.factors, key=lambda f: abs(f.edge))
        rows.append({
            "date": date, "gamePk": gp,
            "away": p.away["name"], "home": p.home["name"],
            "pick": p.winner,
            "win_prob": f"{max(p.p_home, 1 - p.p_home):.3f}",
            "p_home": f"{p.p_home:.3f}",
            "confidence": p.confidence, "top_factor": top.name,
            "actual_winner": "", "correct": "",
            "entry_home_ml": entry_home_ml, "entry_away_ml": entry_away_ml,
            "entry_p_home_vigfree": entry_p_home_vigfree,
            "close_home_ml": prev.get("close_home_ml", ""),
            "close_away_ml": prev.get("close_away_ml", ""),
            "close_p_home_vigfree": prev.get("close_p_home_vigfree", ""),
            "clv": prev.get("clv", ""),
            "edge_vs_close": prev.get("edge_vs_close", ""),
            "pnl_flat": prev.get("pnl_flat", ""),
        })
    rows.sort(key=lambda r: (r.get("date", ""), str(r.get("gamePk", ""))))
    _save(path, rows)


def capture_closing(path: Path, date: str) -> int:
    """Run as close to the slate's earliest first pitch as practical:
    fetch the current BetMGM line for `date` and backfill
    close_home_ml/close_away_ml/close_p_home_vigfree onto every
    already-logged row for that date — including a row whose entry odds
    were blank because the game was in odds.missing_odds() at prediction
    time; if BetMGM has posted a line by now, it lands here. Only a game
    BetMGM still hasn't lined by this call stays null at settle time —
    settle()'s CLV/ROI scoring simply excludes those, they're never
    dropped from the pick log.

    One snapshot can't land at first pitch for every game on a spread-out
    slate, so each updated row also gets close_mins_before_start: minutes
    between this capture and that specific game's scheduled start
    (positive = captured before first pitch, negative = after it already
    started). Use it later to filter CLV down to picks where the close
    was actually captured near first pitch rather than hours early.

    Safe to call more than once — each call overwrites with the latest
    snapshot (including close_mins_before_start), so the last call before
    first pitch wins. Returns how many rows were updated."""
    odds_list = odds.fetch_moneylines()
    if not odds_list:
        return 0
    matched = odds.key_by_gamepk(odds_list, date)
    start_by_pk = {g["gamePk"]: g.get("gameDate") for g in api.schedule(date)}
    captured_at = datetime.now(timezone.utc)

    rows = _load(path)
    n = 0
    for r in rows:
        if r.get("date") != date:
            continue
        try:
            pk = int(r.get("gamePk"))
        except (TypeError, ValueError):
            continue
        event = matched.get(pk)
        bm = odds.betmgm_moneyline(event) if event else None
        if not bm:
            continue
        r["close_home_ml"] = str(bm["home_ml"])
        r["close_away_ml"] = str(bm["away_ml"])
        r["close_p_home_vigfree"] = f"{bm['p_home_vigfree']:.4f}"

        game_date = start_by_pk.get(pk)
        if game_date:
            start = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
            gap_min = (start - captured_at).total_seconds() / 60
            r["close_mins_before_start"] = f"{gap_min:.1f}"
        n += 1
    if n:
        _save(path, rows)
    return n


def settle(path: Path, today: str) -> int:
    """Fill in final results for unsettled picks from earlier dates."""
    rows = _load(path)
    dates = {r["date"] for r in rows
             if not r.get("actual_winner") and r.get("date") and
             r["date"] < today}
    settled = 0
    for d in sorted(dates):
        try:
            games = api.schedule(d)
        except Exception:
            continue
        finals = {}
        for g in games:
            if g.get("status", {}).get("abstractGameState") != "Final":
                continue
            hs = g["teams"]["home"].get("score")
            aw = g["teams"]["away"].get("score")
            if hs is None or aw is None or hs == aw:
                continue
            winner = (g["teams"]["home"]["team"]["name"] if hs > aw
                      else g["teams"]["away"]["team"]["name"])
            finals[str(g["gamePk"])] = winner
        for r in rows:
            if (r["date"] == d and not r.get("actual_winner")
                    and str(r.get("gamePk")) in finals):
                r["actual_winner"] = finals[str(r["gamePk"])]
                r["correct"] = "1" if r["actual_winner"] == r["pick"] else "0"
                settled += 1
    scored = _score_market(rows)
    if settled or scored:
        _save(path, rows)
    return settled


def _score_market(rows: list[dict]) -> int:
    """Once a pick's result is known, and both entry and closing
    moneylines were captured, compute for that pick:

    clv (closing-line value) = de-vigged closing probability of our
    pick's side minus the de-vigged entry probability of that same side
    — positive means the market moved toward our pick after we'd have
    logged it (a signal of real edge, independent of whether it won).

    edge_vs_close = our model's own P(home) minus the vig-free P(home)
    at close — always home-referenced (not pick-side-adjusted), so it
    lines up directly with the already-logged p_home column; a negative
    value on a pick where we took the away side is a *positive* edge on
    that side, not a negative one.

    pnl_flat = profit/loss on a flat 1-unit bet at the entry moneyline
    (the price available when the pick was made), settled by the actual
    result — the basis for the ROI figures in the market report.

    A game with no entry line (odds.missing_odds() at prediction time)
    or no closing line simply isn't scored here — it stays in the pick
    log, just excluded from CLV/ROI.
    """
    scored = 0
    for r in rows:
        if not r.get("actual_winner") or r.get("pnl_flat"):
            continue
        try:
            entry_h = float(r["entry_home_ml"])
            entry_a = float(r["entry_away_ml"])
            close_h = float(r["close_home_ml"])
            close_a = float(r["close_away_ml"])
            p_home = float(r["p_home"])
        except (KeyError, ValueError):
            continue
        pick_home = r["pick"] == r["home"]
        p_entry_home, p_entry_away = odds.devig_pair(entry_h, entry_a)
        p_close_home, p_close_away = odds.devig_pair(close_h, close_a)
        p_entry_pick = p_entry_home if pick_home else p_entry_away
        p_close_pick = p_close_home if pick_home else p_close_away

        r["clv"] = f"{p_close_pick - p_entry_pick:+.4f}"
        r["edge_vs_close"] = f"{p_home - p_close_home:+.4f}"

        pick_ml = entry_h if pick_home else entry_a
        won = r["actual_winner"] == r["pick"]
        r["pnl_flat"] = f"{odds.profit_for_win(pick_ml):.3f}" if won else "-1.000"
        scored += 1
    return scored


def bucket_stats(path: Path) -> list[dict]:
    """Settled picks grouped into 5% confidence bands."""
    rows = [r for r in _load(path) if r.get("correct") in ("0", "1")]
    out = []
    for name, lo, hi in BUCKETS:
        b = [r for r in rows if lo <= float(r["win_prob"]) < hi]
        if not b:
            continue
        w = sum(r["correct"] == "1" for r in b)
        avg = sum(float(r["win_prob"]) for r in b) / len(b)
        out.append({"band": name, "n": len(b), "w": w, "l": len(b) - w,
                    "actual": w / len(b), "predicted": avg,
                    "diff": w / len(b) - avg})
    return out


def print_summary(path: Path) -> None:
    rows = [r for r in _load(path) if r.get("correct") in ("0", "1")]
    if not rows:
        print("\nPick log started - results fill in automatically on "
              "future runs (picks_log.csv).")
        return
    wins = sum(r["correct"] == "1" for r in rows)
    exp = sum(float(r["win_prob"]) for r in rows)
    print(f"\nPick log: {wins}-{len(rows) - wins} on {len(rows)} settled "
          f"picks (model expected {exp:.1f} wins).")
    print("  Band     W-L      Actual   Predicted   Diff")
    for b in bucket_stats(path):
        print(f"  {b['band']:8s}{b['w']}-{b['l']:<6d} {b['actual']:6.1%}   "
              f"{b['predicted']:6.1%}    {b['diff']:+5.1%}")


def write_calibration_html(path: Path, out: Path) -> bool:
    """Calibration dashboard: actual vs predicted win% in 5% bands."""
    from .report import CSS
    rows = [r for r in _load(path) if r.get("correct") in ("0", "1")]
    if not rows:
        return False
    wins = sum(r["correct"] == "1" for r in rows)
    exp = sum(float(r["win_prob"]) for r in rows)
    body = ""
    for b in bucket_stats(path):
        bar_a = int(b["actual"] * 100)
        bar_p = int(b["predicted"] * 100)
        cls = "pos" if b["diff"] >= 0 else "neg"
        note = ("small sample" if b["n"] < 30 else
                "over-performing" if b["diff"] > 0.03 else
                "under-performing" if b["diff"] < -0.03 else "on target")
        body += f"""<tr><td>{b['band']}</td><td class='r'>{b['n']}</td>
<td class='r'>{b['w']}-{b['l']}</td>
<td class='r'>{b['actual']:.1%}</td><td class='r'>{b['predicted']:.1%}</td>
<td class='r {cls}'>{b['diff']:+.1%}</td><td class='small'>{note}</td></tr>
<tr><td colspan='7' style='padding:0 10px 10px'>
<div class='bar' style='height:8px;margin:0'>
<div class='h' style='width:{bar_a}%'></div></div>
<div class='bar' style='height:8px;margin:2px 0 0'>
<div class='a' style='width:{bar_p}%'></div></div></td></tr>"""
    html_doc = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Model calibration</title><style>{CSS}</style></head><body>
<div class="wrap"><h1>Model calibration</h1>
<div class="sub">Settled picks: {len(rows)} &middot; record {wins}-{len(rows)-wins}
({wins/len(rows):.1%}) &middot; model expected {exp:.1f} wins
({exp/len(rows):.1%}). Blue bar = actual win rate, red bar = predicted.</div>
<div class="card"><table>
<tr><th>Confidence band</th><th class="r">Picks</th><th class="r">W-L</th>
<th class="r">Actual win%</th><th class="r">Predicted</th>
<th class="r">Diff</th><th>Read</th></tr>{body}</table>
<p class="small" style="margin-top:10px">A band is only meaningful with 30+
picks; ~100+ before trusting a pattern. If most bands sit below their
predicted line, lower GLOBAL_SHRINK in mlb_predictor/config.py (1.0 &rarr;
~0.75). If one specific band lags with a real sample, bring picks_log.csv
back to Claude for a fitted correction.</p>
</div></div></body></html>"""
    out.write_text(html_doc, encoding="utf-8")
    return True


def _market_rows(path: Path) -> list[dict]:
    """Settled picks that have a full entry+closing market snapshot and a
    computed CLV/pnl — the population the market report is built from."""
    out = []
    for r in _load(path):
        if not r.get("pnl_flat"):
            continue
        try:
            out.append({
                **r,
                "clv": float(r["clv"]),
                "edge_vs_close": float(r["edge_vs_close"]),
                "pnl": float(r["pnl_flat"]),
            })
        except (KeyError, ValueError):
            continue
    return out


def _pick_side_edge(r: dict) -> float:
    """Model's probability on the side we actually picked minus the
    market's vig-free closing probability on that same side. Unlike the
    logged edge_vs_close column (always home-referenced: p_home minus
    vig-free closing P(home)), this is pick-side-adjusted — a large
    negative edge_vs_close on an away pick is a *positive* edge for that
    pick, not a negative one, so filtering on the raw column would
    silently exclude/include the wrong away picks."""
    pick_home = r["pick"] == r["home"]
    p_close_home, p_close_away = odds.devig_pair(
        float(r["close_home_ml"]), float(r["close_away_ml"]))
    p_close_pick = p_close_home if pick_home else p_close_away
    model_p_pick = float(r["p_home"]) if pick_home else 1 - float(r["p_home"])
    return model_p_pick - p_close_pick


def _in_time_window(r: dict, max_mins: float) -> bool:
    """True if this pick's closing line was captured within `max_mins`
    minutes of that game's first pitch (either side). False (excluding
    the row from the windowed sample) if close_mins_before_start is
    missing/unparseable — a spread-out slate can only get one capture_
    closing() snapshot near the earliest first pitch, so games later in
    the slate may have no reliable close-to-start reading at all."""
    try:
        return abs(float(r["close_mins_before_start"])) <= max_mins
    except (KeyError, ValueError):
        return False


def write_market_report_html(path: Path, out: Path,
                             close_mins_before_start_max: float = 30.0,
                             edge_thresholds: tuple = (0.02, 0.03, 0.05)) -> bool:
    """Market benchmark dashboard: average CLV, % of picks that beat the
    closing line, flat-stake ROI, and ROI restricted to picks where our
    model's pick-side-adjusted edge over the vig-free closing price
    exceeded 2/3/5 percentage points (see _pick_side_edge — NOT the
    home-referenced edge_vs_close column, which would mis-filter away
    picks).

    Every metric is shown twice: once restricted to picks whose closing
    line was actually captured near first pitch (within
    `close_mins_before_start_max` minutes, default 30 — a genuine
    closing-line read rather than one taken hours early on a spread-out
    slate) and once across the full sample, so a shift under the time
    filter is visible rather than hidden. Every number carries its own n
    inline, since the edge-threshold buckets in particular can be tiny."""
    from .report import CSS
    rows = _market_rows(path)
    if not rows:
        return False
    for r in rows:
        r["pick_edge"] = _pick_side_edge(r)

    full_rows = rows
    windowed_rows = [r for r in rows if _in_time_window(r, close_mins_before_start_max)]

    def cls(v: float) -> str:
        return "pos" if v > 0 else ("neg" if v < 0 else "zero")

    def signed_cell(v, n, prec: int = 1) -> str:
        if n == 0:
            return "<td class='r small'>n/a (n=0)</td>"
        return f"<td class='r {cls(v)}'>{v:+.{prec}%} <span class='small'>(n={n})</span></td>"

    def plain_cell(v, n, prec: int = 1) -> str:
        if n == 0:
            return "<td class='r small'>n/a (n=0)</td>"
        return f"<td class='r'>{v:.{prec}%} <span class='small'>(n={n})</span></td>"

    def stat_row(label: str, rs: list[dict]) -> str:
        n = len(rs)
        if n == 0:
            na = "<td class='r small'>n/a (n=0)</td>"
            return f"<tr><td>{label}</td><td class='r'>0</td>{na}{na}{na}" + na * len(edge_thresholds) + "</tr>"
        avg_clv = sum(r["clv"] for r in rs) / n
        pos_clv_pct = sum(r["clv"] > 0 for r in rs) / n
        roi = sum(r["pnl"] for r in rs) / n
        edge_cells = ""
        for t in edge_thresholds:
            sub = [r for r in rs if r["pick_edge"] > t]
            en = len(sub)
            eroi = sum(r["pnl"] for r in sub) / en if en else None
            edge_cells += (signed_cell(eroi, en)
                           if eroi is not None else "<td class='r small'>n/a (n=0)</td>")
        return (f"<tr><td>{label}</td><td class='r'>{n}</td>"
                f"{signed_cell(avg_clv, n, 2)}"
                f"{plain_cell(pos_clv_pct, n)}"
                f"{signed_cell(roi, n)}"
                f"{edge_cells}</tr>")

    body = (stat_row(f"Within {close_mins_before_start_max:.0f} min of first pitch",
                     windowed_rows)
           + stat_row("Full sample (no time filter)", full_rows))
    edge_headers = "".join(
        f"<th class='r'>ROI, pick-edge &gt; {t:.0%}</th>" for t in edge_thresholds)

    html_doc = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market benchmark</title><style>{CSS}</style></head><body>
<div class="wrap"><h1>Market benchmark</h1>
<div class="sub">Settled picks with a full entry+closing odds snapshot:
{len(full_rows)}. Compares our model against the market's own vig-free
line rather than against itself. Every figure below carries its own n —
check it before trusting a number, especially in the high-edge columns.</div>
<div class="card"><table>
<tr><th></th><th class="r">n</th><th class="r">Avg CLV</th>
<th class="r">% positive CLV</th><th class="r">Flat-stake ROI</th>
{edge_headers}</tr>
{body}</table>
<p class="small" style="margin-top:10px">CLV (closing-line value) = de-vigged
closing win probability of our pick's side minus the de-vigged entry
probability of that side; positive means the market moved toward our pick
after we'd have logged it. ROI assumes a flat 1-unit bet at the entry
moneyline on every qualifying pick. The edge columns use the
pick-side-adjusted edge — model's probability on the side we picked minus
the market's vig-free closing probability on that same side — not the
home-referenced edge_vs_close column, so away picks aren't mis-filtered.
"Within N min of first pitch" restricts to picks whose closing line was
captured within that many minutes of the game's own first pitch (either
side); picks with no close_mins_before_start recorded are excluded from
that row but still included in the full sample. Meaningful only with
100+ settled picks; treat smaller samples — especially the high-edge
buckets — as noise.</p>
</div></div></body></html>"""
    out.write_text(html_doc, encoding="utf-8")
    return True
