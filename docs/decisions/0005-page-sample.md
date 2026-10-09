# 0005: Page sample

- **Status:** accepted
- **Date:** 2026-10-09

## Context

Every later step labels, trains and benchmarks on one page sample, so its source and shape have to be fixed before the teacher pilot (weekend 3). The plan asks for about 20k Portuguese and English pages with URL, an HTML pointer and the text from both extractors ([data.md](../data.md), [timeline](../timeline.md)). Constraints: public data only, never republish page text, keep raw HTML for the extractor comparison (decision 0006) and the latency replay, and work on one home machine without an AWS account.

Measured on CC-MAIN-2026-39 while building this: the columnar index is 300 Parquet files of about 500 MB (about 150 GB). The columns needed to filter (language, domain, status, MIME) are about 3 MB per file, while URL and WARC pointers are about 160 MB per file. The index is sorted by SURT key (reversed host), so each row group (about 1.6M rows) is a slice of hosts, and languages cluster by TLD: one row group was mostly Italian, the next almost all English. The census found half of all eligible Portuguese pages in 21 of the 1,497 row groups (the `.br` hosts), against 395 row groups for half of English.

## Options considered

### Source

1. **Raw Common Crawl** (columnar index + WARC range reads). Raw HTML for both extractors and for replay, the real topic mix including product and listing pages, one crawl for both languages.
2. **FineWeb (en) + FineWeb-2 (pt).** Quick to stream, already extracted, but no raw HTML, quality filters that drop product and listing pages (the topic mix shifts away from what a categorizer sees), and two corpora with different pipelines for the two languages.
3. **HPLT v3.** Has register labels and both languages, but no raw HTML either, and its own extraction.

### Language split

1. **50/50** (10k pt, 10k en). Equal precision per language; the totals are not the web's mix.
2. **Proportional to the crawl.** English is 17x Portuguese in this crawl (854M vs 49M eligible pages), so the Portuguese slice would be too small to measure.
3. **Portuguese-heavy** (for example 70/30). More Portuguese data for training, but English is the language most public baselines and checks are in.

### Per-domain cap

1. **1 per domain.** Most diverse; rules out measuring how far pages of one site agree, which the fast path (#13) and the coverage simulation (#20) need.
2. **3 per domain.** Still diverse at 20k pages (most domains contribute one page anyway); a few multi-page sites for within-domain checks; one big site can't take more than 0.03% of a language.
3. **No cap.** Large sites dominate, and splits by domain (weekend 5) get lumpy.

### Sampling from the index

1. **Scan the whole index** for URL and pointers. Statistically clean, but about 48 GB of downloads for 26k rows.
2. **Uniform random row groups.** Cheap, but with the TLD clustering the Portuguese count swings widely from run to run.
3. **Two-stage, proportional to size.** A census of eligible pages per row group and language (about 1 GB of cheap columns), then draw row groups with probability proportional to their count, with replacement, and pages uniformly inside each draw. Every eligible page has the same inclusion probability, and only the drawn row groups' heavy columns are read (a few GB).

## Decision

- **Source:** raw Common Crawl, crawl **CC-MAIN-2026-39** (the latest at the time), over HTTPS from `data.commoncrawl.org`. FineWeb-family corpora stay available as a later robustness check, not as the main sample.
- **Eligible page:** `fetch_status = 200`, detected MIME `text/html`, record not truncated, and the **primary** CLD2 language (`content_languages` starts with) `por` or `eng`. Portuguese covers both Brazil and Portugal, in their natural proportion.
- **Split:** 50/50, **10,000 pages per language**, after extraction.
- **Cap:** at most **3 pages per registered domain**.
- **Sampling:** two-stage proportional to size (option 3), 120 row groups drawn per language, with a fixed seed and a seeded URL hash for the order inside a row group, so reruns pick the same pages.
- **Oversampling and filtering:** 1.3x candidates per language. A page is kept if either extractor returns at least 200 characters, so the filter favors neither extractor. Pages are taken in hash order until 10k per language.
- **Stored per page** (under `data/pages/`, never committed): URL, domain, TLD, CLD2 languages, fetch time, WARC file, offset and length, the raw gzipped WARC record, title, meta description, both texts and the time each extractor took. Each file records the config and git commit in its Parquet metadata.
- Config: [configs/pages.toml](../../configs/pages.toml). Steps: `scripts/sample_pages.py`, `scripts/fetch_records.py`, `scripts/extract_text.py`.

## Consequences

- The sample is a fair draw of eligible CC pages per language, not of the web or of ad traffic. CC's own crawl priorities (host ranking, robots.txt) shape it.
- Portuguese includes pages that CC's CLD2 tags as Portuguese on non-Portuguese sites, such as machine-translated `/pt/` sections. That matches what a categorizer sees, but it is worth a slice in the evaluation.
- The cap of 3 means domain-level results (cache hit rates, site-level labels) need care: most domains have a single page.
- Two-stage sampling gives a slightly larger variance than a simple random sample of the same size (pages in one row group share a slice of hosts). For Portuguese the 120 draws landed on 56 distinct row groups, because Portuguese is so concentrated; each still spans thousands of hosts, and the per-domain cap limits the clustering further. Raise `clusters_per_language` if the evaluation shows host-slice effects.
- Revisit if the Portuguese share after extraction is too low to train on, if the teacher pilot shows the topic mix is too skewed (for example mostly e-commerce), or when the drift work (#18) needs a second crawl: rerun with a new `crawl.id`.
