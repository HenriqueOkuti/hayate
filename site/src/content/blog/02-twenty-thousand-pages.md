---
title: "Weekend 2: twenty thousand pages from Common Crawl"
description: "Sampling Portuguese and English pages fairly from a 150 GB index without downloading it, and getting blocked once along the way."
pubDate: 2026-10-10
weekend: 2
tags: [data, decision]
draft: true
---

Hayate needs pages to learn from, and they have to be real, messy web pages, not a cleaned-up corpus. This weekend I pulled 10,000 Portuguese and 10,000 English pages out of Common Crawl, with the raw HTML, and finished a weekend ahead of schedule.

![Hayate sprints with a stack of web page cards under one arm, a few loose pages fluttering behind her, toward a concrete block with a red stop-hand sign and a dent from an earlier collision, on a pale blue-to-lavender background](../../assets/weekend-02.png)

## What I did

- **Picked the source.** [Common Crawl](https://commoncrawl.org/) is a free, public crawl of billions of pages, released about monthly. I used the latest one, CC-MAIN-2026-39. Cleaned datasets like FineWeb would have been quicker, but they throw away the raw HTML and filter out product and listing pages, which are exactly the pages a categorizer sees a lot of.
- **Sampled from the index.** Common Crawl publishes an index of every page as Parquet files (a column-based table format). I query it with DuckDB, keep pages whose main language is Portuguese or English, and allow at most 3 pages per domain so no big site takes over.
- **Fetched only what I needed.** Pages are stored in huge WARC archive files. I don't download those: an HTTP range request grabs just the bytes of one page. I keep each record byte for byte, so I can rerun anything later.
- **Extracted the text twice.** Every page goes through two extractors, trafilatura and resiliparse. Which one is better gets decided later, by which one makes the students more accurate.

The whole thing is [decision 0005](https://github.com/HenriqueOkuti/hayate/blob/main/docs/decisions/0005-page-sample.md).

## What surprised me

**The index is sorted, and that breaks the easy shortcut.** The full index is about 150 GB. It's split into chunks called row groups, and the obvious cheap trick is to pick a few chunks at random and sample inside them. But the index is sorted by reversed hostname (`br.com.example...`), so each chunk is a slice of the web by domain ending. One chunk was mostly Italian, the next almost all English. **Half of all eligible Portuguese pages sat in 21 of 1,497 chunks**, the `.br` ones. Random chunks would give a wildly different Portuguese count on every run.

![Line chart of the cumulative share of eligible pages against the number of index row groups, sorted fullest first. Portuguese (49M pages) passes 50% after 21 of 1,497 row groups and 70% after about 30; English (854M pages) rises gradually and passes 50% after 395.](../../assets/cc-index-concentration.svg)

The fix is a two-step sample. First a *census*: read only the small columns (language, domain, status) of the whole index, about 1 GB, and count the eligible pages in each chunk. Then pick chunks in proportion to those counts, and pages uniformly inside them. Every eligible page ends up with the same chance of being picked, and I only read the heavy URL columns of the chunks I drew, a few GB instead of about 48.

**English is 17 times Portuguese.** The crawl has 854M eligible English pages and 49M Portuguese ones. A sample proportional to that would leave almost no Portuguese to measure, so I went 50/50 on purpose.

## What went wrong

I got blocked. After a few GB of index reads and fetching pages at about 16 requests per second, Common Crawl's CDN started answering *every* request with a 403, even single ones. It lasted about 12 minutes. Their server says "slow down" with a 503 first, and I wasn't listening hard enough.

Now every request retries 503s with backoff, the fetcher is capped at 4 requests per second, and a 403 stops the run right away. The run also saves progress in shards of 1,000 pages, so it resumes from the last finished shard instead of starting over.

## Numbers

| | Portuguese | English |
| --- | --- | --- |
| Candidates fetched | 12,919 | 12,902 |
| Fetch or extraction failures | 0 | 0 |
| At least 200 characters of text | 12,401 | 11,483 |
| Kept | 10,000 | 10,000 |
| Distinct domains | 8,344 | 9,122 |
| Top domain endings | 82% `.br`, 11% `.pt` | 65% `.com` |

Median page text is about 1,400 characters with either extractor, and two thirds of pages have a meta description. Those are counts from the sample run on 2026-10-09, not model results. I'm not quoting extractor speeds yet: they ran 12 at a time on my desktop, which isn't a fair timing setup. Proper latency measurement gets its own weekend.

One thing to keep in mind: this is a fair sample of what Common Crawl collected, not of the web. Common Crawl's own choices about which sites to crawl shape it.

## Next weekend

The teacher pilot: label 500 of these pages with a local open model and an API model, and measure what it costs and how often they agree.
