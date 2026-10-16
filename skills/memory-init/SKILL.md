---
name: memory-init
description: Set up the three-set project memory (.claude/memory/ with CHECKLIST, PLAN, NOW) for the current repo, seeded from the real codebase and the user's stated goal. Use when the user runs /memory-init or a multi-session project has no .claude/memory/.
---
# memory-init

1. If `.claude/memory/` exists, stop and say so; offer `/memory-consolidate`.
2. Ask the user, in one message: the final goal, hard constraints, and the first thing they want to work on. Wait for the answer.
3. Survey cheaply: README, dependency manifests, top-level tree (2 levels), test/lint/typecheck commands, `git log --oneline -15`.
4. Copy the templates from `~/.claude/memory-templates/` into `.claude/memory/`. Append `.claude/memory/.unverified` to `.gitignore`.
5. Fill them:
   - PLAN.md goal header from the user's answers. Set `Verify:` to the exact test/lint/typecheck commands you confirmed exist (separate with `;`). If none exist, say so and ask the user. Note facts inferred from code as "inferred from <file>".
   - CHECKLIST.md: propose milestones and goals with IDs toward the final goal. Mark what the code shows is already done as `[x]` with the evidence in PLAN.md.
   - NOW.md: the first objective, in the user's words.
6. Show the user the CHECKLIST and ask them to correct it before work starts. Do not invent conventions.
