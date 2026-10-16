"""Shared helpers for the brain-level hooks: retro reminders, day-change retro, weekly backup commit.

Pure decisions (is it due?) are separate from I/O (state files, git) so each can be tested alone.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import date, timedelta
from pathlib import Path

BRAIN = Path(__file__).resolve().parent.parent
STATE_DIR = Path.home() / ".claude" / "brain-state"
RETRO_EVERY = int(os.environ.get("BRAIN_RETRO_EVERY", "10"))
BACKUP_EVERY_DAYS = int(os.environ.get("BRAIN_BACKUP_DAYS", "7"))


# ---- pure logic ----

def reminder_due(count: int, every: int = RETRO_EVERY) -> bool:
    """True on every `every`-th message since the last retro."""
    return every > 0 and count > 0 and count % every == 0


def day_changed(last: str | None, today: date) -> bool:
    return last is not None and last != today.isoformat()


def backup_due(last_commit: date | None, today: date, days: int = BACKUP_EVERY_DAYS) -> bool:
    return last_commit is None or today >= last_commit + timedelta(days=days)


def next_backup(last_commit: date | None, days: int = BACKUP_EVERY_DAYS) -> date | None:
    return last_commit + timedelta(days=days) if last_commit else None


# ---- per-session state ----

def load_state(session_id: str) -> dict:
    try:
        return json.loads((STATE_DIR / f"{session_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(session_id: str, state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / f"{session_id}.json").write_text(json.dumps(state), encoding="utf-8")


# ---- git backup of the brain repo (never pushes) ----

def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(BRAIN), *args], capture_output=True, text=True, timeout=30)


def last_commit_date() -> date | None:
    out = _git("log", "-1", "--format=%cs").stdout.strip()
    try:
        return date.fromisoformat(out)
    except ValueError:
        return None


def backup_if_due(today: date) -> str:
    """Commit the whole brain repo if the backup is due and there are changes. Returns a one-line report."""
    last = last_commit_date()
    if not backup_due(last, today):
        return f"brain backup: not due (last commit {last}, next {next_backup(last)})"
    if not _git("status", "--porcelain").stdout.strip():
        return f"brain backup: due but nothing changed since {last}"
    _git("add", "-A")
    done = _git("commit", "-q", "-m", f"mem: weekly backup {today.isoformat()}")
    if done.returncode != 0:
        return f"brain backup: FAILED, tell the user: {(done.stderr or done.stdout).strip()[:200]}"
    head = _git("log", "-1", "--format=%h").stdout.strip()
    return f"brain backup: committed {head} ({today.isoformat()}), next due {next_backup(today)}. Tell the user."
