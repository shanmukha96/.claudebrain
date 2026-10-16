---
name: memory-consolidate
description: Prune and tidy the three-set project memory - collapse finished checklist milestones, trim PLAN sections, check memory against the code, and merge user patterns in me.md. Use when the user runs /memory-consolidate or PLAN.md grows past ~400 lines.
---
# memory-consolidate

Memory that only grows turns into noise that steers you wrong. This is the pruning pass.

1. Read all of `.claude/memory/` and the brain's `me/me.md`.
2. CHECKLIST: collapse finished top-level milestones to one line; confirm `▶ NOW` points at a real open item.
3. PLAN: for finished IDs, shrink the section to why, final approach, evidence and one history line. Keep the goal header and rejected ideas intact.
4. Check claims against the code. Anything the code contradicts: fix it or delete it, and say which.
5. me.md: merge duplicates, keep under 40 lines, then commit in the brain folder with `mem: consolidate`.
6. Report in a few lines what was collapsed, fixed and deleted, ending with `memory: consolidated`.
