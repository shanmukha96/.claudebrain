"""PreToolUse gate on the Agent tool: do not launch a new wave of work while the
last reviewed commit is behind a HEAD that contains code changes.

Why this exists as a HOOK and not a rule. "Run /review-changes before briefing
the next agents" was written in CLAUDE.md, then broken four times, the last time
within hours of writing the stronger wording. The things that actually catch
this on this project are mechanical - the verify gate and the stop hook - so
this is the mechanical version.

It deliberately does NOT block:
  - the `reviewer` agent, which is how the block gets cleared;
  - read-only search agents (explorer / Explore / Plan), which cannot make the
    backlog worse;
  - a project with no REVIEW.md, or a "Last reviewed" ref git does not know
    (a fresh project would otherwise be unable to launch anything);
  - a HEAD whose diff from the reviewed ref touches no code.

Escape hatch: set BRAIN_SKIP_REVIEW_GATE=1 for one session when a launch is
genuinely more urgent than the review.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Claude Code normally puts the script's own directory on sys.path, but not under
# `python -I`, which is how this gets tested. Be explicit so both work.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memlib import is_code, memory_dir, read  # noqa: E402

# Agent types that may always launch: they either clear the backlog or only read.
ALWAYS_ALLOWED = {"reviewer", "explorer", "explore", "plan"}


def git(*args: str, cwd=None, timeout: float = 10) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, timeout=timeout, cwd=cwd
    )


def reviewed_ref(mem) -> str | None:
    """The ref REVIEW.md claims was last reviewed, or None if there isn't one."""
    text = read(mem / "REVIEW.md")
    if not text:
        return None
    m = re.search(r"^-\s*ref:\s*(\S+)", text, re.M)
    if not m:
        return None
    ref = m.group(1).strip()
    return None if ref.lower() in {"none", "-", "n/a", "tbd"} else ref


def unreviewed_code_files(ref: str, cwd=None, run=git) -> list[str]:
    """Code files changed between `ref` and HEAD, or [] if that can't be told.

    `run` is the git runner. The default is this module's git(); memrot passes one that enforces
    a wall-clock budget, because there the three calls below must fit inside a SessionStart timeout."""
    if run("cat-file", "-e", f"{ref}^{{commit}}", cwd=cwd).returncode != 0:
        return []  # a ref git does not know: cannot compare, so do not block
    head = run("rev-parse", "HEAD", cwd=cwd)
    if head.returncode != 0:
        return []
    diff = run("diff", "--name-only", f"{ref}..HEAD", cwd=cwd)
    if diff.returncode != 0:
        return []
    return [p for p in diff.stdout.split("\n") if p.strip() and is_code(p)]


def main() -> None:
    if os.environ.get("BRAIN_SKIP_REVIEW_GATE") == "1":
        return
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    if data.get("tool_name") != "Agent":
        return

    tool_input = data.get("tool_input") or {}
    subagent = str(tool_input.get("subagent_type") or "").strip().lower()
    if subagent in ALWAYS_ALLOWED:
        return

    mem = memory_dir()
    if mem is None:
        return
    ref = reviewed_ref(mem)
    if ref is None:
        return

    pending = unreviewed_code_files(ref)
    if not pending:
        return

    shown = ", ".join(pending[:5])
    more = f" (+{len(pending) - 5} more)" if len(pending) > 5 else ""
    head = git("rev-parse", "--short", "HEAD").stdout.strip() or "HEAD"
    reason = (
        f"Review gate: REVIEW.md's last reviewed ref is {ref}, but HEAD ({head}) has "
        f"{len(pending)} changed code file(s) nobody has reviewed: {shown}{more}. "
        "Run /review-changes first, then update REVIEW.md's 'Last reviewed' ref — "
        "that is what clears this. The `reviewer` agent and read-only search agents "
        "are never blocked. If this launch is genuinely more urgent than the review, "
        "say so to the user and set BRAIN_SKIP_REVIEW_GATE=1 for this session."
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


if __name__ == "__main__":
    main()
