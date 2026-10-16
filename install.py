"""Install the brain into ~/.claude. Works on Windows, WSL, macOS and Linux.

Usage: python install.py    (re-run after moving the folder or pulling updates)

- ~/.claude/CLAUDE.md becomes a one-line import of this folder's CLAUDE.md, so edits
  here (including me/me.md) take effect immediately. No symlinks needed.
- Rules, skills, agents and memory templates are copied (they change rarely; re-run to update).
- Hooks are merged into ~/.claude/settings.json and point at this folder's scripts.
- Anything replaced is backed up to ~/.claude/backup-brain-<timestamp>/.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

BRAIN = Path(__file__).resolve().parent
CLAUDE = Path.home() / ".claude"
MARKER = "<!-- managed by claude-brain install.py -->"
HOOKS = [  # (event, matcher, script, timeout)
    ("SessionStart", "startup|resume|clear|compact", "memory_load.py", 15),
    ("SessionStart", "startup|resume", "brain_backup.py", 30),
    ("UserPromptSubmit", None, "retro_prompt.py", 30),
    ("PostToolUse", "Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell", "memory_dirty.py", 10),
    ("Stop", None, "memory_stop.py", 10),
]

backup_dir = CLAUDE / f"backup-brain-{time.strftime('%Y%m%d-%H%M%S')}"


def posix(p: Path) -> str:
    return p.as_posix()


def backup(path: Path) -> None:
    if path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        dest = backup_dir / path.name
        (shutil.copytree if path.is_dir() else shutil.copy2)(path, dest)
        print(f"  backed up {path.name}")


def write_global_claude_md() -> None:
    target = CLAUDE / "CLAUDE.md"
    if target.exists() and MARKER not in target.read_text(encoding="utf-8", errors="ignore"):
        backup(target)
    target.write_text(
        f"{MARKER}\nBrain folder: {posix(BRAIN)}\n\n@{posix(BRAIN)}/CLAUDE.md\n", encoding="utf-8"
    )
    print("  ~/.claude/CLAUDE.md -> imports brain")


def copy_tree(src: Path, dest: Path) -> None:
    for f in src.rglob("*"):
        if f.is_file():
            out = dest / f.relative_to(src)
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.exists() and out.read_bytes() != f.read_bytes():
                backup(out)
            shutil.copy2(f, out)


def merge_settings() -> None:
    path = CLAUDE / "settings.json"
    settings = {}
    if path.exists() and path.stat().st_size:
        backup(path)
        settings = json.loads(path.read_text(encoding="utf-8"))
    settings["autoMemoryEnabled"] = False  # the three-set memory replaces it
    hooks = settings.setdefault("hooks", {})
    python = posix(Path(sys.executable))
    for event, matcher, script, timeout in HOOKS:
        groups = hooks.setdefault(event, [])
        # drop any earlier install of this script (e.g. the folder moved), keep everything else
        for g in groups:
            g["hooks"] = [h for h in g.get("hooks", []) if script not in h.get("command", "")]
        groups[:] = [g for g in groups if g["hooks"]]
        group = {"hooks": [{
            "type": "command",
            "command": f'"{python}" "{posix(BRAIN / "hooks" / script)}"',
            "timeout": timeout,
        }]}
        if matcher:
            group = {"matcher": matcher, **group}
        groups.append(group)
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print("  merged hooks into ~/.claude/settings.json")


def seed_me() -> None:
    """First install only: give me/ its starting files.

    `me/` is personal - knowledge about the user, and the agent's own mistake counter - so the
    published copy of this repo ships only the stubs under templates/me/ and no me/ directory at
    all. An existing me/ is never touched.
    """
    dest = BRAIN / "me"
    src = BRAIN / "templates" / "me"
    if dest.exists() or not src.is_dir():
        return
    copy_tree(src, dest)
    print(f"  seeded {posix(dest)} from templates/me - fill these in as you go")


def main() -> None:
    print(f"Installing brain from {posix(BRAIN)} into {posix(CLAUDE)}")
    CLAUDE.mkdir(exist_ok=True)
    write_global_claude_md()
    copy_tree(BRAIN / "rules", CLAUDE / "rules")
    copy_tree(BRAIN / "skills", CLAUDE / "skills")
    copy_tree(BRAIN / "agents", CLAUDE / "agents")
    copy_tree(BRAIN / "templates", CLAUDE / "memory-templates")
    seed_me()
    merge_settings()
    if backup_dir.exists():
        print(f"Backups: {posix(backup_dir)}")
    print("Done. Start a new Claude Code session; in a project run /memory-init.")


if __name__ == "__main__":
    main()
