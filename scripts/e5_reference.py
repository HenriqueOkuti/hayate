"""Write an ONNX Runtime reference for the Go tier-3 check (#86): ids, mask and embeddings.

Usage (onnxruntime and tokenizers are not project dependencies; uv fetches them for this run):
  uv run --with onnxruntime --with tokenizers --with huggingface_hub \
      python scripts/e5_reference.py --n 20

Downloads intfloat/multilingual-e5-small's ONNX export, tokenizes the first --n test-page inputs
(prefixed "passage: ", cut to --max-tokens), runs the model with ONNX Runtime on the CPU and
writes artifacts/e5-reference.json with the input ids, the attention mask, the model's input
names and the mean-pooled, l2-normalized embeddings. Page text stays in artifacts/.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="intfloat/multilingual-e5-small")
    ap.add_argument("--ref", type=Path, default=Path("artifacts/tier1-v1/cpu/reference-test.jsonl"))
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--out", type=Path, default=Path("artifacts/e5-reference.json"))
    args = ap.parse_args()

    onnx_path = hf_hub_download(args.model, "onnx/model.onnx")
    tok = Tokenizer.from_file(hf_hub_download(args.model, "onnx/tokenizer.json"))
    tok.enable_truncation(args.max_tokens)
    tok.enable_padding(pad_id=1, pad_token="<pad>")
    texts = []
    with args.ref.open() as f:
        for line in f:
            texts.append("passage: " + json.loads(line)["input"])
            if len(texts) == args.n:
                break
    enc = tok.encode_batch(texts)
    ids = np.array([e.ids for e in enc], dtype=np.int64)
    mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
    sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    names = [i.name for i in sess.get_inputs()]
    feed = {"input_ids": ids, "attention_mask": mask}
    if "token_type_ids" in names:
        feed["token_type_ids"] = np.zeros_like(ids)
    hidden = sess.run(None, feed)[0]
    m = mask[..., None].astype(np.float32)
    pooled = (hidden * m).sum(1) / m.sum(1)
    pooled /= np.linalg.norm(pooled, axis=1, keepdims=True)
    args.out.write_text(json.dumps({
        "model": args.model, "input_names": names, "ids": ids.tolist(), "mask": mask.tolist(),
        "embeddings": pooled.tolist(), "onnx_path": onnx_path,
    }))  # fmt: skip
    print(f"{len(texts)} texts, {ids.shape[1]} tokens, inputs {names}, dim {pooled.shape[1]}")


if __name__ == "__main__":
    main()
