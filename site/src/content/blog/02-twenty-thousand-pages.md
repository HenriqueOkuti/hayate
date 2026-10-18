---
title: "Weekend 2: twenty thousand pages from Common Crawl"
description: "Sampling Portuguese and English pages fairly from a 150 GB index without downloading it, and getting blocked once along the way."
pubDate: 2026-10-10
weekend: 2
tags: [data, decision]
draft: false
---

I need pages to learn from, and they have to be real, messy web pages, not a cleaned-up corpus. This weekend Henrique pulled 10,000 Portuguese and 10,000 English pages out of Common Crawl for me, with the raw HTML, and we finished a weekend ahead of schedule. Fast, as is tradition.

![Hayate-chan sprints with a stack of web page cards under one arm, a few loose pages fluttering behind her, toward a concrete block with a red stop-hand sign and a dent from an earlier collision, on a pale blue-to-lavender background](../../assets/weekend-02.png)

## What we did

- **Picked the source.** [Common Crawl](https://commoncrawl.org/) is a free, public crawl of billions of pages, released about monthly. We used the latest one, CC-MAIN-2026-39. Cleaned datasets like FineWeb would have been quicker, but they throw away the raw HTML and filter out product and listing pages, which are exactly the pages I'll see a lot of.
- **Sampled from the index.** Common Crawl publishes an index of every page as Parquet files (a column-based table format). Henrique queries it with DuckDB, keeps pages whose main language is Portuguese or English, and allows at most 3 pages per domain so no big site takes over.
- **Fetched only what we needed.** Pages are stored in huge WARC archive files. We don't download those: an HTTP range request grabs just the bytes of one page. Each record is kept byte for byte, so anything can be rerun later.
- **Extracted the text twice.** Every page goes through two extractors, trafilatura and resiliparse. Which one is better gets decided later, by which one makes me more accurate.

The whole thing is [decision 0005](https://github.com/HenriqueOkuti/hayate/blob/main/docs/decisions/0005-page-sample.md).

## What surprised us

**The index is sorted, and that breaks the easy shortcut.** The full index is about 150 GB. It's split into chunks called row groups, and the obvious cheap trick is to pick a few chunks at random and sample inside them. But the index is sorted by reversed hostname (`br.com.example...`), so each chunk is a slice of the web by domain ending. One chunk was mostly Italian, the next almost all English. **Half of all eligible Portuguese pages sat in 21 of 1,497 chunks**, the `.br` ones. Random chunks would give a wildly different Portuguese count on every run.

![Line chart of the cumulative share of eligible pages against the number of index row groups, sorted fullest first. Portuguese (49M pages) passes 50% after 21 of 1,497 row groups and 70% after about 30; English (854M pages) rises gradually and passes 50% after 395.](../../assets/cc-index-concentration.svg)

The fix is a two-step sample. First a *census*: read only the small columns (language, domain, status) of the whole index, about 1 GB, and count the eligible pages in each chunk. Then pick chunks in proportion to those counts, and pages uniformly inside them. Every eligible page ends up with the same chance of being picked, and only the heavy URL columns of the drawn chunks get read, a few GB instead of about 48.

**English is 17 times Portuguese.** The crawl has 854M eligible English pages and 49M Portuguese ones. A sample proportional to that would leave almost no Portuguese to measure me on, so we went 50/50 on purpose.

## What went wrong

We got blocked. After a few GB of index reads and fetching pages at about 16 requests per second, Common Crawl's CDN started answering *every* request with a 403, even single ones. It lasted about 12 minutes. Their server says "slow down" with a 503 first, and we weren't listening hard enough. Yes, I know: the one time being fast was the problem.

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

Median page text is about 1,400 characters with either extractor, and two thirds of pages have a meta description. Those are counts from the sample run on 2026-10-09, not model results. No extractor speeds yet: they ran 12 at a time on Henrique's desktop, which isn't a fair timing setup. Proper latency measurement gets its own weekend, and I intend to look good in it.

One thing to keep in mind: this is a fair sample of what Common Crawl collected, not of the web. Common Crawl's own choices about which sites to crawl shape it.

## Next weekend

The teacher pilot: label 500 of these pages with a local open model and an API model, and measure what it costs and how often they agree.
