---
name: blog-post
description: Draft a progress post for the Hayate blog (Astro site in site/). Use when the user wants to write up a weekend, a result or a lesson learned, or when /weekend-wrap asks for one.
---

# Blog post

Posts live in `site/src/content/blog/` and are narrated by **Hayate-chan**, in the first person: she is the model ([docs/mascot.md](../../../docs/mascot.md)), smug, fast and slightly impatient with anything slow, and honest about what didn't work, including her own mistakes. Henrique is the person building her; she calls him Henrique. The teacher is the big LLM she learns from, and the students are her (name the tier where it matters). Facts and numbers stay exact whatever the voice. The audience is curious developers, not ML researchers, so explain jargon the first time it appears.

## File

`site/src/content/blog/NN-short-slug.md`, where `NN` is the next number after the newest post.

```yaml
---
title: "Weekend N: <what happened, in a few words>"
description: "<one sentence for the post list and RSS>"
pubDate: YYYY-MM-DD
weekend: N
tags: [<stage>, ...]
draft: true
---
```

Always create posts with `draft: true`. Only the user publishes, by flipping it to `false`.

## Shape

400–800 words:

1. **Hook:** what this weekend was about, in two sentences.
2. **What I did:** the steps, with one concrete detail each.
3. **What I learned / what surprised me:** the most interesting part.
4. **Numbers**, if any, in a small table. Only include results that passed the `ml-reviewer` agent's checks, and state the hardware and setup.
5. **Next weekend:** one or two lines.

## Media

Charts and images go in `site/src/assets/` and are referenced relatively, e.g. `![alt](../../assets/curve.png)`. Every image needs real alt text. The pipeline diagram `pipeline.svg` is already there.

## Rules

- Never paste page text from crawled pages (it may be copyrighted).
- Never mention the employer or anything non-public.
- Check it with `npm run -s lint:md` and preview it with `make site`.
