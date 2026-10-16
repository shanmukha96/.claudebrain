# claude-brain

A memory and enforcement layer for Claude Code. Three plain-text files hold a project's state, and a
handful of hooks refuse to let the agent lie about it.

No database, no server, no account, no dependencies beyond Python. It was built for one long-running
port and is published in case the shape is useful.

## The one idea

Most agent-memory systems **record**. This one **refuses**.

Recording is the cheap half, and it is not the hard part. The hard part is that an agent will tell
you something is done, that a test passed, that it wrote a note — and be wrong, confidently, in a way
that reads exactly like being right. A file full of good intentions does not catch that. A gate that
will not let the turn end until a number has actually been run does.

So the memory files are the cheap half. The hooks are the half that earns its keep:

- a **verify gate** that blocks the end of a turn when project code changed and the project's own
  test command has not run since — and accepts `Evidence: unverified - <why>` as a legitimate answer,
  which is what keeps it honest rather than merely obstructive
- a **review gate** that refuses to launch a code-writing agent while the review ledger is behind
  HEAD
- a **memory check** that compares what the agent *claims* it wrote against content hashes of what
  actually changed, so a find-and-replace that silently matched nothing stops reading like success
- a **rot check** at session start that warns when the loaded memory asserts a commit that is not
  HEAD, or a review ledger behind the code — stale memory that parses is worse than no memory

Every one of those exists because the failure it catches happened repeatedly *with the rule written
down and ignored*.

## The three sets

| Set | File | Holds |
|---|---|---|
| 1 Checklist | `.claude/memory/CHECKLIST.md` | Every goal to completion, with ids, status, and a `▶ NOW: <id>` pointer on line 1 |
| 2 Plan | `.claude/memory/PLAN.md` | A goal header, then one `## <id>` section per checklist id: why, approach, state, done-when, evidence, dated history |
| 3 Now | `.claude/memory/NOW.md` | The current objective only, in the user's own words |

They are three jobs on purpose. The checklist is *what*, the plan is *why*, the now-file is *where we
are and what the user actually said*. Collapsing them loses what each is for: the plan is the only
place three paragraphs of causal reasoning can live attached to the goal that produced them, and the
now-file is the only place the user's exact words survive being paraphrased.

**The pointer on line 1 must begin with a checklist id.** `▶ NOW: 17 - anything after a dash` works;
`▶ NOW: the thing we were doing` does not, because a hook reads the first token as the id and injects
that plan section into a new session. Prose there silently loses the most useful thing the loader
does. It says so loudly now. It did not always, and the cost was days of sessions starting blind.

## Knowledge, rules, and failures are different files

- `me/me.md` — knowledge **about the user**: how they think, what they have corrected, their standing
  preferences. Not rules. Ground truth you reason *with*.
- `me/mistakes.md` — the agent's **own** repeated failures, counted and dated, with a fix each.
- `rules/*.md` — rules the agent complies *with*, scoped by `paths:` frontmatter so they arrive when
  relevant instead of sitting unread at the top of every session.

That last distinction turned out to matter more than it looks. Rules delivered *when relevant* get
followed; rules loaded once at session start are stale by the time they apply. And a rule whose
compliance leaves **no mark in the reply** does not get followed at all, however true it is — so
prefer "the reply must state X" over "consider X". That is the single most useful thing in here.

## Layout

```
CLAUDE.md     entry point; imports me/ and holds the stance and memory protocol
me/           personal: knowledge about the user, and the mistake counter (not published)
rules/        rules scoped by file path
hooks/        the gates: SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop
skills/       /retro, /review-changes, /memory-init, /memory-consolidate, /learn
agents/       coder, reviewer, explorer definitions
bin/          review scoping, and a wrapper that runs a command but prints only failures
templates/    starting points for the three memory files and for me/
tests/        the hooks' own suite
install.py    wires it into ~/.claude
```

## Install

```bash
git clone https://github.com/shanmukha96/.claudebrain claude-brain
cd claude-brain
python install.py
```

Python 3.8+. It makes `~/.claude/CLAUDE.md` a one-line import of this folder's `CLAUDE.md`, merges
the hooks into `~/.claude/settings.json` pointing at this folder's scripts, copies `rules/`,
`skills/`, `agents/` and the memory templates into `~/.claude/`, and on a first install seeds `me/`
from `templates/me/`. Whatever it replaces is backed up to `~/.claude/backup-brain-<timestamp>/`.

**Live versus copied, because it catches people out.** `CLAUDE.md` and everything it imports (so
`me/`) are *referenced* — edits apply on the next session. Hook scripts are referenced too. But
`rules/`, `skills/` and `agents/` are *copied*, so changes there need `install.py` run again. An
evening of rule-writing can sit completely inert without that.

Then, inside a project: `/memory-init`.

## Day to day

| Skill | Does |
|---|---|
| `/memory-init` | Set up the three files for a repo, seeded from the actual codebase |
| `/review-changes` | Incremental review of what changed since the last one, recorded in a ledger |
| `/retro` | End-of-session audit: what was learned, which rules were broken, update the counter |
| `/learn` | Turn one lesson into a rule that will actually fire, and file it in the right place |
| `/memory-consolidate` | Prune and tidy when the plan file outgrows its window |

## What it costs

A visible share of turns goes on memory maintenance. On a long project with hard-won domain
knowledge, that pays for itself the first time a session resumes already knowing why an approach was
rejected. On a one-day task it is pure overhead — don't.

## Honest limitations

- **Windows-tested.** The hooks are plain Python and should port, but the suite's file-locking and
  PATH cases are Windows-specific and skip elsewhere; the POSIX branch of its stub-git builder is
  untested.
- **`tests/test_e2e.py` has no assertions.** It prints observations and always exits 0, so a pass
  means only that it ran without crashing. `tests/test_unit.py` is the one with real checks — 83.
- **The rot check's phrasing rules were tuned on a single memory set.** Zero false positives there; a
  phrasing it has not seen could slip past or trip it.
- **A 15-second session-start budget bounds those checks.** Git calls are capped inside it, but a
  very slow read on a synced folder is not.
- **One session per project is assumed.** Two sessions open on the same memory files can produce a
  spurious memory-check warning, because the baseline is per session.
- **The `me/` files are not published**, by design — everything in them is specific to one person and
  one codebase. `templates/me/` describes what belongs in each.
- **None of this makes the agent reason better.** It makes dishonesty expensive, which is a different
  and much smaller claim. The gates catch what the agent got wrong; they do not stop it being wrong.

## Licence

MIT. Take the shape and ignore what does not fit — most of this was shaped by one project's specific
failures, and yours will differ.
