"""Write the token-id reference the Go tier-2 tokenizers must reproduce (#91).

Usage (after scripts/tier2_probe.py has built artifacts/tier2-probe/words):
  uv run --with 'model2vec[distill,quantization]' python scripts/tier2_tok_reference.py --n 500

Takes the first --n test-page inputs from artifacts/tier1-v2/cpu/reference-test.jsonl (built at
3,000 characters, as tier 1 and the probe build them; used for parity and latency only, never
for a choice), and writes artifacts/tier2-probe/reference.jsonl with, per page, the text and the
token ids of: potion-multilingual-128M's own tokenizer, and the probe's word-first tokenizer with
and without the Unigram fallback. Also writes the probe's vocabulary to
artifacts/tier2-probe/words/vocab.txt for the Go side. Page text stays in artifacts/.
"""

import argparse
import importlib.util
import json
from pathlib import Path

from model2vec import StaticModel


def probe_module():
    spec = importlib.util.spec_from_file_location("tier2_probe", "scripts/tier2_probe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--ref", type=Path, default=Path("artifacts/tier1-v2/cpu/reference-test.jsonl"))
    ap.add_argument("--art", type=Path, default=Path("artifacts/tier2-probe"))
    ap.add_argument("--potion", default="minishlab/potion-multilingual-128M")
    args = ap.parse_args()

    probe = probe_module()
    vocab = json.loads((args.art / "vocab.json").read_text())
    (args.art / "words" / "vocab.txt").write_text("\n".join(vocab) + "\n")
    potion = StaticModel.from_pretrained(args.potion)
    words = StaticModel.from_pretrained(str(args.art / "words"))
    wf = probe.WordFirst(words.tokenizer, vocab, fallback=True)
    wo = probe.WordFirst(words.tokenizer, vocab, fallback=False)
    with args.ref.open() as f, (args.art / "reference.jsonl").open("w") as out:
        for k, line in enumerate(f):
            if k == args.n:
                break
            text = json.loads(line)["input"]
            out.write(json.dumps({
                "text": text,
                "potion": potion.tokenizer.encode(text, add_special_tokens=False).ids,
                "wordfirst": wf.encode(text)[0],
                "wordonly": wo.encode(text)[0],
            }) + "\n")  # fmt: skip
    print(f"{min(k + 1, args.n)} pages -> {args.art / 'reference.jsonl'}")


if __name__ == "__main__":
    main()
