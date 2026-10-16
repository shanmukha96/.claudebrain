# claude-brain

A memory and enforcement layer for Claude Code. Three plain-text files hold a project's state, and a
handful of hooks refuse to let the agent lie about it.

No database, no server, no account, no dependencies beyond Python. Built for one long-running port,
published in case the shape is useful.

## The one idea

Most agent-memory systems **record**. This one **refuses**.

Recording is the cheap half, and it is not the hard part. The hard part is that an agent will tell
you something is done, that a test passed, that it wrote a note — and be wrong, confidently, in a way
that reads exactly like being right. A file full of good intentions does not catch that. A gate that
will not let the turn end until a number has actually been run does.

Every gate here exists because the failure it catches happened repeatedly *with the rule written down
and ignored*.

## Install

```bash
git clone https://github.com/shanmukha96/.claudebrain claude-brain
cd claude-brain
python install.py
```

Python 3.8+. It makes `~/.claude/CLAUDE.md` a one-line import of this folder's `CLAUDE.md`, merges
the hooks into `~/.claude/settings.json` pointing at this folder's scripts, copies `rules/`,
`skills/`, `agents/` and the memory templates into `~/.claude/`, and on a first install seeds `me/`
from `templates/me/`. Replaced files are backed up to `~/.claude/backup-brain-<timestamp>/`.

Then, inside a project: `/memory-init`.

**What is live versus copied — this catches people out.**

| | Mechanism | Edits apply |
|---|---|---|
| `CLAUDE.md`, and `me/` via its imports | `~/.claude/CLAUDE.md` is a one-line import of this folder | next session, no install |
| `hooks/*.py` | `settings.json` points at these paths | next session, no install |
| `rules/`, `skills/`, `agents/`, `templates/` | **copied** into `~/.claude/` | only after `install.py` runs again |

A whole evening of rule-writing can sit inert because of that second row.

## The three memory sets — per project, in `.claude/memory/`

| File | Holds | How much reaches a new session |
|---|---|---|
| `CHECKLIST.md` | Every goal to completion: ids, status `[ ] [~] [!] [x]`, and a `▶ NOW: <id>` pointer on line 1 | first 80 lines |
| `PLAN.md` | A goal header (final goal, constraints, `Verify:` commands), then one `## <id>` section per checklist id: why, approach, state, done-when, evidence, dated history | header capped at 30 lines, plus the **current id's section** capped at 60 |
| `NOW.md` | The current objective only, in the user's exact words, plus `Noted:` items | first 40 lines |

Three jobs on purpose. The checklist is *what*, the plan is *why*, the now-file is *where we are and
what the user actually said*. Collapsing them loses what each is for — the plan is the only place
causal reasoning can live attached to the goal that produced it, and the now-file is the only place
the user's exact words survive paraphrase.

Two consequences worth knowing before you start:

- **The pointer must begin with an id.** `▶ NOW: 17 - prose after a dash` resolves; `▶ NOW: the thing
  we were doing` makes the loader read "the" as the id, find nothing, and inject no reasoning at all.
  It warns loudly now. It did not always, and the cost was days of sessions starting blind.
- **Only the top of each file arrives.** Current state belongs at the TOP of a file or section;
  history below it. State written underneath the cut never reaches a new session.

## What each piece does

### `hooks/` — the enforcement layer

| Hook | Event | Does |
|---|---|---|
| `memory_load.py` | SessionStart (startup, resume, clear, compact) | Injects NOW, CHECKLIST, the PLAN header and the current id's PLAN section. Shouts when the `▶ NOW` pointer is malformed, names an id with no section, or is missing. Runs the rot checks. Snapshots memory-file hashes as the turn's baseline, and prunes snapshots older than 7 days. |
| `memrot.py` | library, called above | Three checks: a memory file asserting `HEAD <sha>` that is not HEAD; a review ledger behind HEAD with unreviewed code; an open finding whose named file changed since its recorded hash. Scans only the text actually injected — which is what keeps false positives at zero, since memory files are full of legitimate historical shas. |
| `memory_stop.py` | Stop | Two gates, each blocking at most once per turn. **Memory check:** every reply must end with a `memory: ...` line, compared against which memory files actually changed by content hash — claimed-but-unchanged, `none`-but-changed, or no line at all blocks. `memory: none` is legal when nothing changed. **Verify gate:** project code changed but the PLAN header's `Verify:` commands never ran; run them or record `Evidence: unverified - <why>`. |
| `memory_dirty.py` | PostToolUse | Counts edits to project code, scoped to the project tree, so a scratchpad or temp file never triggers the verify gate. |
| `review_gate.py` | PreToolUse on `Agent` | Refuses to launch a code-writing agent while the review ledger's last-reviewed ref is behind a HEAD containing code changes. Read-only agents are never blocked, since the reviewer is what clears it. `BRAIN_SKIP_REVIEW_GATE=1` bypasses it for a session. |
| `retro_prompt.py` | UserPromptSubmit | Reminds about `/retro` every N messages (`BRAIN_RETRO_EVERY`), and asks for one when the date changes mid-session. |
| `brain_backup.py` | SessionStart | Commits this repo locally every 7 days (`BRAIN_BACKUP_DAYS`). Never pushes. |
| `memlib.py`, `brainlib.py` | libraries | Memory-dir resolution, content hashing, snapshot read/write, project-tree scoping, state under `~/.claude/brain-state/`. |

