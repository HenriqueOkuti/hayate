# Data

Snapshot 2026-10-07. Sources and details are in [research/2026-10-07-data.md](research/2026-10-07-data.md). Public data only.

## Page sources

**Common Crawl** is the main source. It is closest to real ad inventory and keeps raw HTML.

- Latest crawl: CC-MAIN-2026-39. Crawls come out about monthly.
- Free over HTTPS (`data.commoncrawl.org`). No account is needed.
- **Sampling:**
  - Query the Parquet **columnar index** with DuckDB, filtering on `content_languages` (CLD2: `por`, `eng`, …), `fetch_status=200` and the TLD. Cap pages per `url_host_registered_domain`.
  - Fetch single records with HTTP range reads on `warc_filename`/`offset`/`length`, and read them with `warcio`/`fastwarc`.
- **Terms:** page owners' rights still apply. **Never republish page text.** URLs, labels and statistics are fine.

**Cleaned corpora** are for quick starts. They keep URLs and stream from Hugging Face:

| Corpus | Languages | License | Note |
| --- | --- | --- | --- |
| FineWeb | en | ODC-By | `sample-10BT` |
| FineWeb-2 | pt, id, vi, th (no en) | ODC-By | `por_Latn`, … |
| HPLT v3 | all | CC0 packaging | Has web-genre labels |

Avoid:

- **FineWeb-Edu:** biased toward educational pages.
- **MADLAD-400:** keeps no URLs.

The quality filters in cleaned corpora drop product and listing pages, which shifts the topic mix.

## Text extraction

| Extractor | Quality (SIGIR'23 mean F1) | Speed |
| --- | --- | --- |
| trafilatura (Apache-2.0) | 0.883, the best | ~0.56 MB/s/core, ~97 ms/page |
| resiliparse (Apache-2.0) | 0.859 | ~4.5 MB/s/core (8× faster), ~28 ms/page |

- Extraction costs about 100× the sub-ms inference target, so it is **reported as its own stage**.
- Choose between the two by **student F1**, not extraction F1.
- Also test **URL + title + meta description** as a near-free input. It doubles as the cache-miss fallback.

## Public labeled sets (sanity checks, never gold)

No good open, human-labeled IAB page dataset exists, so we build the gold sample ([measurement.md](measurement.md)). These help through a hand-made crosswalk to IAB Tier 1:

- **Curlie** (CC BY 3.0, many languages, with URLs): the best URL/domain → category ground truth.
- **Homepage2Vec Curlie set** (CC BY 4.0, 92 languages): website-level, 14 classes.
- **WebOrganizer** (Wettig et al. 2025, en): the closest prior work, an LLM teacher distilled into a small classifier on URL + text. Its Hugging Face artifacts have no license tag.
- **MN-DS** (CC BY 4.0, en): human-labeled news with IPTC topics.
- **SIB-200** (CC BY-SA 4.0): parallel across pt/en/id/vi/th, for cross-lingual checks.
- Kaggle "IAB-labeled" sets: unknown label provenance. Loose checks only.

## Fetching for the request benchmark

1. Freeze a URL list from the CC index, one URL per domain, and store the WARC coordinates with it.
2. **Offline:** time parse → extract → infer on the stored WARC records.
3. **Local replay:** serve the records from localhost, optionally with `tc netem` delay.
4. **Live fetch (polite):**
   - Follow RFC 9309 robots.txt rules and send a User-Agent with a contact URL.
   - Send at most about one request per host every few seconds.
   - Record DNS, connect, TTFB, download and the success rate.
