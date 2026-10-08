---
name: weekend-wrap
description: Wrap up a Hayate weekend session - update the timeline, record decisions, draft the progress blog post, and run the preflight checks. Use when the user says they're stopping for the weekend, "wrap up", "let's call it" or similar.
disable-model-invocation: true
---

# Weekend wrap-up

1. **What happened.** Summarize this session's work from the conversation, plus `git diff --stat` and `git log` since the weekend started (if under git). Separate what is done, what is partial and what is blocked.
2. **Board.** Tick the finished scope items in the weekend's issue. If its "done when" is met, the PR that closes it (`Closes #N`) moves it to Done; otherwise leave it in Doing and add a comment on what's left. New work that came up gets its own issue (task template, milestone, labels, on the board). Change `docs/timeline.md` only if the plan itself changed; don't reshuffle future rows unless the user asks.
3. **Decisions.** Any choice made this session that isn't recorded yet gets a record (follow `/new-decision`). Update `docs/decisions/README.md`.
4. **Docs.** If facts changed (versions, numbers, approach), update the topic doc. Delegate a broader sweep to the `docs-keeper` agent.
5. **Blog post.** Draft the weekend's post with `/blog-post` (`draft: true`), in the user's voice, from what actually happened. Include real numbers only if they passed the `ml-reviewer` agent's checks.
6. **Preflight.** Run `/preflight`. Then delete any merged branches, local and remote (`git fetch --prune`, `git branch --merged main`); never an unmerged one.
7. **Hand-off.** Reply with:
   - three lines on where things stand;
   - the first step for next weekend;
   - the draft post's path, for the user to edit and publish.

Don't commit or push unless the user asks.