### Knowledge, rules, and failures are different files

| Path | Holds |
|---|---|
| `me/me.md` | Knowledge **about the user**: how they think, what they have corrected, standing preferences. Ground truth to reason *with*, not rules. |
| `me/mistakes.md` | The agent's **own** repeated failures, counted and dated, with a fix each. At three occurrences the fix must become a mechanism, not a stronger intention. |
| `rules/*.md` | Rules the agent complies *with*, scoped by `paths:` frontmatter so they arrive when relevant instead of sitting unread at the top of every session. |

That last distinction matters more than it looks. Rules delivered *when relevant* get followed; rules
loaded once at session start are stale by the time they apply. And a rule whose compliance leaves **no
mark in the reply** does not get followed at all, however true it is — so prefer "the reply must
state X" over "consider X". It is the single most useful thing in here.

`me/` ships only as stubs in `templates/me/`; `install.py` seeds it on a first install and never
touches an existing one.

### `rules/`

| File | Scope | Holds |
|---|---|---|
| `engineering.md` | source files | Modularity, pure logic separated from I/O, injected dependencies, error handling at the boundary, naming, a test per bug fix |
| `reasoning.md` | `**/*` | Fifteen one-line rules, and an end-of-reply check that reads them against a finished draft before sending anything that proposes or concludes. Rule 14 is unenforced: read a rule's origin only when its wording is unclear, or when about to overrule it |

### `skills/`

| Skill | Does |
|---|---|
| `/memory-init` | Create the three files for a repo, seeded from the real codebase and the stated goal |
| `/review-changes` | Incremental review: scope to changed files plus their importers, skip already-reviewed content, record findings and per-file hashes in a ledger |
| `/retro` | End-of-session audit: what happened, which rules were broken, increment the mistake counter, file each lesson in exactly one place |
| `/learn` | Turn one lesson into a rule that will actually fire. Its load-bearing step is the shape test: would complying leave a mark in a reply? If not, rewrite it as something the reply must contain |
| `/memory-consolidate` | Prune and tidy when the plan file outgrows its window |

### `agents/`

| Agent | Model | For |
|---|---|---|
| `coder` | Sonnet | Writes code for one assigned task, runs the project's `Verify:` commands, reports back. Never edits memory |
| `reviewer` | Opus | Read-only incremental review of a given scope. Reports findings; never edits |
| `explorer` | Haiku | Read-only search across many files, so file dumps stay out of the main context |

### `bin/`

| Script | Does |
|---|---|
| `quiet.py` | Runs a command and prints only failures plus a short tail: `python bin/quiet.py npm test` |
| `review_scope.py` | Computes a review's scope — changed files, their importers, what to skip — with per-file hashes |

### `tests/`

`test_unit.py` — 83 checks over the hooks' pure logic. `test_e2e.py` — runs the hooks end to end
against temp fixtures. Both derive every path from their own location and redirect `HOME` so they
never touch a real config or a real project's memory.

```bash
PYTHONIOENCODING=utf-8 python tests/test_unit.py
```

(The encoding variable matters: these tests print the `▶` glyph, and a Windows console without it
dies on its own output rather than on a failure.)

## What it costs

A visible share of turns goes on memory maintenance. On a long project with hard-won domain
knowledge, that pays for itself the first time a session resumes already knowing why an approach was
rejected. On a one-day task it is pure overhead — don't.

## Honest limitations

- **Windows-tested.** The hooks are plain Python and should port, but the suite's file-locking and
  PATH cases are Windows-specific and skip elsewhere; the POSIX branch of its stub-git builder is
  untested.
- **`tests/test_e2e.py` has no assertions.** It prints observations and always exits 0, so a pass
  means only that it ran without crashing. `test_unit.py` is the one with real checks.
- **The rot check's phrasing rules were tuned on a single memory set.** Zero false positives there; a
  phrasing it has not seen could slip past or trip it.
- **A 15-second session-start budget bounds those checks.** Git calls are capped inside it; a very
  slow read on a synced folder is not.
- **One session per project is assumed.** Two open at once on the same memory files can produce a
  spurious memory-check warning, because the baseline is per session.
- **The author's own `me/` files are not published**, by design — everything in them is specific to
  one person and one codebase.
- **None of this makes the agent reason better.** It makes dishonesty expensive, which is a smaller
  and different claim. The gates catch what the agent got wrong; they do not stop it being wrong.

## Licence

MIT. Take the shape and ignore what does not fit — most of this was shaped by one project's specific
failures, and yours will differ.
