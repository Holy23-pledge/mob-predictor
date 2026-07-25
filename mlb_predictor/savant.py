"""Baseball Savant leaderboard client: batters' Statcast performance vs
every pitch type. Powers the 'hitters vs similar pitchers' factor."""
from __future__ import annotations

import csv
import io

from . import fetch

URL = ("https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats"
       "?type=batter&pitchType={pt}&year={year}&team={team}&min=1&csv=true")

PITCH_TYPES = ["FF", "SI", "FC", "SL", "ST", "CU", "KC", "CH", "FS", "SV"]

CODE_ALIAS = {"KC": "CU", "SV": "SL", "CS": "CU", "FO": "FS", "FT": "SI"}


def batter_vs_pitchtype(team_abbrev: str, year: int) -> dict[int, dict[str, dict]]:
    out: dict[int, dict[str, dict]] = {}
    texts = []
    try:
        texts.append(fetch.get_text(URL.format(pt="", year=year, team=team_abbrev),
                                    ext=".csv"))
    except Exception:
        pass
    if not texts or _row_count(texts[0]) < 5:
        texts = []
        for pt in PITCH_TYPES:
            try:
                texts.append(fetch.get_text(
                    URL.format(pt=pt, year=year, team=team_abbrev), ext=".csv"))
            except Exception:
                continue
    for text in texts:
        for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
            try:
                pid = int(row["player_id"])
                code = row["pitch_type"].strip()
                out.setdefault(pid, {})[code] = {
                    "woba": float(row["woba"]) if row["woba"] else None,
                    "est_woba": float(row["est_woba"]) if row.get("est_woba") else None,
                    "pa": int(row["pa"]) if row["pa"] else 0,
                    "whiff": float(row["whiff_percent"]) if row.get("whiff_percent") else None,
                    "rv100": float(row["run_value_per_100"]) if row.get("run_value_per_100") else None,
                }
            except (KeyError, ValueError):
                continue
    return out


def _row_count(text: str) -> int:
    return max(0, len(text.strip().splitlines()) - 1)
