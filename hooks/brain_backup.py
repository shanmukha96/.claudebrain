"""SessionStart hook (startup|resume): weekly backup commit of the brain repo.

Checks the last commit date; if BRAIN_BACKUP_DAYS (default 7) have passed and something
changed, commits everything locally. Never pushes. Prints a one-line report into context.
"""
from __future__ import annotations

import sys
from datetime import date

from brainlib import backup_if_due


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.read()  # hook input not needed
    print(backup_if_due(date.today()))


if __name__ == "__main__":
    main()
