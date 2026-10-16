"""SessionStart hook (startup|resume|clear|compact).

Re-injects project memory so /clear and context compaction never lose the
current state: NOW.md in full, CHECKLIST.md, the PLAN.md goal header, and only
the PLAN section for the checklist item the ▶ NOW pointer names.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Claude Code normally puts the script's own directory on sys.path, but not under `python -I`,
# which is how this gets tested. Be explicit so both work (same as review_gate.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memlib import memory_dir, memory_hashes, project_dir, prune_snapshots, read, save_snapshot  # noqa: E402
try:
    from memrot import rot_banners
except Exception:  # rot detection is an extra; a fault in it must never stop memory loading
    def rot_banners(*_args):  # type: ignore[misc]
        return []

CAPS = {"NOW.md": 40, "CHECKLIST.md": 80, "header": 30, "section": 60}


def cap(text: str, n: int) -> str:
    lines = text.strip().splitlines()
    return "\n".join(lines[:n] + ([f"... ({len(lines) - n} more lines in file)"] if len(lines) > n else []))


POINTER = re.compile(r"▶\s*NOW:[ \t]*(.*)")
# An id is digits and dots with an optional trailing letter (2.6b), ending at a non-id character,
# so `▶ NOW: 17 - free prose after it` yields 17.
ID_SHAPE = re.compile(r"(\d+(?:\.\d+)*[a-z]?)(?=$|[^\w.]|\.(?:\s|$))")


def parse_pointer(checklist: str) -> tuple[str | None, str | None]:
    """(id, raw): id is the checklist id after `▶ NOW:` if it has the id shape, else None.
    raw is the text after the colon (None when there is no pointer at all)."""
    m = POINTER.search(checklist)
    if not m:
        return None, None
    raw = m.group(1).strip()
    ident = ID_SHAPE.match(raw)
    return (ident.group(1) if ident else None), raw


def current_id(checklist: str) -> str | None:
    return parse_pointer(checklist)[0]


def pointer_warning(item: str | None, raw: str | None, section: str) -> str | None:
    """A loud banner when the pointer does not lead to a PLAN section, else None.
    Two different faults, two different fixes, so they get different messages."""
    if item and section.strip():
        return None
    bar = "!" * 72
    if raw is None:
        why = (
            "CHECKLIST.md has no `▶ NOW:` pointer, so no PLAN section was loaded. "
            "Fix: put `▶ NOW: <id>` on line 1 of CHECKLIST.md, e.g. `▶ NOW: 17 - prose after the id`."
        )
    elif item is None:
        first = (raw.split() or ["(nothing)"])[0]
        why = (
            f"MALFORMED ▶ NOW POINTER. CHECKLIST.md says `▶ NOW: {raw[:60]}` and `{first}` is not a "
            "checklist id, so NO PLAN section was loaded. "
            "Required format: `▶ NOW: <id>` then optional prose, e.g. `▶ NOW: 17 - prose after the id`. "
            "The id is digits and dots (17, 2.6, 6.58b). Fix the pointer on line 1 of CHECKLIST.md."
        )
    else:
        why = (
            f"`▶ NOW: {item}` is a valid id but PLAN.md has no `## {item} <title>` section, so NO PLAN "
            "section was loaded. "
            f"Fix: add `## {item} <title>` to PLAN.md (why, approach, state, done-when), or point the "
            "pointer at an id that has one."
        )
    head = "!! NOW-POINTER PROBLEM: the current item's reasoning was NOT injected."
    return "\n".join([bar, head, f"!! {why}", bar])


def split_plan(plan: str, item_id: str | None) -> tuple[str, str]:
    """Return (goal header, section for item_id). Sections start with '## <id> '."""
    parts = re.split(r"(?m)^(?=## )", plan)
    is_item = lambda p: re.match(r"## \d[\d.]*\s", p)
    header = "".join(p for p in parts if not is_item(p))
    section = ""
    if item_id:
        for p in parts:
            if re.match(rf"## {re.escape(item_id)}\s", p):
                section = p
    return header, section


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    try:
        session_id = json.load(sys.stdin).get("session_id")
    except ValueError:
        session_id = None
    mem = memory_dir()
    if mem is None:
        print("(No project memory here. If this project will span several sessions, offer /memory-init.)")
        return

    now, checklist, plan = (read(mem / f) for f in ("NOW.md", "CHECKLIST.md", "PLAN.md"))
    item, raw = parse_pointer(checklist)
    header, section = split_plan(plan, item)

    out = ["## Project memory (.claude/memory/, the code wins if they disagree)"]
    loaded: dict[str, str] = {}  # exactly the text injected below: what a new session will believe
    if now.strip():
        loaded["NOW.md"] = cap(now, CAPS["NOW.md"])
        out += ["### Set 3 · NOW", loaded["NOW.md"]]
    if checklist.strip():
        loaded["CHECKLIST.md"] = cap(checklist, CAPS["CHECKLIST.md"])
        out += ["### Set 1 · CHECKLIST", loaded["CHECKLIST.md"]]
    if header.strip():
        loaded["PLAN.md header"] = cap(header, CAPS["header"])
        out += ["### Set 2b · PLAN header", loaded["PLAN.md header"]]
    if section.strip():
        loaded[f"PLAN.md §{item}"] = cap(section, CAPS["section"])
        out += [f"### Set 2b · PLAN §{item} (other sections: read PLAN.md when needed)", loaded[f"PLAN.md §{item}"]]
    warning = pointer_warning(item, raw, section) if checklist.strip() else None
    if warning:
        out = [warning] + out + [warning]  # top and bottom: it must not read as ordinary memory text
    rot = rot_banners(loaded, project_dir(), mem)  # stale-but-well-formed memory; never raises
    if rot:
        out = rot + out + rot  # outermost: it says the facts below may be wrong
    print("\n".join(out))
    try:
        sys.stdout.flush()  # the injection is out before anything below can fail
    except OSError:
        pass
    after_print(session_id, mem)


def after_print(session_id: str | None, mem: Path) -> None:
    """Bookkeeping that must never cost the memory injection, so it runs AFTER the print and
    swallows everything. A failure here once (a locked .md crashing memory_hashes) left sessions
    with no memory at all; the injection is the product, the snapshot is a convenience."""
    try:
        if session_id:  # baseline for the Stop hook's "did memory change this turn" check
            save_snapshot(session_id, memory_hashes(mem))
        prune_snapshots()
    except Exception:
        pass


if __name__ == "__main__":
    main()
