"""HTML reports: per-game breakdown + daily slate dashboard."""
from __future__ import annotations

import html
from datetime import datetime

from .model import Prediction

CSS = """
:root{--bg:#0f1520;--card:#1a2332;--ink:#e8edf5;--dim:#8b98ac;--line:#2a3648;
--green:#37c977;--red:#e5605e;--accent:#4da3ff;--gold:#e8b23e}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,'Segoe UI',Roboto,Helvetica,sans-serif;
background:var(--bg);color:var(--ink);line-height:1.55;padding:24px}
.wrap{max-width:960px;margin:0 auto}
h1{font-size:26px;margin-bottom:2px}
h2{font-size:18px;margin:26px 0 10px}
.sub{color:var(--dim);font-size:14px;margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:18px 20px;margin-bottom:14px}
.pick{display:flex;justify-content:space-between;align-items:center;gap:16px;
flex-wrap:wrap}
.pick .team{font-size:22px;font-weight:700}
.pick .prob{font-size:38px;font-weight:800;color:var(--gold)}
.bar{height:14px;border-radius:7px;background:#2a3648;overflow:hidden;
margin:12px 0 6px;display:flex}
.bar .h{background:var(--accent)} .bar .a{background:var(--red)}
.legend{display:flex;justify-content:space-between;font-size:13px;color:var(--dim)}
table{width:100%;border-collapse:collapse;font-size:14px;margin-top:8px}
th{color:var(--dim);text-align:left;font-weight:600;font-size:12px;
text-transform:uppercase;letter-spacing:.04em}
th,td{padding:6px 10px;border-bottom:1px solid var(--line)}
tr:last-child td{border-bottom:none}
td.r,th.r{text-align:right;font-variant-numeric:tabular-nums}
.pos{color:var(--green)} .neg{color:var(--red)} .zero{color:var(--dim)}
.expl{color:var(--ink);font-size:14px;margin-top:10px}
.factor-head{display:flex;justify-content:space-between;align-items:baseline}
.contrib{font-weight:700;font-size:15px}
details{margin-top:10px}
summary{cursor:pointer;color:var(--accent);font-size:13px}
.small{font-size:12.5px;color:var(--dim)}
.meth p{color:var(--dim);font-size:13.5px;margin-bottom:8px}
.badge{display:inline-block;background:#243248;border-radius:6px;
padding:2px 8px;font-size:12px;color:var(--dim);margin-right:6px}
"""


def _cls(v: float) -> str:
    return "pos" if v > 0.001 else ("neg" if v < -0.001 else "zero")


def _esc(x) -> str:
    return html.escape(str(x))


def render(pred: Prediction, generated_at: str | None = None) -> str:
    home, away = pred.home["name"], pred.away["name"]
    ph = pred.p_home
    meta = pred.meta
    generated_at = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = []
    for f, pp in pred.contributions():
        rows.append(
            f"<tr><td>{_esc(f.name)}</td>"
            f"<td class='r {_cls(pp)}'>{pp:+.1f} pp</td>"
            f"<td class='r {_cls(f.edge)}'>{f.edge:+.3f}</td></tr>")
    factor_cards = "\n".join(_factor_card(f, pp) for f, pp in pred.contributions())

    lineup_html = ""
    for side, label in (("home", home), ("away", away)):
        lu = pred.lineups.get(side, [])
        if lu:
            body = "".join(
                f"<tr><td>{_esc(b['name'])}</td><td class='r'>{b['pa']}</td>"
                f"<td class='r'>{b['ops']:.3f}</td><td class='r'>{b['hr']}</td></tr>"
                for b in lu)
            lineup_html += (f"<details><summary>Projected lineup — {_esc(label)} "
                            f"(top 9 by PA)</summary><table>"
                            f"<tr><th>Player</th><th class='r'>PA</th>"
                            f"<th class='r'>OPS</th><th class='r'>HR</th></tr>"
                            f"{body}</table></details>")

    wx = meta.get("weather")
    wx_badge = (f"<span class='badge'>{wx['temp_f']:.0f}°F, wind "
                f"{wx['wind_mph']:.0f} mph {wx['wind_dir_label']}</span>") if wx else ""

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(away)} @ {_esc(home)} — prediction</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>{_esc(away)} @ {_esc(home)}</h1>
<div class="sub">{_esc(meta.get('venue','?'))} · {_esc(meta.get('game_date',''))}
 · {_esc(meta.get('day_night','?'))} game
 · SP: {_esc(meta.get('away_sp'))} vs {_esc(meta.get('home_sp'))}
 · generated {_esc(generated_at)}</div>

