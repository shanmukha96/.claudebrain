"""Compute what a review needs to look at, so the reviewer never re-reads unchanged code.

Usage: python review_scope.py <repo> [<last_reviewed_ref>] [--full]

Prints JSON:
  base       the ref diffed against (last reviewed commit, or HEAD if none)
  head       current HEAD
  changed    files changed since base, including uncommitted and untracked
  impacted   code files that import a changed file (one hop), minus the changed ones
  skipped    changed files whose content is identical to what was last reviewed (from the ledger)
Pure scoping logic lives in the functions; git and disk access stay in main().
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from memlib import CODE_EXT  # noqa: E402  (single source of truth for code extensions)

IGNORED_DIRS = {".git", "build", ".dart_tool", "node_modules", ".gradle", "Pods", ".idea"}
HASH_LINE = re.compile(r"^-\s+`([^`]+)`\s+sha:([0-9a-f]{12})", re.M)


# ---- pure logic ----

def importers(changed: list[str], sources: dict[str, str]) -> list[str]:
    """Files whose text imports one of the changed files (matched by file name in an import line)."""
    names = {Path(c).name for c in changed}
    out = []
    for path, text in sources.items():
        if path in changed:
            continue
        for line in text.splitlines():
            s = line.strip()
            if s.startswith(("import ", "export ", "part ", "from ", "require(", "#include")) and any(n in s for n in names):
                out.append(path)
                break
    return sorted(out)


def reviewed_hashes(ledger: str) -> dict[str, str]:
    """Map path -> short sha from ledger lines like: - `lib/a.dart` sha:0123456789ab ..."""
    return {m.group(1): m.group(2) for m in HASH_LINE.finditer(ledger)}


def short_sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:12]


# ---- I/O ----

def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout.strip()


def code_sources(repo: Path) -> dict[str, str]:
    out = {}
    for f in repo.rglob("*"):
        if f.suffix.lower() in CODE_EXT and f.is_file() and not IGNORED_DIRS.intersection(f.relative_to(repo).parts):
            try:
                out[f.relative_to(repo).as_posix()] = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                pass
    return out


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--full"]
    repo = Path(args[0]).resolve()
    head = git(repo, "rev-parse", "--short", "HEAD")
    sources = code_sources(repo)
    if "--full" in sys.argv:
        print(json.dumps({"base": None, "head": head, "changed": sorted(sources), "impacted": [], "skipped": []}, indent=1))
        return
    base = args[1] if len(args) > 1 else "HEAD"
    changed = set(git(repo, "diff", "--name-only", base).splitlines())
    changed |= set(git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    ledger_path = repo / ".claude" / "memory" / "REVIEW.md"
    ledger = ledger_path.read_text(encoding="utf-8") if ledger_path.exists() else ""
    seen = reviewed_hashes(ledger)
    skipped = sorted(c for c in changed if (repo / c).is_file() and seen.get(c) == short_sha((repo / c).read_bytes()))
    changed = sorted(c for c in changed if c not in skipped and not c.startswith(".claude/"))
    result = {
        "base": base, "head": head, "changed": changed,
        "impacted": importers(changed, sources), "skipped": skipped,
        "hashes": {c: short_sha((repo / c).read_bytes()) for c in changed if (repo / c).is_file()},
    }
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
