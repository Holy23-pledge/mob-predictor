# MLB Game Winner Predictor

A transparent statistical model that picks a winner for every MLB game and
shows every number and the explanation behind it — with automatic pick
tracking and a calibration report in 5% confidence bands.

## Three ways to run it

1. **On your Mac, one click a day**: double-click "Run Todays Slate.command"
   (first time: right-click -> Open).
2. **On your Mac, fully automatic**: double-click
   "Setup Automatic Morning Run.command" once; it then runs itself daily at
   10:00 AM whenever the Mac is on/awake.
3. **In the cloud, phone-friendly (computer can stay off)**: follow
   **PHONE_SETUP.md** to host it free on GitHub — it runs every morning on
   GitHub's servers and publishes the dashboard, pick log, and calibration
   report as a website you can open anywhere.

Requires Python 3.9+ (built into macOS; no installs needed).

## Command-line options

```bash
python3 predict.py --all                 # every game today -> dashboard + log
python3 predict.py --list                # just list the schedule
python3 predict.py --away Dodgers --home Yankees   # one matchup in depth
python3 predict.py --game 3 --date 2026-07-18      # by game number, any date
```

The .py files are source code — you don't open them like documents. The
results you read are the HTML files and picks_log.csv.

## Pick tracking & calibration

Every slate run appends picks to **picks_log.csv** and fills in actual
winners for earlier days automatically (final scores from the MLB API).
**calibration.html** (rebuilt each run, linked from the dashboard) shows,
for each 5% band (50-55, 55-60, 60-65, 65-70, 70-75, 75%+): picks, W-L,
actual win% vs predicted, and the difference. Confidence tiers:
strong >= 62%, moderate >= 55%, slight < 55%.

If, after a few hundred settled picks, most bands sit below their predicted
win%, lower GLOBAL_SHRINK in mlb_predictor/config.py (1.0 -> ~0.75).

## The model

P(home win) = sigmoid( GLOBAL_SHRINK x sum of 9 factor edges ), a weighted
logistic combination. Each factor computes a log-odds edge from public data,
gets a fixed documented weight, and is capped. Weights live in
mlb_predictor/config.py.

| # | Factor | What it measures |
|---|--------|------------------|
| 1 | Season performance | Pythagorean expectation from runs scored/allowed |
| 2 | Home vs away | ~54% home baseline + each club's home/road split vs its own level |
| 3 | Starting pitching | FIP gap between the probable starters over ~6 IP |
| 4 | Batter vs pitcher history | Lineup's career PA/OPS vs the exact opposing starter, sample-shrunk |
| 5 | Lineup vs pitch-mix | Statcast wOBA vs the starter's pitch types, usage-weighted, velo-adjusted |
| 6 | Weather & wind | Wind decomposed along the park's CF bearing; roofed parks neutral |
| 7 | Time of day | Day/night split records relative to overall level |
| 8 | Stadium | Park factor interacting with the offensive gap + home record there |
| 9 | Injuries | IL lists weighted by each player's playing time |

## Data sources

MLB Stats API (statsapi.mlb.com — schedule, standings/splits, player stats,
BvP, Statcast pitch arsenals, rosters/IL, final scores), Baseball Savant
leaderboards (batter vs pitch type), Open-Meteo (weather). Park factors:
FanGraphs-style 3-year runs factors embedded in config.py. Responses cached
1 hour in data_cache/; the daily schedule is always fetched fresh.

## Files

```
predict.py                        CLI entry point
Run Todays Slate.command          double-click daily runner (Mac)
Setup Automatic Morning Run.command  one-time Mac auto-schedule installer
PHONE_SETUP.md                    free cloud + phone setup (GitHub)
github-workflow-daily.yml         the cloud schedule (copy for GitHub setup)
picks_log.csv                     auto-maintained pick history
calibration.html                  actual vs predicted win% in 5% bands
mlb_predictor/                    the model's source code (9 factors etc.)
```

Disclaimer: research/entertainment tool. Baseball is high-variance; even
great teams lose ~40% of the time. Not betting advice.
