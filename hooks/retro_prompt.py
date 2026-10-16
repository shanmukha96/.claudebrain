"""UserPromptSubmit hook: retro reminders and day-change retro.

- Counts the user's messages per session. Every BRAIN_RETRO_EVERY (default 10) messages since
  the last retro, tells Claude to remind the user to run /retro.
- If the date changed since this session's previous message, tells Claude to run the /retro
  procedure itself before answering, and runs the weekly brain backup check.
- A prompt starting with /retro resets the count.
"""
from __future__ import annotations

import json
import sys
from datetime import date

from brainlib import backup_if_due, day_changed, load_state, reminder_due, save_state


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    session = data.get("session_id") or "unknown"
    prompt = (data.get("prompt") or "").strip().lower()
    today = date.today()

    state = load_state(session)
    notes = []
    if prompt.startswith("/retro"):
        state["count"] = 0
    elif day_changed(state.get("date"), today):
        notes.append(
            f"The date changed since this session's last message ({state.get('date')} -> {today}). "
            "Before answering, run the /retro procedure (including the self-audit and mistake counter) "
            "for the work so far, report it briefly, then answer the user's message."
        )
        notes.append(backup_if_due(today))
        state["count"] = 0
    else:
        state["count"] = state.get("count", 0) + 1
        if reminder_due(state["count"]):
            notes.append(
                f"{state['count']} messages since the last retro. End your reply with one line "
                "reminding the user to run /retro when convenient, and say why if anything worth filing happened."
            )
    state["date"] = today.isoformat()
    save_state(session, state)

    if notes:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": " ".join(notes),
        }}))


if __name__ == "__main__":
    main()
