"""Stop hook: runs at the end of EVERY response (which is also where an agent hand-back ends up,
because the hand-back arrives as input to a turn that then stops here).

1. Memory rule: a memory write is expected at the end of every response. The reply must end with
   a `memory: ...` line, and that line is checked against the memory files that actually changed
   since the last check (content hashes taken at SessionStart and at each Stop). `memory: none` is
   a legal and sufficient answer when nothing changed, like `Evidence: unverified - <why>` is for
   the verify gate. Mismatches (claimed but unchanged, "none" but changed, no line) block once.
2. Verify gate: project code was edited and the project's verify command (PLAN.md 'Verify:')
   never ran.

stop_hook_active (set when Claude is already continuing because of this hook) prevents loops: on
that second pass nothing blocks, a leftover mismatch is shown to the user as a warning instead.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Claude Code normally puts the script's own directory on sys.path, but not under `python -I`,
# which is how this gets tested. Be explicit so both work (same as review_gate.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memlib import changed_files, get_count, load_snapshot, memory_dir, memory_hashes, save_snapshot

MEMORY_LINE = re.compile(r"(?im)^[\s>*_`-]*memory:\**\s*(.+?)\s*$")
# "Nothing changed" in any of its natural spellings. Without these, `n/a`, `-` and `no changes`
# were each blocked as "names no memory file" - a legal answer treated as a failure.
NONE = re.compile(
    r"^(?:(?:none|nothing|n/?a|not applicable|unchanged|no\s+(?:memory\s+)?(?:changes?|updates?|writes?))\b"
    r"|[-\u2013\u2014]+$)", re.I)
# Global files and routines outside the project's memory folder: a line that only names these is
# fine when no project file changed. (`retro` writes me.md / mistakes.md.)
BRAIN_ONLY = re.compile(r"me\.md|mistakes|\bbrain\b|\bretro\b|\bglobal\b", re.I)
# Phrases in the memory: line that name a project memory file. NOW is case-sensitive so the English
# word "now" is not a claim; "NOW pointer" / "▶ NOW" is the CHECKLIST.md pointer, not NOW.md.
# Deliberately NOT claims: bare `tick` (ticking REVIEW.md findings is a standing rule here, and
# `memory: REVIEW.md ticked 3 findings` would have claimed CHECKLIST.md too) and bare `pointer`
# (a reply describing the loader uses the word without having touched CHECKLIST.md). The pointer
# counts only as `NOW pointer` / `▶ NOW`, which POINTER_PHRASE rewrites to the word "checklist".
CLAIMS = {
    "CHECKLIST.md": re.compile(r"checklist|▶", re.I),
    "PLAN.md": re.compile(r"\bplan\b|§", re.I),
    "NOW.md": re.compile(r"\bNOW\b"),
    "REVIEW.md": re.compile(r"\bREVIEW\b"),
}
POINTER_PHRASE = re.compile(r"▶\s*NOW|\bNOW\s+pointer", re.I)


# ---- pure logic ----

TAIL_LINES = 3  # the rule is "END every reply with the line", so only the last few lines count


def _outside_fences(text: str) -> list[str]:
    """Lines of `text` that are not inside a ``` fenced block (fence lines included in the block).
    An unpaired trailing fence is ignored rather than swallowing the rest of the reply."""
    lines = text.splitlines()
    fences = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("```")]
    inside: set[int] = set()
    for a, b in zip(fences[0::2], fences[1::2]):
        inside.update(range(a, b + 1))
    return [ln for i, ln in enumerate(lines) if i not in inside]


def last_memory_line(text: str | None) -> str | None:
    """The `memory:` line the reply ENDS with, or None. A match anywhere else - quoted in prose or
    inside a code block - would let a turn that merely describes the rule pass without the line."""
    tail = [ln for ln in _outside_fences(text or "") if ln.strip()][-TAIL_LINES:]
    for ln in reversed(tail):
        m = MEMORY_LINE.search(ln)
        if m:
            return m.group(1)
    return None


def claimed_files(line: str) -> set[str]:
    scrubbed = POINTER_PHRASE.sub(" checklist ", line)
    return {name for name, pat in CLAIMS.items() if pat.search(scrubbed)}


