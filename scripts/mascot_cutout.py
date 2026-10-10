"""Cut the mascot out of a white-background image into a transparent PNG.

Background removal is BiRefNet (MIT) through rembg (MIT). Edge pixels are then
un-mixed from the white background and the outermost pixel is trimmed, so the
cut-out has no light fringe on a dark page.

Usage: uvx --from "rembg[cpu]" --with pillow --with numpy python scripts/mascot_cutout.py IN OUT
"""

import sys

import numpy as np
from PIL import Image, ImageFilter
from rembg import new_session, remove

MODEL = "birefnet-general"


def cutout(src: Image.Image) -> Image.Image:
    mask = remove(src, session=new_session(MODEL), only_mask=True)
    # Trim one pixel off the edge, where the colour is mostly background.
    mask = mask.filter(ImageFilter.MinFilter(3))
    rgb = np.asarray(src.convert("RGB"), dtype=np.float32)
    a = np.asarray(mask, dtype=np.float32)[..., None] / 255.0
    # Observed = a * colour + (1 - a) * white, so solve for the colour.
    safe = np.maximum(a, 1e-3)
    un = np.clip((rgb - (1.0 - a) * 255.0) / safe, 0, 255)
    rgba = np.concatenate([un, a * 255.0], axis=-1).round().astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


if __name__ == "__main__":
    src, out = sys.argv[1], sys.argv[2]
    cutout(Image.open(src)).save(out, optimize=True)
