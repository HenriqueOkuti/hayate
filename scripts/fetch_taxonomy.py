"""Download the pinned IAB Content Taxonomy, verify its sha256 and write the frozen label set.

Usage: uv run python scripts/fetch_taxonomy.py --config configs/taxonomy.toml

Writes to the configured output dir (under data/, git-ignored):
- the original TSV, byte for byte;
- labels.json: the label set from decision 0002, with the source pin and config it came from.
"""

import argparse
import json
import tomllib
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from hayate.taxonomy import iab


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    cfg = tomllib.loads(args.config.read_text())
    src, lab = cfg["source"], cfg["labels"]

    out = Path(cfg["output"]["dir"])
    out.mkdir(parents=True, exist_ok=True)
    tsv = out / Path(src["path"]).name

    if tsv.exists():
        data = tsv.read_bytes()
    else:
        data = iab.download(iab.raw_url(src["repo"], src["commit"], src["path"]))
    iab.verify(data, src["sha256"])
    tsv.write_bytes(data)

    nodes = iab.parse(data)
    labels = iab.label_set(nodes, lab["max_tier"], lab["exclude_tier1"])
    (out / "labels.json").write_text(
        json.dumps(
            {
                "source": src,
                "labels_config": lab,
                "labels": [asdict(n) | {"tier": n.tier} for n in labels],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    by_tier = Counter(n.tier for n in labels)
    print(f"verified {tsv} ({len(nodes)} nodes, sha256 ok)")
    print(
        f"label set: {len(labels)} labels, tiers {dict(sorted(by_tier.items()))}, "
        f"{sum(n.scd for n in labels)} SCD -> {out / 'labels.json'}"
    )


if __name__ == "__main__":
    main()
