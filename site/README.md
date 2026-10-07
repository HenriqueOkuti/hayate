# Hayate blog

The progress blog, built with [Astro](https://astro.build) and deployed to
GitHub Pages by [`.github/workflows/pages.yml`](../.github/workflows/pages.yml).

```bash
npm install          # once
npm run dev          # http://localhost:4321, drafts included
npm run build        # production build into dist/, drafts excluded
```

## Writing a post

Add a Markdown file to `src/content/blog/` with this frontmatter:

```yaml
---
title: "Weekend 3: the teacher pilot"
description: "One sentence for the post list and RSS."
pubDate: 2026-10-25
weekend: 3
tags: [teacher]
draft: true        # flip to false to publish
---
```

Images go in `src/assets/` and are referenced relatively, e.g.
`![alt](../../assets/chart.png)`.

## Going live

1. Create the GitHub repo and push `main`.
2. In the repo, go to **Settings → Pages → Source** and choose **GitHub
   Actions**.
3. The workflow sets the site URL and base path from the Pages settings, so
   nothing is hard-coded. The blog appears at
   `https://<user>.github.io/<repo>/`.
