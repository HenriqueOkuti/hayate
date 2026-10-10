# 0009: Mascot rig tool

- **Status:** accepted
- **Date:** 2026-10-10

## Context

The redesigned mascot ([mascot.md](../mascot.md), [#36](https://github.com/HenriqueOkuti/hayate/issues/36)) gets a small idle animation on the Astro site: breathing, blinking, scarf and ponytail sway, maybe expression swaps, with a static fallback and `prefers-reduced-motion` respected ([#39](https://github.com/HenriqueOkuti/hayate/issues/39)). Constraints: a public MIT repo whose source files should be committable and redistributable, one developer on Linux (WSL2) who is not an animator, a static site with no build-time runtime to maintain, and free unless a budget is set. The source art is flat generated PNGs on white with no layers. Facts are from [research/2026-10-10-mascot-rig-tool.md](../research/2026-10-10-mascot-rig-tool.md).

## Options considered

1. **Layered raster + CSS keyframes, a few lines of JS for random blinks.** No runtime bytes, everything MIT and in git, reduced motion is one media query and the fallback is the same composite with animation off. Motion is rigid only: scarf and ponytail swing as rotating segments instead of bending.
2. **Rive.** Best authoring-to-web fit (browser editor works on Linux, meshes and bones, MIT runtime about 1.26 MB uncompressed). Free exports play a Rive splash screen; removing it is $9/seat/mo. The editor is closed and account-based, so nobody can edit the rig without a Rive account, and the docs disagree on whether free export works at all.
3. **Spine Professional.** Proper meshes, weights and IK on a native Linux editor, for $379 one-time. Its runtime license requires every integrator to hold a Spine license and binds forks, which doesn't fit an MIT repo.
4. **Open mesh tools: Godot or Inochi2D.** Free and open with bones and weighted meshes, but Godot's web export is tens of MB and reportedly can't show a transparent background over the page, and Inochi2D has no stable web runtime. Live2D (no Linux editor, restrictive Core license) and DragonBones (unmaintained since 2025-05) were ruled out.

## Decision

Option 1. The animation is small enough that rigid segments look fine at blog size, and it keeps the whole thing free, MIT and editable by anyone with a text editor and an image editor. Layers are WebP cut from `hayate-base.png`; an animation library is optional and, if used, must be MIT (Motion or anime.js, not GSAP, whose license is not open source).

Layer cutting starts with See-through (code Apache-2.0, fits the 4070 with offloading) if its model weights carry a license that allows committing the outputs; otherwise SAM 2.1 masks plus Krita AI Diffusion inpainting, with manual cleanup either way.

## Consequences

- No new runtime dependency on the site, and the rig source is plain files in `site/` plus layer images.
- Bending cloth and hair can't be done; the sway is rotation around pivots, so it reads as stylized.
- The layers are cut from one pose, so new poses mean new layers, not re-posing a rig.
- Revisit if the rigid sway looks bad in practice, or if a later need (several poses, a talking mascot) justifies mesh deformation. Rive Cadet would be the first paid option to weigh, and it needs a budget here first.
