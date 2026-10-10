"""Export the mascot rig layers from a See-through PSD to WebP for the site.

The PSD comes from See-through (shitagaki-lab/see-through) run on
docs/assets/mascot/hayate-base.png; see docs/mascot.md. This script drops the
two layers See-through got wrong (headwear, nose), splits the arms so the far
one sits behind the jacket, crops every layer to one shared canvas and writes
them in stacking order.

Usage: uv run --with psd-tools --with scipy python scripts/mascot_rig_export.py \
    docs/assets/mascot/rig/hayate-base.psd site/public/rig
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from psd_tools import PSDImage
from scipy import ndimage

DROP = {"headwear", "nose"}
# Shared canvas in PSD pixels (left, top, right, bottom) and headroom on top,
# so rotations never clip the hair.
CROP = (452, 0, 856, 1280)
PAD_TOP = 16


def full_layer(psd: PSDImage, layer) -> np.ndarray:
    canvas = Image.new("RGBA", psd.size, (0, 0, 0, 0))
    im = layer.topil().convert("RGBA")
    canvas.paste(im, (layer.left, layer.top), im)
    return np.array(canvas)


def split_arms(arms: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split the two arms; return (near, far), near being the one on the left."""
    labels, n = ndimage.label(arms[..., 3] > 8)
    sizes = ndimage.sum(np.ones_like(labels), labels, range(1, n + 1))
    two = np.argsort(sizes)[::-1][:2] + 1
    two = sorted(two, key=lambda b: ndimage.center_of_mass(labels == b)[1])
    out = []
    for b in two:
        part = arms.copy()
        part[..., 3] = np.where(labels == b, arms[..., 3], 0)
        out.append(part)
    return out[0], out[1]


def main(psd_path: str, out_dir: str) -> None:
    psd = PSDImage.open(psd_path)
    layers, arms = [], None
    for layer in psd:
        name = layer.name.replace(" ", "-")
        if name == "handwear":
            arms = split_arms(full_layer(psd, layer))
        elif name not in DROP:
            layers.append((name, full_layer(psd, layer)))
    # The far arm goes behind the jacket, the near one in front of it.
    near, far = arms
    names = [n for n, _ in layers]
    layers.insert(names.index("topwear") + 1, ("arm-near", near))
    layers.insert(names.index("topwear"), ("arm-far", far))

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    w, h = CROP[2] - CROP[0], CROP[3] - CROP[1] + PAD_TOP
    for name, arr in layers:
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        canvas.paste(Image.fromarray(arr).crop(CROP), (0, PAD_TOP))
        canvas.save(out / f"{name}.webp", lossless=True, method=6)
    meta = {"width": w, "height": h, "order": [n for n, _ in layers]}
    (out / "layers.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(w, h, [n for n, _ in layers])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
