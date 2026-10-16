"""PostToolUse hook (Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell).

Tracks one counter in .claude/memory/ for the verify gate:
  .unverified  code edits INSIDE THE PROJECT TREE since the project's verify command last ran
Files outside the project (a Python script in a temp/scratchpad folder, anything in another repo)
are not project code and never count. Whether memory itself was updated is not tracked here:
memory_stop.py compares content hashes of the memory files at the end of each turn.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Claude Code normally puts the script's own directory on sys.path, but not under `python -I`,
# which is how this gets tested. Be explicit so both work (same as review_gate.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memlib import bump, in_project, in_tree, is_code, memory_dir, verify_pattern  # noqa: E402

SHELL_TOOLS = ("Bash", "PowerShell")


def counts_as_project_code(path: str, scratchpad: str = "") -> bool:
    """A code file inside the project tree, not in memory and not in the session scratchpad.

    `scratchpad` comes from the payload field `scratchpad_dir`, which is NOT a documented hook
    field and has never been confirmed to arrive. When it is absent this parameter does nothing and
    nothing is lost: in_project() already excludes a scratchpad that lies outside the project tree,
    which is where it lives. It is kept only as a second guard for a scratchpad nested inside it."""
    if not is_code(path) or not in_project(path):
        return False
    if "/.claude/memory/" in path or (scratchpad and in_tree(path, scratchpad)):
        return False
    return True


def on_edit(mem, path: str, tool_input: dict, scratchpad: str = "") -> None:
    if path.endswith(".claude/memory/PLAN.md"):
        written = json.dumps(tool_input).lower()
        if "unverified" in written:  # Claude chose to record the change as unverified
            (mem / ".unverified").unlink(missing_ok=True)
    elif counts_as_project_code(path, scratchpad):
        bump(mem / ".unverified")


def on_shell(mem, command: str) -> None:
    if verify_pattern(mem).search(command):
        (mem / ".unverified").unlink(missing_ok=True)


def main() -> None:
    mem = memory_dir()
    if mem is None:
        return
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    tool_input = data.get("tool_input") or {}
    if data.get("tool_name") in SHELL_TOOLS:
        on_shell(mem, tool_input.get("command", ""))
        return
    path = (tool_input.get("file_path") or tool_input.get("notebook_path") or "").replace("\\", "/")
    if path:
        on_edit(mem, path, tool_input, (data.get("scratchpad_dir") or "").replace("\\", "/"))


if __name__ == "__main__":
    main()
