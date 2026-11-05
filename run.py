#!/usr/bin/env python3
"""Run the UZEX AI agent: web app (FastAPI) and/or Telegram bot, with auto-restart.

    python run.py                 # web + bot (bot only if TELEGRAM_BOT_TOKEN is set)
    python run.py --web           # only the web app
    python run.py --bot           # only the Telegram bot
    python run.py --port 9000     # web port (default 8000, or $PORT)
    python run.py --check         # build DB if needed, run smoke tests, exit
    python run.py --stop          # stop every running bot and web process (and supervisors)

Children are restarted if they crash (with back-off). Ctrl+C / SIGTERM stops everything.
Logs: logs/web.out, logs/bot.out, logs/qa.jsonl.
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGS = ROOT / "logs"
PY = sys.executable


def log(msg: str) -> None:
    print(f"[run {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_env() -> dict[str, str]:
    env = dict(os.environ)
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env.setdefault(key.strip(), value.strip())
    env["PYTHONUNBUFFERED"] = "1"
    return env


def ensure_db(env: dict[str, str]) -> None:
    db = Path(env.get("DB_PATH", "data/uzex.duckdb"))
    db = db if db.is_absolute() else ROOT / db
    if db.exists():
        return
    log(f"database not found ({db}); building it from CSV (1-2 min)...")
    subprocess.run([PY, "scripts/build_db.py"], cwd=ROOT, env=env, check=True)


def other_bot_running() -> list[str]:
    """PIDs of running `python -m app.bot` processes (Telegram allows one poller per token)."""
    try:
        out = subprocess.run(["pgrep", "-f", r"[Pp]ython.* -m app\.bot"], capture_output=True, text=True).stdout
    except (FileNotFoundError, OSError):
        return []
    return [pid for pid in out.split() if pid != str(os.getpid())]


SUPERVISOR_RE = re.compile(r"""(^|[\\/\s"'])run\.py(["'\s]|$)""")
CHILD_RES = [re.compile(r"-m\s+app\.bot(\s|$)"), re.compile(r"uvicorn\s+app\.api:app")]


def list_processes() -> list[tuple[int, str]]:
    """(pid, command line) of every process; works on Windows and POSIX."""
    try:
        if os.name == "nt":
            ps = ('Get-CimInstance Win32_Process | ForEach-Object '
                  '{ "$($_.ProcessId)`t$($_.CommandLine)" }')
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
            rows = [line.split("\t", 1) for line in out.splitlines() if "\t" in line]
        else:
            out = subprocess.run(["ps", "-eo", "pid=,args="], capture_output=True, text=True).stdout
            rows = [line.strip().split(None, 1) for line in out.splitlines() if line.strip()]
    except (FileNotFoundError, OSError):
        return []
    result = []
    for row in rows:
        if len(row) == 2 and row[0].strip().isdigit():
            result.append((int(row[0]), row[1]))
    return result


def _kill(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def stop_all() -> int:
    """Stop every run.py supervisor, bot (python -m app.bot) and web (uvicorn app.api) process.

    Supervisors go first, otherwise they would restart the children we kill.
    """
    me = {os.getpid(), os.getppid()}
    procs = [(pid, cmd) for pid, cmd in list_processes() if pid not in me]
    supervisors = [(p, c) for p, c in procs if SUPERVISOR_RE.search(c) and "--stop" not in c]
    children = [(p, c) for p, c in procs if any(r.search(c) for r in CHILD_RES)]
    if not supervisors and not children:
        log("nothing to stop: no bot or web process is running")
        return 0
    for group in (supervisors, children):
        for pid, cmd in group:
            log(f"stopping pid {pid}: {cmd[:90]}")
            _kill(pid)
        time.sleep(1)
    time.sleep(1)
    alive = {pid for pid, _ in list_processes()}
    left = [pid for pid, _ in supervisors + children if pid in alive]
    if left:
        log(f"still running: {', '.join(map(str, left))}")
        return 1
    log("all bot and web processes stopped")
    return 0


class Child:
    def __init__(self, name: str, cmd: list[str], env: dict[str, str]):
        self.name, self.cmd, self.env = name, cmd, env
        self.proc: subprocess.Popen | None = None
        self.restarts = 0
        self.started_at = 0.0
        self.next_start = 0.0

    def start(self) -> None:
        LOGS.mkdir(exist_ok=True)
        out = open(LOGS / f"{self.name}.out", "a", encoding="utf-8")
        out.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} start {' '.join(self.cmd[1:])} =====\n")
        out.flush()
        self.proc = subprocess.Popen(self.cmd, cwd=ROOT, env=self.env, stdout=out, stderr=subprocess.STDOUT)
        self.started_at = time.monotonic()
        log(f"{self.name}: started (pid {self.proc.pid}), log: logs/{self.name}.out")

    def poll(self) -> None:
        now = time.monotonic()
        if self.proc is None:
            if now >= self.next_start:
                self.start()
            return
        code = self.proc.poll()
        if code is None:
            if now - self.started_at > 300:
                self.restarts = 0  # stable for 5 min -> reset back-off
            return
        self.restarts += 1
        delay = min(60, 2 ** min(self.restarts, 6))
        log(f"{self.name}: exited with code {code}; restart #{self.restarts} in {delay}s")
        self.proc = None
        self.next_start = now + delay

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            log(f"{self.name}: stopped")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the UZEX AI agent")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--web", action="store_true", help="only the web app")
    mode.add_argument("--bot", action="store_true", help="only the Telegram bot")
    mode.add_argument("--check", action="store_true", help="build DB if needed, run tests, exit")
    mode.add_argument("--stop", action="store_true", help="stop all running bot and web processes, exit")
    ap.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    args = ap.parse_args()

    if args.stop:
        return stop_all()

    os.chdir(ROOT)
    env = load_env()
    ensure_db(env)

    if args.check:
        code = subprocess.run([PY, "scripts/smoke_test.py"], cwd=ROOT, env=env).returncode
        code |= subprocess.run([PY, "scripts/eval.py"], cwd=ROOT, env=env).returncode
        return code

    want_web = not args.bot
    want_bot = not args.web
    children: list[Child] = []

    if want_web:
        children.append(Child("web", [PY, "-m", "uvicorn", "app.api:app", "--host", args.host,
                                      "--port", str(args.port)], env))
    if want_bot:
        if not env.get("TELEGRAM_BOT_TOKEN"):
            log("bot: TELEGRAM_BOT_TOKEN is empty in .env — bot is not started")
            if args.bot:
                return 1
        else:
            others = other_bot_running()
            if others:
                log(f"bot: another bot instance is already running (pid {', '.join(others)}). "
                    "Telegram allows only one — stop it first (kill <pid>). Bot is not started.")
                if args.bot:
                    return 1
            else:
                children.append(Child("bot", [PY, "-m", "app.bot"], env))

    if not children:
        log("nothing to run")
        return 1

    stopping = False

    def handle_signal(signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if want_web:
        log(f"web: http://localhost:{args.port}/   (health: /health, API: POST /ask)")
    log("press Ctrl+C to stop")
    while not stopping:
        for child in children:
            child.poll()
        time.sleep(1)

    log("stopping...")
    for child in children:
        child.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
