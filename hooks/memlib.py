"""Shared helpers for the memory hooks: locating memory, reading files, small counters."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

from brainlib import STATE_DIR

# Keep in sync with the `paths:` glob in rules/engineering.md.
CODE_EXT = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rs", ".java", ".kt",
    ".kts", ".swift", ".m", ".mm", ".rb", ".php", ".cs", ".c", ".cpp", ".h", ".hpp",
    ".vue", ".svelte", ".dart", ".scala", ".lua", ".r", ".sh", ".ps1", ".sql",
    ".html", ".css", ".scss",
}
# Used when PLAN.md has no "Verify:" line.
DEFAULT_VERIFY = r"\b(test|tests|pytest|jest|vitest|mocha|lint|eslint|ruff|mypy|tsc|typecheck|cargo (test|check|clippy)|go (test|vet)|gradlew|mvn|dotnet test|quiet\.py)\b"


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def memory_dir() -> Path | None:
    """The project's .claude/memory folder, or None if this project has no memory."""
    proj = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    mem = proj / ".claude" / "memory"
    if not mem.is_dir() or mem.resolve() == (Path.home() / ".claude" / "memory").resolve():
        return None
    return mem


def project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def in_tree(path: str, root: str | Path) -> bool:
    r = os.path.normcase(os.path.abspath(root))
    p = os.path.normcase(os.path.abspath(path))
    return p == r or p.startswith(r.rstrip(os.sep) + os.sep)


def in_project(path: str) -> bool:
    """True if `path` lies inside the project tree. A scratchpad or temp file is not project code."""
    return in_tree(path, project_dir())


def memory_hashes(mem: Path) -> dict[str, str]:
    """Content hash of every top-level *.md in the memory folder. Hash, not mtime: a write that
    changed nothing (the str.replace that matched nothing) must read as unchanged."""
    return {
        f.name: _hash_file(f)
        for f in sorted(mem.glob("*.md")) if f.is_file()
    }


# A locked or unreadable file must NOT crash the hook. On Windows this is routine, not exotic:
# a sync client, an open editor or antivirus can hold a handle, and these files often live
# in a synced folder. Both hooks died with an unhandled PermissionError here - the loader then injected no
# memory at all, and the Stop hook crashed at the end of every turn.
# The sentinel (rather than omitting the file) keeps the key present, so an unreadable file compares
# EQUAL to itself across two snapshots instead of looking like an appearance or a deletion.
UNREADABLE = "unreadable"


def _hash_file(path: Path) -> str:
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        return UNREADABLE


def _snapshot_file(session_id: str) -> Path:
    return STATE_DIR / f"{session_id}.memsnap.json"


def load_snapshot(session_id: str) -> dict[str, str] | None:
    """The memory hashes recorded at the last SessionStart / Stop, or None if there is no baseline.
    Valid JSON that is not an object (`[]`, `"x"`) is as useless as garbage, and is also None:
    the caller would otherwise crash on .keys() at the end of every turn."""
    try:
        data = json.loads(_snapshot_file(session_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def save_snapshot(session_id: str, hashes: dict[str, str]) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _snapshot_file(session_id).write_text(json.dumps(hashes), encoding="utf-8")
    except OSError:
        pass  # a missing baseline only weakens the check; it must never break the hook


SNAPSHOT_MAX_AGE_DAYS = 7


def prune_snapshots(max_age_days: float = SNAPSHOT_MAX_AGE_DAYS, now: float | None = None) -> int:
    """Delete *.memsnap.json older than `max_age_days` (by mtime; a live session rewrites its file
    at every Stop, so only abandoned sessions age out). Returns how many went. Never raises: this is
    housekeeping and must not cost anyone their memory injection. Called from SessionStart."""
    cutoff = (time.time() if now is None else now) - max_age_days * 86400
    removed = 0
    try:
        files = list(STATE_DIR.glob("*.memsnap.json"))
    except OSError:
        return 0
    for f in files:
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            pass  # locked, or already gone
    return removed


def changed_files(before: dict[str, str], after: dict[str, str]) -> set[str]:
    return {n for n in before.keys() | after.keys() if before.get(n) != after.get(n)}


def verify_pattern(mem: Path) -> re.Pattern[str]:
    """Regex matching the project's verification commands (PLAN.md 'Verify:' line, else defaults)."""
    m = re.search(r"(?mi)^-?\s*\**Verify:?\**:?\s*(.+)$", read(mem / "PLAN.md"))
    value = m.group(1).strip() if m else ""
    if value.startswith("<"):  # template placeholder never filled in
        value = ""
    cmds = [c.strip(" `") for c in re.split(r"[;,]|\s\|\|\s", value)]
    cmds = [c for c in cmds if c]
    if not cmds:
        return re.compile(DEFAULT_VERIFY, re.I)
    return re.compile("|".join(re.escape(c) for c in cmds) + r"|quiet\.py", re.I)


def get_count(path: Path) -> int:
    try:
        return int(path.read_text().strip() or 0)
    except (OSError, ValueError):
        return 0


def bump(path: Path) -> None:
    path.write_text(str(get_count(path) + 1))


def is_code(path: str) -> bool:
    return Path(path).suffix.lower() in CODE_EXT
