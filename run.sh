#!/usr/bin/env bash
# UZEX AI agent launcher: prepares the environment, then starts run.py.
#
#   ./run.sh              # web + Telegram bot (bot only if TELEGRAM_BOT_TOKEN is set)
#   ./run.sh --web        # only the web app      (http://localhost:8000)
#   ./run.sh --bot        # only the Telegram bot
#   ./run.sh --port 9000  # another web port
#   ./run.sh --check      # build DB if needed + smoke tests + eval
#   ./run.sh --bg         # run in background (nohup), logs in logs/run.out
#   ./run.sh --stop       # stop the background launcher started with --bg
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
VENV="$ROOT/.venv"
PIDFILE="$ROOT/logs/run.pid"
mkdir -p "$ROOT/logs"

if [[ "${1:-}" == "--stop" ]]; then
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")" && rm -f "$PIDFILE" && echo "stopped"
  else
    echo "no background launcher running"
  fi
  exit 0
fi

# 1. Python virtualenv
if [[ ! -x "$VENV/bin/python" ]]; then
  PYTHON_BIN="$(command -v python3.12 || command -v python3 || true)"
  if [[ -z "$PYTHON_BIN" ]]; then
    echo "Python 3 not found. Install Python 3.11+ first." >&2
    exit 1
  fi
  echo "[run.sh] creating virtualenv with $PYTHON_BIN"
  "$PYTHON_BIN" -m venv "$VENV"
fi

# 2. Dependencies (re-installed only when requirements.txt changes)
STAMP="$VENV/.requirements.sha"
REQ_SHA="$(shasum requirements.txt | awk '{print $1}')"
if [[ ! -f "$STAMP" || "$(cat "$STAMP")" != "$REQ_SHA" ]]; then
  echo "[run.sh] installing dependencies"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r requirements.txt
  echo "$REQ_SHA" > "$STAMP"
fi

# 3. Config
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "[run.sh] created .env from .env.example — set TELEGRAM_BOT_TOKEN (and LLM_*) there"
fi

# 4. Start (run.py builds the DuckDB database on first start)
if [[ "${1:-}" == "--bg" ]]; then
  shift
  nohup "$VENV/bin/python" run.py "$@" >> "$ROOT/logs/run.out" 2>&1 &
  echo $! > "$PIDFILE"
  echo "[run.sh] started in background (pid $!). Logs: logs/run.out, logs/web.out, logs/bot.out"
  echo "[run.sh] stop with: ./run.sh --stop"
  exit 0
fi

exec "$VENV/bin/python" run.py "$@"
