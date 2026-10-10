# Research notes: which tool to build the mascot's 2D idle rig in

Project: Hayate (issue #38, housekeeping). Question: which tool should the mascot's small idle animation (breathing, blinking, scarf and ponytail sway, maybe expression swaps) be built in, for an Astro static site in a public MIT repo, by one non-animator on Linux (WSL2) with an RTX 4070.

Access date for all sources: **2026-10-10**. Method: official pricing, license, docs and repo pages, plus the public npm registry and unpkg file listings for package sizes. Every claim lists a source as [Sn]. Anything not confirmed on a primary source is tagged **UNVERIFIED** and collected again in the last section. Prices are as shown on 2026-10-10 in USD unless noted.

---

## 1. Candidates and licenses

### 1.1 Summary table

| Tool | Editor cost (2026-10-10) | Editor on Linux | Web runtime license | Can runtime and sources go in a public MIT repo | Maintenance signal |
| --- | --- | --- | --- | --- | --- |
| Rive | Free plan; Cadet $9/seat/mo; Voyager $32; Enterprise $120 [S1] | Browser editor only; desktop app is macOS and Windows [S3] | MIT [S2, S5] | Runtime yes (MIT). Source `.rev` is a proprietary binary from a closed, cloud-hosted editor [S6, S7] | npm `@rive-app/canvas-lite` 2.44.1 [S8] |
| Spine | Essential $69, Professional $379 (sale prices; list $99 and $449); Enterprise $2,499 + $379/user [S9] | Yes, 64-bit Linux [S9] | Spine Runtimes License, not open source [S10, S11] | Runtime may be redistributed with its license, but anyone who integrates or modifies it needs their own Spine Editor license [S10, S11] | Spine 4.3; `spine-player` 4.3.13 on npm [S12, S13] |
| Live2D Cubism | FREE edition with limits; PRO by subscription, price on the store only [S14, S15] | No; Windows and macOS only [S16] | Framework: Live2D Open Software License; Core: Live2D Proprietary Software License [S17] | Core redistribution only to end users inside a derivative work; a public repo looks restricted [S18] | Active (Cubism 5.x) [S16] |
| Inochi2D | Free, BSD-2-Clause [S19] | Yes (Linux zip in releases) [S20] | BSD-2-Clause (D library and Rust port Inox2D) [S21, S22] | Yes | Last tagged Creator release v0.8.6 on 2024-09-18 [S20]; core library commits as recent as 2026-10-03 [S23]; web support is WASM from nightly builds, Inox2D is "prototype" [S21, S22] |
| Godot (Skeleton2D, Polygon2D) | Free, MIT [S24] | Yes | MIT; ship the copyright notice [S24] | Yes; `.tscn` scenes are text | Docs at 4.7 stable [S25] |
| DragonBones | Editor not open source [S26]; status of the original editor UNVERIFIED | UNVERIFIED | MIT (DragonBonesJS) [S27] | Runtime yes | Last DragonBonesJS commits 2025-05-24 (adds a Pixi 8 runtime) [S28]; README points to "LoongBones" as successor [S27] |
| Layered PNG/SVG + CSS or WAAPI | Free | Any | None needed (browser) | Yes | Web standards |
| + Motion (motion.dev) | Free | Any | MIT, 14.1.0 [S29] | Yes | Active |
| + anime.js | Free | Any | MIT, 4.5.0 [S30] | Yes | Active |
| + GSAP | Free since 2025-04-30 [S31] | Any | "Standard No Charge" license from Webflow, not OSI [S31, S32] | Use is allowed; redistribution and MIT compatibility not addressed [S31] | 3.15.0 [S32] |

### 1.2 Rive

- Free plan includes the Rive Editor and CLI, 3 collaborative files, and "Export .riv files with a splash screen"; the page says "Free exports play a Rive splash screen" [S1]. Cadet ($9/seat/mo, up to 3 seats) is described as "Ship apps and games without the splash screen" [S1].
- Conflict: the October 2025 blog post said "exports now move to paid plans" [S4], and the export docs still say "Exporting for runtime is available on paid plans" [S6]. The pricing page on 2026-10-10 is the newest of the three and allows free exports with a splash screen [S1]. Exactly what the splash looks like and how long it plays is **UNVERIFIED**.
- The same blog post says "Runtimes remain open-source under MIT", that Rive files "don't phone home or depend on an active subscription", and "Your exports will keep working exactly as they do today, forever" [S4]. The `rive-wasm` repo is MIT [S5].
- Editor: desktop app for macOS and Windows; the browser editor at editor.rive.app is the Linux option [S3]. A forum feature request for a native Linux app exists [S33].
- Source files: `.rev` backup exports keep everything stripped from runtime `.riv` files and can be dragged back into the editor [S7]. A 2024-11-13 changelog says `.rev` export is available on all plans [S34]; the backup doc still says paid plans [S7]. Both `.riv` and `.rev` are binary (inferred from the docs describing them as exports of an editor format; byte format not documented on the pages read; **UNVERIFIED**).
- For a public MIT repo: committing the `.riv` and the MIT runtime is fine; but nobody can edit the rig without a Rive account, and the editor itself is closed.

### 1.3 Spine

- Essential lacks meshes and IK; Essential "can't save or export projects that use them" [S9]. Mesh deformation (needed for soft scarf and hair bend) therefore needs Professional, $379 on 2026-10-10 (list $449) [S9].
- Trial: all Professional features "except saving projects, texture packing, and exporting animation data, images and video" [S35], and the trial "does not grant rights to integrate, distribute, or otherwise make use of the Spine Runtimes" (Editor License 1.4.1) [S10].
- Runtimes: integration requires that the integrator holds a valid Spine Editor license; distribution must include the Spine Runtimes License (Exhibit A); third parties may not create derivative works containing the runtimes without their own license [S10, S11]. For an MIT repo this means the runtime files stay under Spine's license, not MIT, and forks that modify the rig or integration need a Spine license (interpretation of [S10, S11]; not legal advice).
- spine-ts packages: spine-core, spine-webgl, spine-canvas, spine-player, spine-webcomponents; "spine-ts Canvas does not support mesh attachments" except an experimental slow mode [S12].
- Export data is JSON text (git-friendly) or a binary format [S36]. The `.spine` project file format is not documented on the pages read (**UNVERIFIED** that it is binary).

### 1.4 Live2D Cubism

- FREE edition limits include 1 texture up to 2048 px, 100 ArtMeshes, 30 parts, 30 parameters, 3 blend shapes, 50 deformers, 9x9 warp divisions, and a 3-frame step for animation; above the limits the file cannot be saved [S14]. FREE is allowed for commercial use by general users and small businesses under 10 million JPY annual sales [S14].
- PRO price is not on the comparison page; 42-day PRO trial [S14, S16]. A current individual price was not found on a primary page (**UNVERIFIED**; a July 2026 sale covered annual and 3-year plans only, secondary source [S37]).
- Editor platforms: Windows and macOS (Apple Silicon and Intel); Linux not listed [S16]. Note: WSL2 runs on a Windows host, so Windows-only editors could run on the host side; that is outside the "Linux" requirement and is a trade-off, not a fact from the sources.
- SDK licensing: individuals and small-scale enterprises are exempt from the release license and payment, except "Expandable Applications" [S38]. Web Framework is under the Live2D Open Software License; Cubism Core under the Live2D Proprietary Software License [S17]. CubismWebFramework does not include Core; it must be downloaded separately from live2d.com [S39].
- Core redistribution: Section 5 allows redistribution only to make the derivative work available to end users; Section 1.14 counts placing software on an internet server as redistribution; Section 6.8 bars releasing any of the software under a non-Live2D license; Section 5.3.2 bars combining it with licenses that require source distribution [S18]. Committing Core into a public MIT repo looks restricted (interpretation of [S18]).

### 1.5 Inochi2D

- Open-source spec plus Inochi Creator (rigging) and Inochi Session (VTubing); rigs deform textures by parameters, similar in concept to Live2D [S40].
- Creator is BSD-2-Clause; last tagged release v0.8.6 (2024-09-18) with Linux, macOS and Windows builds [S19, S20].
- The core library has WASM support via a `wasm` config that needs a patched druntime toolchain (Linux only), with JavaScript wrappers in `dist/` and precompiled WASM in nightly builds; "starting with 0.9" main releases will include them [S21]. The planned 0.9 web portability was funded by an NLnet grant running 2024-02 to 2025-09 [S41]. No 0.9 release was found (**UNVERIFIED** whether 0.9 has shipped as of 2026-10-10).
- Inox2D (Rust port, BSD-2-Clause) has a WebGL demo but says it is "in a prototype state, it is not recommended to use this library in production" [S22].

### 1.6 Godot

- Engine is MIT; exported projects must include the copyright notice and license statement somewhere in the documentation or credits [S24].
- 2D rigging: Polygon2D pieces cut from one texture in the UV editor, a Skeleton2D with Bone2D hierarchy, weight painting per polygon, extra internal vertices for bending [S42].
- Web export (4.7 docs): WebAssembly + WebGL 2, Compatibility renderer only; single-threaded export is the default since 4.3 and avoids the COOP/COEP header requirement, which suits GitHub Pages [S25].
- Size: the docs give no absolute size, only that gzip shrinks the wasm to about a quarter [S25]. A third-party measurement reports a 42.0 MB default web export, down to 2.7 MB Brotli after custom templates and wasm-opt (secondary, [S43]).
- Transparent canvas over HTML: not documented; forum reports on 4.x and 4.6.2 say web builds stay opaque even when desktop builds are transparent (secondary, [S44]; **UNVERIFIED**).

### 1.7 DragonBones

- DragonBonesJS is MIT with runtimes for Egret, PixiJS, Phaser, Hilo and Cocos Creator; the README says "Highly suggest use LoongBones to create animation" and links loongbones.app [S27]. The LoongBones site returned only a title [S45]; a forum post says DragonBones was renamed LoongBones and is free (secondary, [S46]). LoongBones platforms, license and export formats are **UNVERIFIED**.
- A HaxeFlixel post says the DragonBones editor is not open source, only the runtime (secondary, [S26]).

### 1.8 Plain layers plus CSS or a small JS library

- GSAP: free including former Club plugins (SplitText, MorphSVG) since the Webflow license effective 2025-04-30, last modified 2025-05-30; prohibited use covers no-code visual animation tools that compete with Webflow; the license grants use, not redistribution or sublicensing [S31]. npm license field: "Standard 'no charge' license" [S32]. Not an OSI license, so it would be a non-MIT dependency.
- Motion (MIT, 14.1.0, 757 KB unpacked) [S29] and anime.js (MIT, 4.5.0, 2.1 MB unpacked) [S30] are MIT alternatives. CSS keyframes and the Web Animations API need no library at all.

## 2. Web playback

| Option | What ships to the browser | Embedding in Astro | Reduced-motion handling |
| --- | --- | --- | --- |
| Rive canvas-lite | `rive.wasm` 768 kB + `rive.js` 490 kB (uncompressed, v2.44.1) [S47], plus the `.riv` | npm import in a processed `<script>` that Astro bundles [S48]; `<canvas>` element | `autoplay` defaults to false; `play`, `pause`, `stop`, `stopRendering` [S49]; check `matchMedia` in JS [S50] |
| Rive canvas / webgl2 | `@rive-app/canvas` 5.6 MB unpacked [S51]; webgl2 uses the Rive Renderer, canvas uses Canvas2D; canvas-lite drops text, layout, audio and scripting [S52] | Same | Same |
| Spine player | `spine-player.min.js` 286 kB (iife, 4.3.13) [S53] plus atlas, PNG and JSON | Script or npm import; WebGL | JS (`matchMedia`) [S50]; player pause API not checked (**UNVERIFIED**) |
| Live2D | Cubism Core (separate download) + Web Framework + a WebGL renderer [S39] | Core cannot be bundled from npm; must be hosted per its license [S18] | JS |
| Inochi2D | WASM build from nightly; no stable web runtime [S21, S22] | Experimental | JS |
| Godot | Engine wasm (tens of MB before compression, secondary [S43]) + `.pck` | iframe sized to the game, or a custom HTML shell [S25] | JS around the iframe; opaque background likely (**UNVERIFIED**) |
| Layered PNG/WebP + CSS | Only the image layers; no runtime | Plain markup in an `.astro` component | `@media (prefers-reduced-motion: reduce)` in CSS, Baseline widely available since January 2020 [S50]; the static fallback is the same layers with animation off |

- Rive draws only on visual change by default (`DrawOnChanged`) [S49], and offers `stopRendering()` for an offscreen canvas [S49]. Pausing offscreen with an IntersectionObserver is a page-side choice for every canvas option.
- Astro processes `<script>` tags without attributes as bundled TypeScript modules, included once per page; `is:inline` or `public/` scripts skip processing [S48].

## 3. Art pipeline

### 3.1 What each tool needs

| Tool | Deformation model | Layers needed for this idle |
| --- | --- | --- |
| CSS / WAAPI | Rigid transforms (translate, rotate, scale, skew) and opacity only | Body/torso, head, eyes open, eyes closed (or lids), mouth variants, ponytail (one or a few segments), scarf tails (a few segments); each with a pivot point |
| Godot | Polygon2D meshes weighted to Bone2D bones [S42] | Same parts, packed into one texture [S42] |
| Spine | Bones; meshes and weights only in Professional [S9] | Same parts; meshes allow soft bending of scarf and hair |
| Rive | Bones plus meshes on raster images, with weights shown in the editor [S54] | Same parts |
| Live2D / Inochi2D | Mesh warp and rotation deformers driven by parameters [S14, S40] | Many more parts (front and back hair, eye white, iris, lids, brows, mouth parts) and fully inpainted hidden areas |

- Hidden areas: any part that moves exposes what is behind it (neck under the head, torso under the scarf, the back of the ponytail), so each lower layer needs its covered area painted in. This is true for every option; the parameter-driven tools need it the most.

### 3.2 Cutting and inpainting layers from a flat image

| Tool | What it does | License | Hardware note |
| --- | --- | --- | --- |
| See-through (SIGGRAPH 2026) | Single anime image to a layered PSD of up to 23 semantic, inpainted body-part layers with inferred draw order; also depth maps and masks [S55, S56] | Code Apache-2.0; weights license not stated on the repo page (**UNVERIFIED**) [S55] | About 12 to 16 GB VRAM bf16 at 1280 px; about 10 GB with group offload; about 8 GB NF4 [S55]. The RTX 4070 has 12 GB (**UNVERIFIED**, not checked on a primary page) |
| Qwen-Image-Layered | Decomposes an image into 3 to 8 (or recursive) RGBA layers; 20B parameters, BF16; recommended resolution 640 [S57] | Apache 2.0 [S57] | VRAM not stated [S57]; a 20B BF16 model is larger than 12 GB (inference from parameter count) |
| SAM 2.1 | Click or box prompted segmentation masks; local web demo [S58] | Apache 2.0 [S58] | CUDA toolkit; Windows users told to use WSL [S58] |
| Krita AI Diffusion | Selection-driven generative fill, inpainting and object removal inside Krita; segmentation via the separate krita-ai-tools plugin [S59] | GPL-3.0 [S59] | Linux supported; at least 6 GB NVIDIA VRAM recommended [S59] |
| IOPaint | LaMa erase plus diffusion inpainting, SAM and anime segmentation plugins [S60] | Apache-2.0 [S60] | Archived 2025-08-13, read-only [S60] |
| GIMP / Krita (manual) | Hand masking and painting | GPL | None |

- A third system, Bunraku (arXiv 2607.27348), reportedly outputs layers, per-layer meshes and Live2D keypose offsets from one illustration; code availability is **UNVERIFIED** (secondary, [S61]).
- License note: the README states the mascot art is MIT and generated with OpenAI image generation [S62]; derived layers would follow the same repo license, and the README already covers mascot art.

### 3.3 Git-friendliness of source files

| Tool | Source file | Text or binary |
| --- | --- | --- |
| CSS / SVG | `.astro`, `.css`, `.svg` | Text; layer PNG or WebP images are binary |
| Godot | `.tscn` scenes | Text (format not re-checked on a primary page this session; **UNVERIFIED**) |
| Spine | `.spine` project; export JSON or binary [S36] | Export JSON is text [S36]; project format **UNVERIFIED** |
| Rive | `.rev` backup and `.riv` runtime [S7] | Binary (**UNVERIFIED**) |
| Live2D | `.cmo3` model, `.can3` animation | **UNVERIFIED** (not checked) |
| Inochi2D | `.inx` / INP | INP 2 is a binary format from 0.9 (secondary, [S63]) |

- The repo rule that data and model artifacts are not committed does not cover art; the README ships mascot PNGs [S62]. Large binary layers would bloat history; Git LFS is an option (not researched here).

## 4. Assessment for this case

This section lays out trade-offs for the decision record; the decision itself belongs in `docs/decisions/`.

### 4.1 Best free path

- **Layered raster (WebP or PNG) plus CSS keyframes, with a few lines of JS only for random blink timing.** Zero runtime bytes, fully MIT, every source file is text except the images, works on GitHub Pages, and `prefers-reduced-motion` is one media query [S50]. The static fallback is the same composite with animation off. Limit: rigid transforms only, so scarf and ponytail sway is done by rotating a few segments around pivots rather than bending a mesh. If an animation library is wanted, Motion or anime.js are MIT [S29, S30]; GSAP is free but not OSI-licensed [S31].
- **Layer cutting:** See-through can produce the layered, inpainted PSD in one pass and fits a 12 GB GPU with offload [S55]; SAM 2.1 masks plus Krita AI Diffusion inpainting is the hand-controlled fallback [S58, S59]. Expect manual cleanup either way (secondary review, [S64]).
- **Free path with mesh bending:** Godot (MIT, Linux editor, text scenes) gives bones and weighted meshes [S24, S42], but the web payload is tens of MB before compression (secondary, [S43]) and a transparent background over the page is reported not to work (secondary, [S44]). Inochi2D is fully open but has no stable web runtime [S21, S22].
- **Rive Free** has the best authoring-to-web fit (browser editor on Linux, raster meshes and bones, MIT runtime about 1.26 MB uncompressed for canvas-lite) [S3, S47, S54], but free exports play a Rive splash screen [S1] and the editor is closed and account-based, so the rig cannot be edited by anyone without a Rive account.

### 4.2 What a paid path adds

| Paid option | Cost on 2026-10-10 | Adds |
| --- | --- | --- |
| Rive Cadet | $9/seat/mo, $9/mo billed annually per the 2025 post [S1, S4] | Removes the splash screen; exports keep working after cancelling [S4] |
| Spine Professional | $379 one-time (sale; list $449) [S9] | Meshes, weights, IK on a native Linux editor [S9]; JSON export [S36]; but a non-MIT runtime license that binds forks [S10, S11] |
| Live2D Cubism PRO | Store price, not confirmed [S14] | Lifts FREE limits; the Live2D look (parameter-driven head turns) [S14]; no Linux editor [S16] and a restrictive Core license for a public repo [S18] |

---

## Sources (all accessed 2026-10-10)

- S1 https://rive.app/pricing
- S2 https://rive.app/docs/runtimes/getting-started
- S3 https://rive.app/docs/editor/get-rive
- S4 https://rive.app/blog/rive-s-new-9-mo-plan
- S5 https://github.com/rive-app/rive-wasm
- S6 https://rive.app/docs/editor/exporting/exporting-for-runtime
- S7 https://rive.app/docs/editor/exporting/exporting-for-backup
- S8 https://registry.npmjs.org/@rive-app/canvas-lite/latest
- S9 https://esotericsoftware.com/spine-purchase
- S10 https://esotericsoftware.com/spine-editor-license
- S11 https://esotericsoftware.com/spine-runtimes-license
- S12 https://github.com/EsotericSoftware/spine-runtimes/tree/4.2/spine-ts
- S13 https://registry.npmjs.org/@esotericsoftware/spine-player/latest
- S14 https://www.live2d.com/en/cubism/comparison/
- S15 https://help.live2d.com/en/?p=1908
- S16 https://www.live2d.com/en/cubism/download/editor/
- S17 https://raw.githubusercontent.com/Live2D/CubismWebFramework/develop/LICENSE.md
- S18 https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html
- S19 https://github.com/Inochi2D/inochi-creator
- S20 https://api.github.com/repos/Inochi2D/inochi-creator/releases?per_page=5
- S21 https://github.com/Inochi2D/inochi2d
- S22 https://github.com/inochi2d/inox2d
- S23 https://api.github.com/repos/Inochi2D/inochi2d/commits?per_page=3
- S24 https://godotengine.org/license/
- S25 https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html
- S26 https://haxeflixel.com/blog/13-HaxeFlixel-DragonBones-Support/ (secondary)
- S27 https://github.com/DragonBones/DragonBonesJS
- S28 https://api.github.com/repos/DragonBones/DragonBonesJS/commits?per_page=2
- S29 https://registry.npmjs.org/motion/latest
- S30 https://registry.npmjs.org/animejs/latest
- S31 https://gsap.com/licensing/
- S32 https://registry.npmjs.org/gsap/latest
- S33 https://rive.app/community/forums/feature-requests/fsyCzA4A9Yar/linux-desktop-app-for-rive-editor/ftUmuvMQ5dW8
- S34 https://rive.app/changelog/backup-exports-available-for-all-users
- S35 https://esotericsoftware.com/spine-download
- S36 https://esotericsoftware.com/spine-json-format
- S37 https://koubo.jp/article/99033 (secondary)
- S38 https://www.live2d.com/en/sdk/license/
- S39 https://github.com/Live2D/CubismWebFramework
- S40 https://docs.inochi2d.com/
- S41 https://nlnet.nl/project/Inochi2D/
- S42 https://docs.godotengine.org/en/stable/tutorials/animation/2d_skeletons.html
- S43 https://popcar.bearblog.dev/how-to-minify-godots-build-size/ (secondary)
- S44 https://forum.godotengine.org/t/enable-see-through-background-on-web-export-desktop-works/139052 (secondary)
- S45 https://loongbones.app
- S46 https://forum.defold.com/t/hope-defold-can-continue-to-support-the-new-loongbones/81757 (secondary)
- S47 https://app.unpkg.com/@rive-app/canvas-lite@2.44.1
- S48 https://docs.astro.build/en/guides/client-side-scripts/
- S49 https://rive.app/docs/runtimes/web/rive-parameters
- S50 https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion
- S51 https://registry.npmjs.org/@rive-app/canvas/latest
- S52 https://rive.app/docs/runtimes/web/canvas-vs-webgl
- S53 https://app.unpkg.com/@esotericsoftware/spine-player@4.3.13/files/dist/iife
- S54 https://rive.app/docs/editor/manipulating-shapes/meshes
- S55 https://github.com/shitagaki-lab/see-through
- S56 https://arxiv.org/abs/2602.03749
- S57 https://huggingface.co/Qwen/Qwen-Image-Layered
- S58 https://github.com/facebookresearch/sam2
- S59 https://github.com/Acly/krita-ai-diffusion
- S60 https://github.com/Sanster/IOPaint
- S61 https://papers.cool/arxiv/2607.27348 (secondary)
- S62 /home/henri/Projects/categorizer/README.md (repo file, License section)
- S63 https://docsearch.algolia.com/mcp/docs/repo/inochi2d/inochi2d (secondary, search snippet)
- S64 https://lilting.ch/en/articles/see-through-anime-layer-decomposition (secondary)

## UNVERIFIED / uncertain

1. Rive free exports: the pricing page allows them with a splash screen [S1], but the export docs [S6] and the October 2025 blog [S4] say exports are paid-only. The pricing page is the newest; the splash's look and duration were not checked.
2. Rive `.rev` export on the free plan: the 2024-11-13 changelog says all plans [S34], the backup doc says paid plans [S7].
3. Rive `.riv` and `.rev` being binary, and Spine `.spine`, Live2D `.cmo3` and `.can3` formats: not confirmed on a primary page.
4. Spine player pause or reduced-motion API: not checked.
5. Live2D Cubism PRO current price for individuals: not on any primary page reached; the Live2D Store was not fetched.
6. Whether Live2D's RedistributableFiles.txt lists the web Core file, and whether hosting it on GitHub Pages (not in the repo) is allowed: the license text suggests redistribution only to end users inside a derivative work [S18].
7. Inochi2D 0.9: no release found; the web runtime state as of 2026-10-10 is based on README text [S21, S22].
8. LoongBones (DragonBones successor): platforms, license, price and export formats not confirmed.
9. Godot web build size (secondary measurement only) and transparent canvas on web (forum reports only).
10. See-through model weights license: not stated on the repo page.
11. RTX 4070 VRAM (12 GB) not checked on a primary page; Qwen-Image-Layered VRAM needs not stated.
12. Godot `.tscn` being text: well known but not re-checked this session.
13. Whether the GSAP license allows committing GSAP files into an MIT repo: the license page does not address redistribution [S31].
