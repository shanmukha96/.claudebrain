---
name: retro
description: End-of-session retrospective and self-audit - file what was learned this session into the right place (me.md, PLAN, rules, or a new skill), audit whether the brain's rules were followed, and update the mistake counter. Use when the user runs /retro or says they're wrapping up a session.
---
# retro

Keep it to one short pass. Only file lessons with evidence from this session.

1. List what happened this session in 3–6 bullets: corrections the user made, things that failed, things that worked, anything repeated.
2. Audit yourself against the brain: for each rule in CLAUDE.md, `guides/non-code.md`, the skills used and `me/me.md`, was it followed? List every skipped step or broken rule, with the moment it happened. Be honest; the user checks.
3. Update `me/mistakes.md`: for each mistake from 1–2, if a matching line exists, increment its count and date; otherwise add it at count 1. Any line at count 3+ needs a stronger fix: propose a rule change in CLAUDE.md or a hook, and say so in the report.
4. File each lesson in exactly one place:
   - How the user works or wants things → brain `me/me.md` (one dated line; merge with an existing line if similar). Don't commit; the weekly backup hook does.
   - Project reasoning, decisions, dead ends → `PLAN.md` under the relevant ID (dated history line; dead ends also go to "Rejected ideas").
   - A code convention for this project → `.claude/rules/<area>.md` in the project, with a ❌/✅ example and `paths:` frontmatter.
   - Something done more than once a day → propose a skill (name + one-line description). Don't create it without the user's OK.
5. Make sure CHECKLIST and NOW match reality; clear NOW if the objective is done.
6. Report in ≤8 lines: audit result (rules broken), mistakes counted (flag any at 3+), what went where, ending with the `memory: ...` line.
