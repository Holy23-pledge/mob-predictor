#!/usr/bin/env python3
"""MLB game winner predictor.

Usage:
  python predict.py --all [--date YYYY-MM-DD]        # every game today
  python predict.py --list [--date YYYY-MM-DD]
  python predict.py --away Dodgers --home Yankees [--date YYYY-MM-DD]
  python predict.py --game 3 [--date YYYY-MM-DD]     # game # from --list
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as _date
from pathlib import Path

from mlb_predictor import fetch, tracker
from mlb_predictor import mlb_api as api
from mlb_predictor.model import predict_game
from mlb_predictor.report import render, render_slate

VERSION = "1.5"


def pick_game(games: list[dict], args) -> dict:
    if args.game is not None:
        if not (1 <= args.game <= len(games)):
            sys.exit(f"--game must be 1..{len(games)}")
        return games[args.game - 1]
    if args.home or args.away:
        q_home = (args.home or "").lower()
        q_away = (args.away or "").lower()
        for g in games:
            hn = g["teams"]["home"]["team"]["name"].lower()
            an = g["teams"]["away"]["team"]["name"].lower()
            if (not q_home or q_home in hn) and (not q_away or q_away in an):
                return g
        sys.exit("No game on that date matches those teams. Try --list.")
    sys.exit("Specify a matchup: --home/--away, or --game N, or use --list, "
             "or --all for the whole slate.")


def list_games(games: list[dict]) -> None:
    if not games:
        print("No MLB games scheduled that date.")
        return
    for i, g in enumerate(games, 1):
        a, h = g["teams"]["away"], g["teams"]["home"]
        asp = a.get("probablePitcher", {}).get("fullName", "TBD")
        hsp = h.get("probablePitcher", {}).get("fullName", "TBD")
        print(f"{i:2d}. {a['team']['name']} @ {h['team']['name']}"
              f"  [{g.get('dayNight','?')}, {g.get('venue',{}).get('name','?')}]"
              f"  {asp} vs {hsp}")


def run_slate(games: list[dict], season: int, args) -> None:
    if not games:
        print("No MLB games scheduled that date.")
        return
    print(f"Found {len(games)} game(s) scheduled for {args.date}.")
    if len(games) <= 2:
        print("  (If that looks low, MLB may have an off/travel day — check "
              "the date, or your internet connection.)")
    outdir = Path(args.out or f"slate_{args.date}")
    outdir.mkdir(parents=True, exist_ok=True)
    entries = []
    for i, g in enumerate(games, 1):
        a = g["teams"]["away"]["team"]["name"]
        h = g["teams"]["home"]["team"]["name"]
        label = f"{a} @ {h}"
        fname = f"{i:02d}_{a.split()[-1]}_at_{h.split()[-1]}.html"
        print(f"[{i}/{len(games)}] {label} ...", flush=True)
        try:
            pred = predict_game(g, season)
            (outdir / fname).write_text(render(pred), encoding="utf-8")
            pw = max(pred.p_home, 1 - pred.p_home)
            print(f"    PICK: {pred.winner} ({pw:.1%}, {pred.confidence})")
            entries.append({"pred": pred, "file": fname, "label": label})
        except Exception as exc:
            print(f"    skipped: {exc}")
            entries.append({"pred": None, "file": fname, "label": label,
                            "error": str(exc)})
    index = outdir / "index.html"
    index.write_text(render_slate(entries, args.date), encoding="utf-8")
    print(f"\nSlate dashboard: {index}")

    log = Path("picks_log.csv")
    try:
        n = tracker.settle(log, args.date)
        if n:
            print(f"Filled in final results for {n} earlier pick(s).")
    except Exception as exc:
        print(f"(couldn't settle earlier picks this run: {exc})")

    tracker.record(log, args.date,
                   [e["pred"] for e in entries if e.get("pred")])
    tracker.print_summary(log)
    if tracker.write_calibration_html(log, Path("calibration.html")):
        print("Calibration report (5% bands): calibration.html")
    if tracker.write_market_report_html(log, Path("market.html")):
        print("Market benchmark (CLV & ROI vs. the closing line): market.html")


def main() -> None:
    p = argparse.ArgumentParser(description="Predict an MLB game winner")
    p.add_argument("--date", default=str(_date.today()))
    p.add_argument("--home")
    p.add_argument("--away")
    p.add_argument("--game", type=int)
    p.add_argument("--all", action="store_true",
                   help="predict every game on the slate")
    p.add_argument("--list", action="store_true")
    p.add_argument("--out", default=None, help="output HTML path")
    p.add_argument("--cache-only", action="store_true")
    p.add_argument("--closing", action="store_true",
                   help="capture closing-line odds for today's already-"
                        "logged picks; run this again near first pitch")
    args = p.parse_args()

    if args.cache_only:
        fetch.CACHE_ONLY = True

    if args.closing:
        log = Path("picks_log.csv")
        n = tracker.capture_closing(log, args.date)
        print(f"Captured closing odds for {n} game(s)." if n else
              "No closing odds captured (set ODDS_API_KEY, or no BetMGM "
              "lines posted yet for today's picks).")
        if tracker.write_market_report_html(log, Path("market.html")):
            print("Market benchmark refreshed: market.html")
        return

    season = int(args.date[:4])
    print(f"mlb-predictor v{VERSION} — fetching schedule for {args.date} ...")
    try:
        games = api.schedule(args.date)
    except Exception as exc:
        sys.exit(f"\nERROR: could not download the MLB schedule.\n"
                 f"  Reason: {exc}\n"
                 f"  Check your internet connection and run it again.")

    if args.list:
        list_games(games)
        return

    if args.all:
        run_slate(games, season, args)
        return

    game = pick_game(games, args)
    a = game["teams"]["away"]["team"]["name"]
    h = game["teams"]["home"]["team"]["name"]
    print(f"Analyzing {a} @ {h} ({args.date}) ...")
    pred = predict_game(game, season)

    print("=" * 62)
    print(f"PICK: {pred.winner}  "
          f"({max(pred.p_home, 1-pred.p_home):.1%}, {pred.confidence} confidence)")
    print(f"P({h} win) = {pred.p_home:.1%}")
    print("-" * 62)
    for f, pp in pred.contributions():
        print(f"{f.name:<38} {pp:+6.1f} pp")
    print("=" * 62)

    out = args.out or f"prediction_{args.date}_{a.split()[-1]}_at_{h.split()[-1]}.html"
    Path(out).write_text(render(pred), encoding="utf-8")
    print(f"Full report with numbers & explanations: {out}")


if __name__ == "__main__":
    main()