def memory_problems(line: str | None, changed: set[str] | None) -> list[str]:
    """Compare the `memory:` line with what changed. changed=None means there is no baseline to
    compare against, so only the presence of the line can be checked.

    ASYMMETRY, on purpose: a file that CHANGED but is not NAMED passes silently (unless the line
    says `none`). The check exists to catch a false statement - claiming a write that did not land,
    or `none` over a real write. The line is a summary, not an inventory, and demanding every
    changed file be named would fire on routine turns (REVIEW.md ticked, a counter in NOW.md) and
    train everyone to write the line by rote. The cost is an unmentioned write goes unnoticed;
    that is the lesser failure, so the behaviour stays as it is."""
    if line is None:
        return ["the reply has no `memory:` line"]
    if changed is None:
        return []
    shown = ", ".join(sorted(changed)) or "no memory file"
    if NONE.match(line):
        return [f"the reply says `memory: none` but {shown} changed this turn"] if changed else []
    claimed = claimed_files(line)
    problems = [
        f"the reply claims {name} was updated but its content is identical to the start of the turn"
        for name in sorted(claimed - changed)
    ]
    if not claimed and not changed and not BRAIN_ONLY.search(line):
        problems.append(f"the `memory:` line names no memory file I can check and none changed (`{line[:60]}`)")
    return problems


# ---- I/O ----

def transcript_last_text(path: str | None) -> str | None:
    """Fallback if the Stop payload has no last_assistant_message: the newest assistant text in the
    transcript, stopping at the user's prompt so an earlier turn's text is never mistaken for it."""
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 400_000))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    for raw in reversed(lines):
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        content = (entry.get("message") or {}).get("content")
        if entry.get("type") == "assistant" and isinstance(content, list):
            texts = [b.get("text", "") for b in content if b.get("type") == "text"]
            if any(t.strip() for t in texts):
                return "\n".join(texts)
        elif entry.get("type") == "user" and not (
            isinstance(content, list) and content and content[0].get("type") == "tool_result"
        ):
            return None
    return None


def verify_reasons(mem) -> list[str]:
    untested = get_count(mem / ".unverified")
    if not untested:
        return []
    return [
        f"Verify gate: {untested} project code edits and the project's verify command (PLAN.md 'Verify:') "
        "hasn't run since. Run it (prefer `python <brain>/bin/quiet.py <cmd>`) and fix failures, "
        "or if it can't run, write 'Evidence: unverified — <why>' in the PLAN section."
    ]


def main() -> None:
    mem = memory_dir()
    if mem is None:
        return
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    sid = data.get("session_id")
    text = data.get("last_assistant_message") or transcript_last_text(data.get("transcript_path"))
    after = memory_hashes(mem)
    before = load_snapshot(sid) if sid else None
    changed = changed_files(before, after) if before is not None else None

    problems = memory_problems(last_memory_line(text), changed) if text else []
    if not text:
        # Message unreachable: say what can be said (did memory change at all) and do not pretend more.
        note = ("memory files changed this turn: " + ", ".join(sorted(changed))) if changed else (
            "no memory file changed this turn" if changed is not None else "memory change check had no baseline")
        notice = f"Memory check: the reply text was not available, so the `memory:` line was NOT compared; {note}."
    else:
        notice = ""

    if data.get("stop_hook_active"):
        # Already nudged once; never block twice. Reset the verify batch, show leftovers to the user.
        (mem / ".unverified").unlink(missing_ok=True)
        warn = [f"MEMORY CHECK STILL FAILING: {p}." for p in problems]
        if sid:
            save_snapshot(sid, after)
        if warn or notice:
            print(json.dumps({"systemMessage": " ".join(warn) or notice}))
        return

    found = [
        "MEMORY CHECK FAILED: " + "; ".join(problems) + ". A memory write is expected at the end of every "
        "response. Either make the write and confirm it landed (re-read the file), or correct the line. "
        "If nothing needed recording, end with `memory: none`."
    ] if problems else []
    found += verify_reasons(mem)
    if found:  # snapshot NOT advanced: the continuation is judged against the same baseline
        print(json.dumps({
            "decision": "block",
            "reason": " ".join(found) + " Keep it short, end with the 'memory: ...' line, then finish.",
        }))
        return
    if sid:
        save_snapshot(sid, after)
    if notice:
        print(json.dumps({"systemMessage": notice}))


if __name__ == "__main__":
    main()