<div class="card pick">
  <div><div class="small">MODEL PICK ({_esc(pred.confidence)} confidence)</div>
  <div class="team">{_esc(pred.winner)}</div>
  {wx_badge}<span class="badge">park factor {_esc(meta.get('park_factor'))}</span>
  <span class="badge">roof: {_esc(meta.get('roof'))}</span></div>
  <div class="prob">{max(ph,1-ph):.1%}</div>
</div>
<div class="card">
  <div class="bar"><div class="h" style="width:{ph*100:.1f}%"></div>
  <div class="a" style="width:{(1-ph)*100:.1f}%"></div></div>
  <div class="legend"><span>{_esc(home)} {ph:.1%}</span>
  <span>{_esc(away)} {(1-ph):.1%}</span></div>
</div>

<h2>Factor summary</h2>
<div class="card">
<table><tr><th>Factor</th><th class="r">Effect on win prob.</th>
<th class="r">Log-odds edge</th></tr>
{''.join(rows)}
<tr><td><b>Total → P({_esc(home)} win)</b></td>
<td class="r"><b>{ph:.1%}</b></td>
<td class="r"><b>{meta.get('total_logodds',0):+.3f}</b></td></tr></table>
<p class="small" style="margin-top:8px">pp = percentage points of win
probability. Positive favors the home team, negative the visitors.</p>
</div>

<h2>Factor-by-factor breakdown</h2>
{factor_cards}

<h2>Projected lineups</h2>
<div class="card">{lineup_html or '<p class="small">Lineups unavailable.</p>'}</div>

<h2>Methodology</h2>
<div class="card meth">
<p><b>Model:</b> P(home win) = sigmoid(Σ factor edges). Each factor produces a
log-odds edge from public data, is multiplied by a fixed weight, and capped.
Weights are documented in config.py.</p>
<p><b>Data:</b> MLB Stats API (schedule, standings, splits, BvP, pitch
arsenals, rosters/IL), Baseball Savant leaderboards (Statcast batter
performance vs pitch type), Open-Meteo (game-time forecast). Park factors are
FanGraphs-style 3-year runs factors compiled in config.py.</p>
<p><b>Key ideas:</b> Pythagorean run differential; FIP starter comparison;
sample-shrunk BvP; lineup vs the starter's pitch mix & velocity (Statcast
wOBA by pitch type); wind decomposed along the park's center-field bearing;
injuries weighted by playing time.</p>
<p><b>Disclaimer:</b> for entertainment/research. Baseball is noisy — the best
teams lose ~40% of their games. Not betting advice.</p>
</div>
</div></body></html>"""


def render_slate(entries: list, date: str) -> str:
    rows = ""
    for e in entries:
        p = e.get("pred")
        if p is None:
            rows += (f"<tr><td>{_esc(e['label'])}</td><td colspan='4' "
                     f"class='small'>skipped: {_esc(e.get('error','no data'))}"
                     f"</td></tr>")
            continue
        pw = max(p.p_home, 1 - p.p_home)
        top = max(p.factors, key=lambda f: abs(f.edge))
        rows += (f"<tr><td><a style='color:var(--accent)' "
                 f"href='{_esc(e['file'])}'>{_esc(e['label'])}</a></td>"
                 f"<td>{_esc(p.meta.get('away_sp'))} vs "
                 f"{_esc(p.meta.get('home_sp'))}</td>"
                 f"<td><b>{_esc(p.winner)}</b></td>"
                 f"<td class='r'>{pw:.1%} ({_esc(p.confidence)})</td>"
                 f"<td class='small'>{_esc(top.name)}</td></tr>")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MLB picks — {_esc(date)}</title><style>{CSS}</style></head>
<body><div class="wrap"><h1>MLB model picks — {_esc(date)}</h1>
<div class="sub">Generated {_esc(datetime.now().strftime('%Y-%m-%d %H:%M'))}.
Click a matchup for the full numbers and factor-by-factor explanation.</div>
<div class="card"><table>
<tr><th>Matchup (away @ home)</th><th>Starters</th><th>Pick</th>
<th class="r">Win prob.</th><th>Biggest factor</th></tr>
{rows}</table></div>
<div class="card meth"><p>Every run pulls fresh data. Picks are auto-logged
to picks_log.csv and results fill in on the next run.
<a style="color:var(--accent)" href="../calibration.html">Calibration report
(actual vs predicted win% in 5% bands)</a>. For entertainment/research; not
betting advice.</p></div>
</div></body></html>"""


