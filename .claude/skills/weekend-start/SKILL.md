---
name: weekend-start
description: Start a Hayate weekend session - read where things stand, pick this weekend's row in the timeline, and propose a concrete plan with a "done when" outcome. Use at the start of a weekend work session or when the user says "let's start", "where were we" or "what's next".
disable-model-invocation: true
---

# Weekend start

Hayate is worked on in roughly one day per weekend. Get the user productive fast.

1. **Where things stand.** Read:
   - the roadmap board (`gh project item-list 2 --owner HenriqueOkuti`): the lowest-Order issue that isn't Done, and its issue body (`gh issue view N`);
   - `docs/timeline.md`: that issue's row, for context;
   - `docs/decisions/README.md`: what is pending and due this weekend;
   - the newest post in `site/src/content/blog/`: what was last reported;
   - `git log --oneline -15` and `git status`, if the repo is under git.
2. **Today's date.** Compare it with the row's planned weekend. If the plan has slipped, say by how much. Don't treat the dates as deadlines.
3. **Propose the session plan** in five lines or fewer:
   - the goal: the issue's "Done when";
   - 3–6 concrete steps, small enough to finish in one day;
   - any decision that must be made first (offer `/new-decision`);
   - anything that will cost money (API calls, cloud), with an estimate. Spend nothing until the user confirms.
4. **On the user's go-ahead**, move the issue to Doing on the board and create its branch, `<issue>-<slug>`.

Keep the reply short. The user wants to start working, not read a report.
