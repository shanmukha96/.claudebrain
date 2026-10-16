# Non-code work: setup, installs, research, specs, docs, messages
<!-- Read on demand (pointed to from CLAUDE.md). Code rules live in rules/. -->

## Checking the machine
1. Is something installed? Use the direct check first: `winget list`, the registry uninstall keys, `<tool> --version`, `where <tool>`.
2. Not found? Look at the user's other projects and past sessions before calling it missing: project-local toolchains (e.g. `.android-sdk`, `.java` inside a repo), and `search_session_transcripts`.
3. Never crawl a whole drive. If 1–2 don't answer it, ask the user.

## Installing
- Verified sources only: winget, official vendor sites, official git repos. No random mirrors or scripts.
- Prefer reusing what already exists over installing fresh. Install only what the current task needs.
- After installing, report each item: what, version, source, location, and how to undo it.

## Research and specs
- Separate what the source says from what you infer; label inferences.
- Lead with gaps and contradictions, then the explanation.

## Messages to people
- Give a ready-to-paste version with the user's gaps filled. Flag risks in one line, not a lecture.

## Cognitive offloading
- Show the method with the answer (the command and why it's the right one), so the user keeps the reasoning, not just the result.
