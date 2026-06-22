# MLB Postponement Alerts — Railway Deployment

Polls MLB's free official Stats API and sends a Telegram alert the first time
any game's status changes to **Postponed**. Pure Python standard library — no
dependencies to install.

## Files

| File | Purpose |
|------|---------|
| `mlb_postponement_alerts.py` | The alert script |
| `railway.toml` | Start command + cron schedule (every 5 min, UTC) |
| `requirements.txt` | Empty — just signals "this is a Python project" |
| `.python-version` | Pins Python 3.12 |

## Deploy steps

1. Push this folder to a GitHub repo (or run `railway up` from the folder with the Railway CLI).
2. In Railway, create a **New Service** from the repo. Nixpacks auto-detects Python.
3. Open the service → **Variables** tab → add:
   - `TELEGRAM_BOT_TOKEN` — your BotFather token
   - `TELEGRAM_CHAT_ID` — your chat ID
   - `MLB_ALERT_STATE` — set to `/data/alerted_games.json` (see volume note below)
4. The cron schedule (`*/5 * * * *`) and start command are already set in `railway.toml`.
   If you prefer the dashboard, they live under **Settings → Cron Schedule** and
   **Settings → Deploy → Custom Start Command**.

## Important: add a volume for dedupe state

Each cron run is a fresh container, so the `alerted_games.json` file that prevents
duplicate alerts would vanish between runs — you'd get re-alerted for the same
postponement every 5 minutes.

Fix: attach a Railway **Volume**, mount it at `/data`, and set
`MLB_ALERT_STATE=/data/alerted_games.json` (step 3 above). The script reads that
env var for its state path, so no code change is needed.

## Other notifiers (optional)

The script also supports email, Slack, and a generic webhook. Set the relevant
env vars in the Variables tab to enable any of them — see the docstring at the top
of `mlb_postponement_alerts.py`. If no notifier vars are set, alerts print to logs.

## Run mode note

`railway.toml` runs the script in **check-once-and-exit** mode (no `--loop`),
which is what Railway cron expects — the process must exit so the next scheduled
run isn't skipped. Don't add `--loop` for a cron service.