def _factor_card(f, pp: float) -> str:
    nums = ""
    if f.numbers:
        body = "".join(
            f"<tr><td>{_esc(n['label'])}</td><td class='r'>{_esc(n['home'])}</td>"
            f"<td class='r'>{_esc(n['away'])}</td></tr>" for n in f.numbers)
        nums = (f"<table><tr><th></th><th class='r'>Home</th>"
                f"<th class='r'>Away</th></tr>{body}</table>")
    detail = ""
    for d in (f.detail or []):
        if not d.get("rows"):
            continue
        kind = d.get("kind", "bvp")
        if kind == "arsenal":
            head = ("<tr><th>Pitch</th><th class='r'>Usage</th><th class='r'>Velo"
                    "</th><th class='r'>Lineup wOBA</th><th class='r'>Velo adj"
                    "</th><th class='r'>Sample PA</th></tr>")
            rows = "".join(
                f"<tr><td>{_esc(r['pitch'])}</td><td class='r'>{_esc(r['usage'])}</td>"
                f"<td class='r'>{_esc(r['velo'])}</td><td class='r'>{_esc(r['lineup_woba'])}</td>"
                f"<td class='r'>{_esc(r['velo_adj'])}</td><td class='r'>{_esc(r['pa'])}</td></tr>"
                for r in d["rows"])
        elif kind == "il":
            head = ("<tr><th>Player</th><th>Pos</th><th>Status</th>"
                    "<th class='r'>Usage</th><th class='r'>Impact</th></tr>")
            rows = "".join(
                f"<tr><td>{_esc(r['name'])}</td><td>{_esc(r['pos'])}</td>"
                f"<td>{_esc(r['status'])}</td><td class='r'>{_esc(r['usage'])}</td>"
                f"<td class='r'>{_esc(r['impact'])}</td></tr>" for r in d["rows"])
        else:
            head = ("<tr><th>Batter</th><th class='r'>PA</th><th class='r'>AVG"
                    "</th><th class='r'>OPS</th><th class='r'>HR</th>"
                    "<th class='r'>K</th></tr>")
            rows = "".join(
                f"<tr><td>{_esc(r['name'])}</td><td class='r'>{r['pa']}</td>"
                f"<td class='r'>{_esc(r['avg'])}</td><td class='r'>{_esc(r['ops'])}</td>"
                f"<td class='r'>{r['hr']}</td><td class='r'>{r['so']}</td></tr>"
                for r in d["rows"])
        detail += (f"<details><summary>{_esc(d['title'])}</summary>"
                   f"<table>{head}{rows}</table></details>")
    return f"""<div class="card">
<div class="factor-head"><h3>{_esc(f.name)}</h3>
<span class="contrib {_cls(pp)}">{pp:+.1f} pp</span></div>
{nums}<p class="expl">{_esc(f.explanation)}</p>{detail}</div>"""
