#!/usr/bin/env python3
"""
MLB Postponement Alert System
==============================
Polls MLB's free official Stats API (no key required) and sends an alert
the first time any game's status changes to "Postponed".

Usage:
    python mlb_postponement_alerts.py                # run once (e.g. from cron)
    python mlb_postponement_alerts.py --loop 300     # poll every 300 seconds

Configure notifications via environment variables (any subset):
    EMAIL  : SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_FROM, ALERT_TO
    SLACK  : SLACK_WEBHOOK_URL
    WEBHOOK: GENERIC_WEBHOOK_URL   (POSTs the raw JSON payload)
    TELEGRAM: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
If none are set, alerts are printed to stdout.
"""

import argparse
import json
import os
import smtplib
import sys
import time
import urllib.request
from datetime import datetime, timezone
from email.mime.text import MIMEText

SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}"
STATE_FILE = os.environ.get("MLB_ALERT_STATE", "alerted_games.json")
# MLB reports postponed games with detailedState "Postponed" (codedGameState "D").
POSTPONED_STATES = {"Postponed"}


def fetch_games(date_str):
    url = SCHEDULE_URL.format(date=date_str)
    req = urllib.request.Request(url, headers={"User-Agent": "mlb-postpone-alert/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    games = []
    for d in data.get("dates", []):
        games.extend(d.get("games", []))
    return games


def load_alerted():
    try:
        with open(STATE_FILE) as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_alerted(ids):
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(ids), f)


def build_message(game):
    teams = game.get("teams", {})
    away = teams.get("away", {}).get("team", {}).get("name", "Away")
    home = teams.get("home", {}).get("team", {}).get("name", "Home")
    dt = game.get("gameDate", "")
    reason = game.get("status", {}).get("reason", "")
    venue = game.get("venue", {}).get("name", "")
    line = f"⚾ POSTPONED: {away} @ {home}"
    details = f"Scheduled: {dt}" + (f" | {venue}" if venue else "")
    if reason:
        details += f" | Reason: {reason}"
    return line, details


# ---------- notification channels ----------

def notify_email(subject, body):
    host = os.environ.get("SMTP_HOST")
    if not host:
        return False
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = os.environ["ALERT_FROM"]
    msg["To"] = os.environ["ALERT_TO"]
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", 587))) as s:
        s.starttls()
        if os.environ.get("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)
    return True


def _post_json(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=30).read()


def notify_slack(text):
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return False
    _post_json(url, {"text": text})
    return True


def notify_webhook(payload):
    url = os.environ.get("GENERIC_WEBHOOK_URL")
    if not url:
        return False
    _post_json(url, payload)
    return True


def notify_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    _post_json(url, {"chat_id": chat_id, "text": text})
    return True


def dispatch(game):
    line, details = build_message(game)
    body = f"{line}\n{details}"
    sent = False
    sent |= notify_email("MLB Game Postponed", body)
    sent |= notify_slack(body)
    sent |= notify_webhook({"game_pk": game.get("gamePk"), "message": body, "game": game})
    sent |= notify_telegram(body)
    if not sent:
        print(f"[{datetime.now(timezone.utc).isoformat()}] {body}\n")


# ---------- main check ----------

def check_once():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    alerted = load_alerted()
    new_alerts = 0
    for game in fetch_games(today):
        state = game.get("status", {}).get("detailedState", "")
        pk = game.get("gamePk")
        if state in POSTPONED_STATES and pk not in alerted:
            dispatch(game)
            alerted.add(pk)
            new_alerts += 1
    save_alerted(alerted)
    return new_alerts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, metavar="SECONDS",
                    help="poll continuously every N seconds instead of running once")
    args = ap.parse_args()

    if args.loop:
        print(f"Polling every {args.loop}s. Ctrl-C to stop.", file=sys.stderr)
        while True:
            try:
                n = check_once()
                if n:
                    print(f"Sent {n} new alert(s).", file=sys.stderr)
            except Exception as e:  # keep the loop alive on transient errors
                print(f"Error: {e}", file=sys.stderr)
            time.sleep(args.loop)
    else:
        check_once()


if __name__ == "__main__":
    main()
