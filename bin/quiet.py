"""Run a command and print only what matters: failures with context, plus a short tail.

Usage: python quiet.py <command...>      e.g.  python quiet.py npm test
Exit code is the command's own, so callers still see pass/fail.
Keeps test/lint/build output from flooding the context window.
"""
from __future__ import annotations

import re
import subprocess
import sys

MAX_LINES = 80
TAIL = 15        # on success
FAIL_TAIL = 5    # on failure: the summary line is usually at the end
BEFORE, AFTER = 2, 6
FAIL = re.compile(
    r"\b(fail(ed|ure|ing)?|error|errors|exception|traceback|assert(ion)?|panic|fatal|"
    r"expected|received|not ok|✗|✕|×)\b",
    re.I,
)


def failure_lines(lines: list[str]) -> list[str]:
    """Lines matching failure patterns, with a little context, de-duplicated and in order."""
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if FAIL.search(line):
            keep.update(range(max(0, i - BEFORE), min(len(lines), i + AFTER + 1)))
    out, prev = [], -2
    for i in sorted(keep):
        if i != prev + 1:
            out.append("  ...")
        out.append(lines[i])
        prev = i
    return out


def summarize(lines: list[str], code: int) -> list[str]:
    if code == 0:
        return lines[-TAIL:]
    tail = lines[-FAIL_TAIL:]
    room = MAX_LINES - FAIL_TAIL
    hits = failure_lines(lines[:-FAIL_TAIL] if len(lines) > FAIL_TAIL else [])
    if len(hits) > room:
        hits = hits[:room] + [f"  ... ({len(hits) - room} more failure lines cut)"]
    return hits + (["  --- last lines ---"] if hits else []) + tail


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmd = " ".join(sys.argv[1:])
    proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace")
    lines = proc.stdout.splitlines()
    status = "PASS" if proc.returncode == 0 else f"FAIL (exit {proc.returncode})"
    print(f"$ {cmd}  ->  {status}  [{len(lines)} lines of output, showing the relevant part]")
    print("\n".join(summarize(lines, proc.returncode)))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
