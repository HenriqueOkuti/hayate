---
name: weekend-wrap
description: Wrap up a Hayate weekend session - update the timeline, record decisions, draft the progress blog post, and run the preflight checks. Use when the user says they're stopping for the weekend, "wrap up", "let's call it" or similar.
disable-model-invocation: true
---

# Weekend wrap-up

1. **What happened.** Summarize this session's work from the conversation,
   plus `git diff --stat` and `git log` since the weekend started (if under
   git). Separate what is done, what is partial and what is blocked.
2. **Timeline.** Update `docs/timeline.md`: set this weekend's row to `done`,
   or leave it `doing` with a one-line note on what's left. Don't reshuffle
   future rows unless the user asks.
3. **Decisions.** Any choice made this session that isn't recorded yet gets a
   record (follow `/new-decision`). Update `docs/decisions/README.md`.
4. **Docs.** If facts changed (versions, numbers, approach), update the topic
   doc. Delegate a broader sweep to the `docs-keeper` agent.
5. **Blog post.** Draft the weekend's post with `/blog-post`
   (`draft: true`), in the user's voice, from what actually happened. Include
   real numbers only if they passed the `ml-reviewer` agent's checks.
6. **Preflight.** Run `/preflight`.
7. **Hand-off.** Reply with:
   - three lines on where things stand;
   - the first step for next weekend;
   - the draft post's path, for the user to edit and publish.

Don't commit or push unless the user asks.
