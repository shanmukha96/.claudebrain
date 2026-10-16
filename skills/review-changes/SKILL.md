---
name: review-changes
description: Incremental review of code changes by the reviewer agent - scopes the review to files changed since the last review plus the files that import them, skips anything already reviewed with identical content, then records results in .claude/memory/REVIEW.md and advises the user. Use when the user runs /review-changes, or after the coder agent reports a task done. Pass "full" for a whole-codebase review.
---
# review-changes

You (the main session) run this; the `reviewer` agent only reads and reports. Only you write REVIEW.md.

1. If `.claude/memory/REVIEW.md` doesn't exist, copy it from `~/.claude/memory-templates/REVIEW.md`.
2. Get the scope with the script, not by reading files:
   `python "<brain>/bin/review_scope.py" <repo> <ref from REVIEW.md "Last reviewed", omit if none>` (add `--full` only if the user passed "full").
   If `changed` is empty, say "nothing new to review" and stop.
3. Spawn the `reviewer` agent with a brief containing: the task's PLAN id, the base ref, the `changed`, `impacted` and `skipped` lists, and the "Open findings" section of REVIEW.md. Nothing else; it reads memory itself.
4. When it reports, update REVIEW.md:
   - "Last reviewed": the `head` ref and today's date.
   - "Open findings": add new ones as `- [ ]`, tick fixed ones `- [x]`.
   - "Reviewed": for each file in its "Checked" list, one line `` - `path` sha:<hash from the script's "hashes"> YYYY-MM-DD (id) ``, replacing that path's older line.
5. Advise the user (you are the advisor, the reviewer is not): in plain words, what changed, what the reviewer found and how serious it is, what you recommend (fix now / later / ignore and why), and what they should understand before this goes to the team. End with the `memory:` line.
