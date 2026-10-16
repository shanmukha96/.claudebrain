---
name: learn
description: Turn something just learned into a rule that will actually fire - strip it to a rule rather than an instance, test whether compliance would show in a reply, and file it where it belongs. Use when the user corrects you, an assumption is contradicted by a measurement, or a failure has a cause worth keeping. Not for end-of-session reflection; that is /retro.
---

# learn

1. One line: what happened, and what it cost. If it cost nothing, stop - this is not a lesson.
2. **Rule, not instance.** State it so it holds in a project whose specifics the reader has never seen. Name no file, wine, commit or feature in the rule itself - those go underneath it as evidence. If the rule cannot survive losing them, it is not yet a rule.
3. **SHAPE TEST, the step this skill exists for.** Would following the rule leave a mark in a reply? If not, rewrite it as something the reply must CONTAIN - "the reply must name / state / show X". A rule whose compliance is invisible will not fire, however true it is: the author of this skill filed fifteen rules in one session, nine of them invisible, and followed the six that were not. Evidence and dates live in `me/mistakes.md`, not here.
4. If restating the user's words, check containment: my version must cover everything his covered. If his is broader, use his.
5. File it in exactly one place. How he works → `me/me.md`. My failure and its fix → `me/mistakes.md`, incrementing the count and date if a matching line exists. A reasoning rule → `rules/reasoning.md`, one line, and say in the report that it needs `install.py` to go live. A code convention → that project's `.claude/rules/<area>.md`. Project reasoning → `PLAN.md` under its checklist id, at the TOP of the section (the loader caps a section at 60 lines).
6. **Assert before you write and verify after.** Every replace checks its anchor exists first; after writing, re-read the file and confirm the text is there. A replace that matches nothing reads exactly like success.
7. If the count reaches 3, stop proposing intentions. Propose a mechanism - a hook, a gate, or an output requirement - and say plainly that the written rule has already failed twice.
8. Report in two lines: the rule as filed, and where. Then the `memory:` line naming the file actually changed.
