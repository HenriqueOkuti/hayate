# Tier-1 student v2: trained in Go (#90)

Run 2026-11-14. The head was trained by `go/train/cmd/tier1-train` on commit `aaa4098` (GoMLX, XLA CUDA backend on the RTX 4070 SUPER) and tuned and scored by `scripts/train_tier1.py --heads` on commit `1957ffd`, with everything else as in [tier1-v1](tier1-v1.md): the same features, label set, splits, learning-rate grid, early stopping, temperature, cross-fitted thresholds and top-label floor grid. The numbers are in [tier1-v2.json](tier1-v2.json) (the Go trainer's settings are under `model.go_heads_check`), the paired comparisons in [compare-tier1-v2-v1.json](compare-tier1-v2-v1.json) and [compare-tier1-v2-v1-eps7.json](compare-tier1-v2-v1-eps7.json), the control run in [tier1-v1-eps7.json](tier1-v1-eps7.json) and the CPU bundle checks in [tier1-v2-cpu.json](tier1-v2-cpu.json). No number here is accuracy; the references are the teacher and the panel.

Test was scored three times by runs that changed no choice: once before the code was committed, once after, and once after a change that only records more provenance. All three gave the same numbers to every printed digit, and nothing was chosen on test.

## Why v2 trains longer: the Adam epsilon

The PyTorch head of v1 stopped improving at epoch 3, where the GoMLX head kept going to epoch 10 at the same learning rate. Both use Adam with no weight decay, a zero-initialised weight matrix, a base-rate bias and batches of 256. One difference is the default epsilon in the denominator: 1e-8 in PyTorch, 1e-7 in GoMLX.

A likely mechanism, not measured: the loss is a mean over 256 x 317 cells, so the gradient of a weight for a rare feature and an absent label is tiny (an estimate puts it near 1e-9), and epsilon then sets the step size of much of the matrix. At 1e-8 those weights move fast and the head overfits early; at 1e-7 they move more slowly.

**Control run:** `train_tier1.py --adam-eps 1e-7` (run `tier1-v1-eps7`) is v1 with nothing changed but the epsilon, PyTorch throughout. It behaves like the Go head: at learning rate 0.01 it stops at epoch 11 (v1: 3), and val chose learning rate 0.03 (epoch 3). On test it reaches Tier-2 F1 0.493 and Tier-1 F1 0.608. So the epsilon accounts for the whole v1 to v2 gain; the framework does not add to it.

| Paired over the same pages, Tier-2 F1 | Val | Test |
| --- | --- | --- |
| v2 (Go) minus v1 (PyTorch, epsilon 1e-8) | +0.038 (0.029 to 0.048) | +0.039 (0.029 to 0.049) |
| v2 (Go) minus the control (PyTorch, epsilon 1e-7) | -0.005 (-0.013 to 0.002) | -0.012 (-0.019 to -0.005) |

The control is slightly better on test, by an interval that excludes zero, but val, where choices are made, cannot tell the two apart. Both are one seed. Why the PyTorch head is a little better at the same epsilon is not known (shuffle order and the learning rate val picked differ).

## Checks

- **Same inputs:** the IDF fitted in Go equals the one fitted in Python to 9e-16, and the Go trainer's label set equals the Python run's (317 labels).
- **Same heads:** for each of the three candidates, the val BCE that Python computes from the loaded Go weights equals the one the Go trainer recorded, to six digits, and the loaded learning rates are the `--lrs` grid.
- **CPU bundle** ([tier1-v2-cpu.json](tier1-v2-cpu.json), bundle hash `9d30c3af`): `scripts/export_tier1.py` gives the same labels as training time on 500 val pages (logits within 2e-6), and `go/cmd/tier1-parity` gives the same input, feature indices and labels on all 1,875 test pages (probabilities within 1.2e-7).

## Results

Val chose learning rate 0.01 (best epoch 10 of 13), own thresholds from 20 val positives, and a top-label floor of 0.02 (v1: 0.03). Cross-fitted val micro F1 at Tier 2: 0.486 (v1: 0.452). The 0.003 candidate was still improving at the 20-epoch limit inherited from v1; with the slower epsilon that limit binds at the low end of the grid, so the next run should raise it.

| Test, against the teacher | v1 | v2 | v2 minus v1, paired |
| --- | --- | --- | --- |
| Tier-2 micro F1 | 0.442 | 0.481 | +0.039 (0.029 to 0.049) |
| Tier-1 micro F1 | 0.554 | 0.598 | +0.045 (0.034 to 0.055) |
| Tier-2 precision / recall | 0.417 / 0.471 | 0.452 / 0.514 | |

- **Both languages gain:** Tier-2 F1 0.483 in English and 0.480 in Portuguese (v1: 0.440 and 0.444).
- **Panel** (without Sonnet's vote, 285 and 296 pages): Tier-2 F1 0.467 (0.422 to 0.510), Tier-1 F1 0.612 (0.567 to 0.654); v1 had 0.408 (0.363 to 0.452) and 0.556 (0.507 to 0.601). These are separate intervals, not a paired difference, and they overlap. The teacher scores 0.771 and 0.875 on the same pages.
- **Labels never predicted:** 136 labels that occur in test are never predicted (v1: 151).
- **The top-label rule** fires on about 646 test pages (v1: about 568), a third of them, adding one label to each. As in v1, the recall it gains (0.442 to 0.514) is paid for in precision (0.527 to 0.452), and the net Tier-2 effect is +0.001 (-0.009 to 0.011); v1's was +0.002 (-0.006 to 0.011).
- **"No topic":** v2 gives no label to 53 test pages, where the teacher gives none to 114; the overlap is still near zero (precision 0.04, recall 0.02).
- **Intervals** resample pages, not domains (1,875 test pages on 1,602 domains), so they are slightly too narrow.

## Latency

The model has the same shape as v1 (2^18 + 2^18 features, 317 labels, float32), so the Go latency in [bench-tier1-go.md](bench-tier1-go.md) applies; the benchmark reference (`results/bench-reference.json`) is keyed by bundle hash, so the first v2 benchmark run sets its own baseline. Training cost on the GPU, from the Go trainer's records: 28 s for the chosen candidate, 86 s for the grid of three, plus 4.3 s to featurize the train and val pages in Go.

## Verdict

v2 replaces v1 as the tier-1 student: about 4 points of Tier-2 F1 better against the teacher, with a paired interval well clear of zero, and trained in Go as decision 0012 asks. The gain comes from the Adam epsilon, as the PyTorch control shows. That control is a little better again on test, but val, which makes the choice, does not separate them, so the Go-trained head stays.
