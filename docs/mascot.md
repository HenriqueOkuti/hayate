# Mascot

Hayate (疾風, "gale") is the project mascot: a smug, fast, cyan-haired runner. This page is her canon and the way new images of her are made. The redesign of 2026-10-10 replaced the earlier dark-teal version ([#36](https://github.com/HenriqueOkuti/hayate/issues/36)).

## Canon

- **References:** [hayate-base.png](assets/mascot/hayate-base.png) (full body, standing) and [hayate-sheet.png](assets/mascot/hayate-sheet.png) (turnaround, expressions, details, swatches). They are the authority. [hayate-moving.png](assets/mascot/hayate-moving.png) is a second view; [hayate-sheet-v0.png](assets/mascot/hayate-sheet-v0.png) is superseded and kept for history.
- **Canon block:** [canon.txt](assets/mascot/canon.txt) describes her in words, with the locked details. It goes at the top of every generation prompt.

## Rules

- **Only the character references go in as images.** The only image inputs to a generation are `hayate-base.png` and `hayate-sheet.png`. Never pass any other image: not a derived or earlier mascot image, not the chibi or another style (a different skeleton doesn't transpose cleanly), not a scene, layout or style reference. Everything else is described in words. Feeding generated images back in makes errors pile up, which is how the first mascot drifted. `scripts/mascot_gen.sh` takes no image arguments, so it enforces this.
- **Every image has a record.** `NAME.png` sits next to `NAME.prompt.txt`, with the references, the date, the tool and the full prompt.
- **Change the canon on purpose.** A new reference or a change to `canon.txt` is its own commit, with the reason in the message.
- **Backgrounds are simple, never busy.** She and the one prop that carries the joke are the subject. A background is a soft flat color or gentle gradient, with at most one or two large, simple shapes that support the story. No furnished rooms, no clutter, no crowds of floating objects, no detailed scenery. Plain white isn't required either; pick a calm color that suits the post.
- **Transparent only where she sits on the page.** The README and site header, the footer chibi and the expression stickers are cut out with `scripts/mascot_cutout.py`. Post illustrations keep their simple background.

## Checklist for a new image

Reject and regenerate if any of these fail:

- [ ] Cyan hair, messy, high ponytail with an orange hair tie
- [ ] Cyan-blue eyes, one pointed canine fang
- [ ] Cyan jacket with a white zipper, two white stripes per sleeve, sleeves pushed up to just below the elbow, white undershirt at the neckline
- [ ] Cyan pants with two white stripes per outer seam, cuffed ankles
- [ ] Orange scarf with fringed ends
- [ ] White sneakers with cyan panels and orange laces
- [ ] Slim, athletic proportions as in `hayate-base.png`
- [ ] No stray text, logos, watermarks, extra accessories or extra limbs and fingers
- [ ] Background is calm: flat color or gentle gradient, at most one or two simple shapes

## Making an image

```sh
scripts/mascot_gen.sh weekend-03 scene.txt /tmp/mascot/weekend-03
uvx --from "rembg[cpu]" --with pillow --with numpy python -I scripts/mascot_cutout.py \
  /tmp/mascot/weekend-03/weekend-03.png site/src/assets/weekend-03.png
cp /tmp/mascot/weekend-03/weekend-03.prompt.txt site/src/assets/
```

- `scene.txt` holds the pose, framing, props and size. The script adds the canon block and the references.
- The generator is Henrique's personal Codex CLI with OpenAI image generation. Art is MIT, like the rest of the repo ([README](../README.md#license)).
- The cut-out uses BiRefNet (MIT) through rembg (MIT). It un-mixes edge pixels from the white background and trims one pixel, so there is no light fringe on a dark page. Thin strands enclosed by hair can still keep a speck of white; check at 100% on a dark background.

## Library

Ready-to-use cut-outs in [site/src/assets/mascot/](../site/src/assets/mascot/):

| File | Use |
| --- | --- |
| `expr-smug.png` | Default reaction, a result went well |
| `expr-laugh.png` | Something absurd, a funny failure |
| `expr-provoke.png` | A challenge, "next weekend" teasers |
| `expr-surprised.png` | An unexpected number or bug |
| `hayate-running.png` | Speed, latency, progress |

Site images: `site/public/hayate-peek.png` (home hero), `hayate-og.png` (social card, solid background), `hayate-avatar.png` (favicon and nav icon), `hayate-chibi.png` (footer). The README header is `docs/assets/hayate-peek.png`: head and shoulders peeking over the edge.

## 2D rig

An idle animation of her (breathing, a slight head tilt, ponytail and scarf sway, random blinks) is on the site's About page, built as layered WebP with CSS ([decision 0009](decisions/0009-mascot-rig.md), [#39](https://github.com/HenriqueOkuti/hayate/issues/39)).

- **Layers:** [See-through](https://github.com/shitagaki-lab/see-through) split `hayate-base.png` into inpainted layers. Its weights are Apache-2.0 from the authors on top of CreativeML OpenRAIL++-M (SDXL and Animagine base), which claims no rights in the outputs. On the 4070 the NF4 script ran out of memory and its CPU-offload path crashed; `inference_psd_blockswap.py` fits (about 8 GB, 30 steps in about 5 minutes). The PSD is in [assets/mascot/rig/](assets/mascot/rig/).
- **Export:** `scripts/mascot_rig_export.py` turns the PSD into `site/public/rig/*.webp`. It drops `headwear` and `nose` (See-through got them wrong), splits the arms so the far one sits behind the jacket, and crops to a 404 x 1296 canvas with 16 px of headroom.
- **Animation:** `site/src/components/HayateRig.astro`. Each layer is a full-canvas image in stacking order. The outer div breathes (`translate`) and tilts with the head (`rotate` around the neck); the inner image sways around the hair tie or the scarf knot, or blinks (`scale` on the eye line). A few lines of JS trigger a blink every 2.5 to 6 seconds. `prefers-reduced-motion` shows the still composite.
- **Changing the pose** means new layers from a new reference image, not re-posing: the rig only moves and rotates parts, it doesn't bend them.
