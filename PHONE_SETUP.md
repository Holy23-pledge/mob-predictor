# Use the predictor from your phone (no computer needed)

One-time setup, ~15 minutes, all free. After this, GitHub's servers run the
predictor every morning, keep picks_log.csv updated, and host a website you
can open on your phone from anywhere. Your computer can stay off for weeks.

## Step 1 — Create a free GitHub account
Go to **github.com** and sign up (free plan is fine).

## Step 2 — Create the repository
1. Click the **+** (top right) → **New repository**
2. Name it exactly: `mlb-predictor`
3. Set it to **Public** (required for the free website)
4. Click **Create repository**

## Step 3 — Upload the app
1. On the new repo page, click **"uploading an existing file"**
2. On your Mac, open the mlb-predictor folder, select ALL the files and
   folders inside it (Cmd+A), and drag them into the browser window.
   (If `picks_log.csv` exists, include it — your history carries over.)
3. Click **Commit changes** and wait for the upload to finish.

## Step 4 — Add the automatic daily run
The `.github` folder usually doesn't survive drag-and-drop (Mac hides it),
so add the schedule by hand:
1. In the repo, click **Actions** (top menu) → **set up a workflow yourself**
2. Delete the sample text and paste in the entire contents of the file
   `.github/workflows/daily.yml` from this folder (open it with TextEdit)
3. Click **Commit changes**
4. Still under Actions: click **Daily MLB picks** → **Run workflow** →
   green **Run workflow** button. Wait ~3 minutes; it should show a green
   check. This was your first cloud run.

## Step 5 — Turn on the phone website
1. In the repo: **Settings** → **Pages** (left sidebar)
2. Under "Build and deployment": Source = **Deploy from a branch**,
   Branch = **main**, folder = **/ (root)** → **Save**
3. Wait ~2 minutes. Your site is at:

   **https://YOURUSERNAME.github.io/mlb-predictor/today/**

   (replace YOURUSERNAME with your GitHub username)

## Step 6 — Put it on your phone's home screen
Open that link in Safari on your iPhone → Share button → **Add to Home
Screen**. Now it's one tap, like an app.

- Today's picks: `.../mlb-predictor/today/`
- Calibration report: `.../mlb-predictor/calibration.html`
- Pick log: open the repo on your phone and tap `picks_log.csv`

## Step 7 — (Optional) Track the model against real market odds
1. Get a free API key at **the-odds-api.com** (500 requests/month, no card
   needed).
2. In the repo: **Settings** → **Secrets and variables** → **Actions** →
   **New repository secret**.
3. Name it exactly `ODDS_API_KEY`, paste your key, **Add secret**.
4. That's it — the morning run now logs the market's opening moneyline, and
   a second run in the evening (already scheduled in the workflow) captures
   the closing line. Once picks settle, `market.html` shows how the model
   compares to the market (closing-line value and ROI vs. a flat bet).

## Good to know
- Runs daily at 10:00 AM Eastern (change the `cron` line in the workflow to
  adjust; times are in UTC, so 14 = 10 AM ET).
- You can force a fresh run anytime from your phone: repo → Actions →
  Daily MLB picks → Run workflow.
- **Use ONE tracker**: once this is set up, let GitHub own picks_log.csv.
  Turn off the Mac's morning schedule so the two don't drift apart:
  `launchctl unload ~/Library/LaunchAgents/com.mlb-predictor.daily.plist`
- GitHub pauses schedules if a repo sees no human activity for 60 days —
  just open the site or the repo occasionally and it keeps running.
