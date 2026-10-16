"""Memory ROT detection, run at SessionStart only.

memory_load.py's pointer banner catches memory that is structurally BROKEN. This catches memory
that is well-formed and OUT OF DATE, the failure that actually cost something: NOW.md said
"HEAD 052e2f1, 3329 tests" for three days while the repo was at a1760d4, and a fresh session was
handed that as fact.

Three checks, all cheap (a handful of git calls, no test runs):
  A. stale commit claims in the text the loader INJECTS
  B. REVIEW.md's last-reviewed ref behind a HEAD with code changes (reuses review_gate)
  C. open REVIEW.md findings whose file has changed since it was last reviewed (a hint only)

HOW A TELLS "CLAIMED AS CURRENT" FROM "MENTIONED AS HISTORY" (the crux, see rot_findings):
  1. Only text the loader injects is scanned. That is what a new session believes as fact; the
     200 lines of dated history below the caps never reach it, so a historical "HEAD x" there is
     not a claim anyone is handed. This one choice removes almost all false positives.
  2. Only the grammatical forms that assert the CURRENT state count: `HEAD <sha>`, `HEAD is
     <sha>`, `<sha> is HEAD`, `<sha> (HEAD)`, `currently on commit <sha>`, `repo sits at <sha>`,
     `last commit is <sha>`, `tip of main: <sha>`, `REVIEW.md is at <sha>`, `REVIEW.md ref: <sha>`,
     `last reviewed <sha>`. A bare sha next to "fixed in" / "pushed" / "merge" is never a claim
     about the present, so an ancestor of HEAD mentioned that way is normal history and is not
     flagged.
  3. Even in those forms, a claim is skipped when it is quoted or reported: the sha sits inside
     "double quotes", or a reporting word leads into it. "this header said HEAD 052e2f1"
     describes a stale claim; it is not one. See REPORTING_STRONG / REPORTING_WEAK for how far
     back each kind of word reaches.

DELIBERATELY ABSENT: a check that flags any hex-looking token which is "not a commit". It
cried wolf on 8-digit ARGB colour literals (#FFE0B342), test ids and upstream shas in reporting
sentences, and a banner that is wrong once teaches everyone to ignore it. A claim whose sha is
not a commit is still caught - but only when it is phrased as a claim about the present.

Everything that touches git degrades to silence: no git, not a repo, no commits, a timeout.
All git work shares ONE wall-clock budget (BUDGET), because this runs inside a SessionStart hook
with a hard timeout: a hook that is killed prints NOTHING, which loses the memory injection too.
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))  # review_scope: ledger parsing + file hash

BAR = "~" * 72  # the pointer banner uses "!"; rot is visibly a different kind of failure
# Hook timeout for SessionStart is 15s (settings.json, the owner's file). Per call and in total we
# stay well inside it: 3s for one git call, 8s for everything this module does, which leaves the
# interpreter start-up, the file reads and the print the rest of the 15s.
GIT_TIMEOUT = 3
BUDGET = 8.0
_deadline: float | None = None  # monotonic time at which the budget is spent; set by rot_banners

HEXTOK = r"(?<![0-9A-Za-z_-])(?P<sha>[0-9a-fA-F]{7,40})(?![0-9A-Za-z_-])"
SEP = r"[\s:=@`'(]*"
# Forms that assert the CURRENT state. (kind, pattern); the pattern's group "sha" is the sha.
# Kinds: HEAD, REVIEW, and TIP (which also has group "ref": the branch the claim is about).
CURRENT_FORMS = [
    ("HEAD", re.compile(rf"(?<!\.)\bHEAD\b{SEP}(?:(?:is|now|at|currently|commit|sha)\b{SEP})*{HEXTOK}", re.I)),
    ("HEAD", re.compile(rf"{HEXTOK}[\s,)`']*(?:\(\s*HEAD\s*\)|(?:(?:which|that)\s+)?(?:is|=)\s+(?:the\s+)?(?:current\s+)?HEAD\b)", re.I)),
    ("HEAD", re.compile(rf"\b(?:currently|now)\s+(?:on|at)\s+(?:commit\s+)?{SEP}{HEXTOK}", re.I)),
    ("HEAD", re.compile(rf"\b(?:repo|repository|tree|checkout|clone)\s+(?:currently\s+)?(?:sits|stands|stays|is)\s+(?:currently\s+)?(?:on|at)\s+(?:commit\s+)?{SEP}{HEXTOK}", re.I)),
    ("HEAD", re.compile(rf"\b(?:last|latest|newest|current|most\s+recent)\s+commit\s*(?:(?:is|now)\b)?{SEP}{HEXTOK}", re.I)),
    ("TIP", re.compile(rf"\btip\s+of\s+(?:the\s+)?(?:branch\s+)?(?P<ref>[\w./-]+?)(?:\s+branch)?\s*(?:(?:is|=|now)\b)?{SEP}{HEXTOK}", re.I)),
    ("REVIEW", re.compile(rf"\bREVIEW(?:\.md)?\b[\s`']*(?:is\s+|now\s+)*at{SEP}{HEXTOK}", re.I)),
    ("REVIEW", re.compile(rf"\blast[- ]reviewed(?:\s+(?:at|ref|commit|sha|is))*{SEP}{HEXTOK}", re.I)),
    ("REVIEW", re.compile(rf"\bREVIEW(?:\.md)?(?:'s)?[\s`']*(?:last[- ]reviewed\s+)?ref(?:erence)?\b(?:\s+is)?{SEP}{HEXTOK}", re.I)),
]
# Words that mean the sentence is REPORTING an earlier claim or a past state, not making one.
# STRONG words introduce a quotation or name another repo: they reach anywhere in the last 60
# characters of the sentence. WEAK words are ordinary English ("the suite was green", "I had to
# rerun") and only mean "reporting" when they sit in the SAME CLAUSE as the sha and close to it, so
# "Work was finished, so HEAD a1760d4" (a genuine claim) is no longer swallowed.
REPORTING_STRONG = re.compile(
    r"\b(said|says|named|names|claimed|claims|asserted|asserts|wrote|written|stated|"
    r"recorded|described|used to|upstream|origin|remote|fork)\b", re.I)
REPORTING_WEAK = re.compile(r"\b(was|were|had|read|reads)\b", re.I)
WEAK_REACH = 30
CLAUSE_BREAK = re.compile(r",|\s[-\u2013\u2014]+\s|[\u2013\u2014]")
SENTENCE_BREAK = re.compile(r"[.;!?]\s|\bbut\b|\band then\b", re.I)


def _inside_quotes(line: str, pos: int) -> bool:
    # An opening quote with no close on this line is a quotation wrapping onto the next line.
    before = line[:pos]
    return before.count('"') % 2 == 1 or before.count("“") > before.count("”")


def _is_reported(line: str, start: int) -> bool:
    """True when the claim at `start` is quoted, or follows a reporting word in its own sentence."""
    if _inside_quotes(line, start):
        return True
    lead = line[:start]
    breaks = list(SENTENCE_BREAK.finditer(lead))
    sentence = lead[breaks[-1].end():] if breaks else lead
    if REPORTING_STRONG.search(sentence[-60:]):
        return True
    clause = CLAUSE_BREAK.split(sentence[-WEAK_REACH:])[-1]
    return bool(REPORTING_WEAK.search(clause))


def current_claims(text: str) -> list[tuple[str, str, int]]:
    """(kind, sha, line_no) for every assertion of the CURRENT head that is not quoted/reported.
    A TIP claim has kind "TIP:<branch>"."""
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        for kind, pat in CURRENT_FORMS:
            for m in pat.finditer(line):
                tok = m.group("sha")
                if not (re.search(r"\d", tok) and re.search(r"[a-fA-F]", tok)):
                    continue  # plain numbers and English words ("defaced") are not shas
                if _is_reported(line, m.start()):
                    continue
                out.append((f"TIP:{m.group('ref')}" if kind == "TIP" else kind, tok.lower(), no))
    return sorted(set(out), key=lambda c: (c[2], c[1]))


def claim_refs(claims: list[tuple[str, str, int]]) -> set[str]:
    """Branch names that TIP claims ask about, so they can be resolved in the same git call."""
    return {k[4:] for k, _, _ in claims if k.startswith("TIP:")}


def stale_claims(
    claims: list[tuple[str, str, int]], head: str, review_ref: str | None, known: dict[str, str | None]
) -> list[str]:
    """Describe each claim that disagrees with reality. `known` maps sha (or branch name) -> full
    commit sha, or None when git ANSWERED and said it is not a commit. A name that is absent from
    `known` means git could not answer (no git, timeout, odd output): that is silence for the
    "NOT A COMMIT" accusation, never a false one, because the claim might name a real commit."""
    out = []
    for kind, sha, no in claims:
        if kind == "HEAD":
            if head.startswith(sha) or known.get(sha) == head:
                continue
            if sha in known and known[sha] is None:  # git answered, and the answer was "no such commit"
                out.append(f"line {no} says HEAD is {sha}, which is NOT A COMMIT in this repo (real HEAD is {head[:7]})")
            else:
                out.append(f"line {no} says HEAD is {sha}, but real HEAD is {head[:7]}")
        elif kind.startswith("TIP:"):
            ref = kind[4:]
            tip = known.get(ref)
            if not (tip and re.fullmatch(r"[0-9a-f]{40}", tip)):
                continue  # unknown branch, ambiguous name or git could not answer: cannot tell
            if tip.startswith(sha) or known.get(sha) == tip:
                continue
            out.append(f"line {no} says the tip of {ref} is {sha}, but {ref} is at {tip[:7]}")
        elif kind == "REVIEW" and review_ref:
            if review_ref.lower().startswith(sha) or sha.startswith(review_ref.lower()):
                continue
            out.append(f"line {no} says REVIEW.md is at {sha}, but REVIEW.md's ref is {review_ref}")
    return out


# ---- git (every call degrades to None / empty) ----

def _call_timeout() -> float:
    """Timeout for the next git call: GIT_TIMEOUT, or what is left of the budget if that is less.
    Raises once the budget is spent, so a slow git costs BUDGET seconds in total, not per call."""
    if _deadline is None:
        return GIT_TIMEOUT
    left = _deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError("memrot git budget spent")
    return min(GIT_TIMEOUT, left)


def _git(project: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess | None:
    try:
        r = subprocess.run(["git", *args], cwd=str(project), input=stdin, capture_output=True,
                           text=True, timeout=_call_timeout())
    except Exception:  # no git, bad cwd, timeout: rot detection must never break a session
        return None
    return r if r.returncode == 0 else None


def head_full(project: Path) -> str | None:
    r = _git(project, "rev-parse", "HEAD")
    return r.stdout.strip().lower() if r and r.stdout.strip() else None


def resolve_commits(project: Path, shas: set[str]) -> dict[str, str | None]:
    """sha -> full commit sha, or None if it is not a commit here. One git process for all."""
    if not shas:
        return {}
    order = sorted(shas)
    r = _git(project, "cat-file", "--batch-check", stdin="".join(f"{s}^{{commit}}\n" for s in order))
    if r is None:
        return {}
    lines = r.stdout.splitlines()
    if len(lines) != len(order):
        return {}
    out = {}
    for sha, line in zip(order, lines):
        parts = line.split()
        if line.endswith(" missing"):
            out[sha] = None
        elif len(parts) >= 2 and parts[1] == "commit":
            out[sha] = parts[0].lower()
        else:  # ambiguous prefix etc.: it exists, so do not call it invented
            out[sha] = sha
    return out


# ---- B and C ----

def ledger_drift(project: Path, mem: Path) -> list[str]:
    """B: REVIEW.md's last-reviewed ref is behind a HEAD with code changes. Reuses review_gate,
    with its git calls routed through the shared budget (review_gate's own are 10s each)."""
    import review_gate as gate
    ref = gate.reviewed_ref(mem)
    if ref is None:
        return []
    pending = gate.unreviewed_code_files(
        ref, cwd=project, run=lambda *a, cwd=None: gate.git(*a, cwd=cwd, timeout=_call_timeout()))
    if not pending:
        return []
    shown = ", ".join(pending[:4]) + (f" (+{len(pending) - 4} more)" if len(pending) > 4 else "")
    return [f"REVIEW.md was last reviewed at {ref} but HEAD has {len(pending)} changed code file(s) since: "
            f"{shown}. Run /review-changes before launching writing agents (the review gate will refuse them anyway)"]


FINDING = re.compile(r"^\s*-\s*\[ \]\s*(?:(?:LOW-MED|MED-HIGH|HIGH|MED|LOW|INFO|NIT)\b\s*)?(.*)$")
FILE_REF = re.compile(r"([\w./-]+\.(?:dart|ts|tsx|js|jsx|py|go|rs|kt|swift|java|rb|php|cs|c|cpp|h|vue|svelte|sql|css|html|sh|yaml|yml))\b")


def finding_files(review_text: str) -> list[tuple[str, str]]:
    """(file token, finding head) for each open `- [ ]` finding. Only the LOCATION part is read
    (the text before the first ' - '), because the prose after it mentions files in passing."""
    out = []
    for line in review_text.splitlines():
        m = FINDING.match(line)
        if not m:
            continue
        head = m.group(1)
        location = head.split(" - ", 1)[0]
        for f in FILE_REF.findall(location):
            out.append((f, head[:70]))
    return out


def moved_findings(project: Path, review_text: str) -> list[str]:
    """C: open findings whose file's content hash differs from the one recorded when it was last
    reviewed. A hint ('may be stale, verify'), never a verdict: a file changes for unrelated reasons."""
    from review_scope import reviewed_hashes, short_sha
    recorded = reviewed_hashes(review_text)
    by_name: dict[str, list[str]] = {}
    for path in recorded:
        by_name.setdefault(Path(path).name, []).append(path)
    out, seen = [], set()
    for tok, head in finding_files(review_text):
        paths = [p for p in recorded if p == tok or p.endswith("/" + tok)] or by_name.get(Path(tok).name, [])
        if len(paths) != 1 or paths[0] in seen:  # unknown or ambiguous file: cannot tell, stay quiet
            continue
        f = project / paths[0]
        if not f.is_file():
            continue
        now = short_sha(f.read_bytes())
        if now != recorded[paths[0]]:
            seen.add(paths[0])
            out.append(f"open finding `{head[:50]}...` names {paths[0]}, which changed since its review "
                       f"(sha {recorded[paths[0]]} -> {now}); it MAY be fixed already, verify before acting")
    return out


# ---- entry point ----

def banner(title: str, lines: list[str]) -> str:
    return "\n".join([BAR, f"~~ {title}", *[f"~~ - {l}" for l in lines], BAR])


def rot_banners(loaded: dict[str, str], project: Path, mem: Path) -> list[str]:
    """Banners for everything stale in `loaded` (file label -> injected text), or [] for none or on
    any failure. Never raises. All git work shares one wall-clock BUDGET."""
    global _deadline
    _deadline = time.monotonic() + BUDGET
    try:
        head = head_full(project)
        if head is None:
            return []
        gate_ref = None
        try:
            import review_gate as gate
            gate_ref = gate.reviewed_ref(mem)
        except Exception:
            pass
        claims = {name: current_claims(text) for name, text in loaded.items()}
        want = {s for cs in claims.values() for _, s, _ in cs}
        want |= {r for cs in claims.values() for r in claim_refs(cs)}
        known = resolve_commits(project, want)

        stale = []
        for name, cs in claims.items():
            stale += [f"{name}: {s}" for s in stale_claims(cs, head, gate_ref, known)]

        out = []
        if stale:
            out.append(banner(f"MEMORY ROT: stale commit claims (HEAD is {head[:7]}); a fresh session would trust these", stale))
        review = []
        try:
            review += ledger_drift(project, mem)
        except Exception:
            pass
        try:
            from memlib import read
            review += moved_findings(project, read(mem / "REVIEW.md"))
        except Exception:
            pass
        if review:
            out.append(banner("REVIEW LEDGER DRIFT (check before trusting REVIEW.md)", review))
        return out
    except Exception:
        return []
