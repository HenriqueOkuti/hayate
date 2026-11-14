"""Multi-label quality metrics for students: F1 per category and tier, calibration, thresholds.

Everything works on label-id sets per page, or on a score matrix (pages x labels, probabilities)
with a reference matrix of 0/1. Conventions (docs/measurement.md):
- Tier 2 is the ids as given (the teacher also uses Tier-1 ids on their own); Tier 1 rolls every
  id up to its Tier-1 ancestor; hierarchical P/R/F expands both sides with their ancestors first.
- Macro F1 averages over the labels with reference support in the scored set; labels with no
  support are listed with their predicted count but left out of the average.
- ECE uses equal-width bins over [0, 1] per category, weighted by bin size; the per-category
  values are averaged weighted by support. Brier is the mean squared error per category.
- Thresholds and the temperature are fitted on validation only. A label with fewer than
  `min_support` validation positives gets the global threshold, so a rare label cannot buy F1 by
  predicting itself everywhere.
"""

import random

import numpy as np

Sets = list[list[str]]


def to_matrix(sets: Sets, ids: list[str]) -> np.ndarray:
    col = {i: k for k, i in enumerate(ids)}
    m = np.zeros((len(sets), len(ids)), dtype=bool)
    for r, s in enumerate(sets):
        for i in s:
            m[r, col[i]] = True
    return m


def to_sets(m: np.ndarray, ids: list[str]) -> Sets:
    return [[ids[k] for k in np.flatnonzero(row)] for row in m]


def rollup(sets: Sets, tier1: dict[str, str]) -> Sets:
    return [sorted({tier1[i] for i in s}) for s in sets]


def expand(sets: Sets, tier1: dict[str, str]) -> Sets:
    """Each id plus its Tier-1 ancestor (the taxonomy here has two tiers)."""
    return [sorted(set(s) | {tier1[i] for i in s}) for s in sets]


def prf(tp: float, n_pred: float, n_ref: float) -> dict:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_ref if n_ref else 0.0
    f = 2 * tp / (n_pred + n_ref) if n_pred + n_ref else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4)}


def micro(ref: Sets, pred: Sets) -> dict:
    tp = sum(len(set(a) & set(b)) for a, b in zip(ref, pred, strict=True))
    return prf(tp, sum(len(set(b)) for b in pred), sum(len(set(a)) for a in ref))


def per_category(ref: Sets, pred: Sets, names: dict[str, str]) -> dict[str, dict]:
    stats: dict[str, list[int]] = {}
    for a, b in zip(ref, pred, strict=True):
        a, b = set(a), set(b)
        for i in a | b:
            s = stats.setdefault(i, [0, 0, 0])  # tp, predicted, support
            s[0] += i in a and i in b
            s[1] += i in b
            s[2] += i in a
    return {
        i: {"name": names.get(i, i), "support": s[2], "predicted": s[1], **prf(s[0], s[1], s[2])}
        for i, s in sorted(stats.items(), key=lambda kv: -kv[1][2])
    }


def micro_ci(ref: Sets, pred: Sets, boot: int = 1000, seed: int = 0) -> list[float]:
    """95% bootstrap interval of micro F1 over pages."""
    pairs = zip(ref, pred, strict=True)
    rows = [(len(set(a) & set(b)), len(set(b)), len(set(a))) for a, b in pairs]
    rng = random.Random(seed)
    draws = []
    for _ in range(boot):
        tp = n_pred = n_ref = 0
        for t, p, r in rng.choices(rows, k=len(rows)):
            tp, n_pred, n_ref = tp + t, n_pred + p, n_ref + r
        draws.append(2 * tp / (n_pred + n_ref) if n_pred + n_ref else 0.0)
    draws.sort()
    return [round(draws[int(0.025 * boot)], 4), round(draws[int(0.975 * boot) - 1], 4)]


def f1_report(ref: Sets, pred: Sets, tier1: dict[str, str], names: dict[str, str]) -> dict:
    """Micro (with interval), macro and per-category F1 at Tier 2 and Tier 1, plus hierarchical."""
    out = {"pages": len(ref)}
    for tier, (r, p) in {
        "tier2": (ref, pred),
        "tier1": (rollup(ref, tier1), rollup(pred, tier1)),
    }.items():
        cats = per_category(r, p, names)
        supported = [c["f1"] for c in cats.values() if c["support"]]
        exact = [set(x) == set(z) for x, z in zip(r, p, strict=True)]
        out[tier] = {
            "micro": micro(r, p) | {"f1_ci95": micro_ci(r, p)},
            "macro_f1": round(float(np.mean(supported)), 4) if supported else None,
            "labels_with_support": len(supported),
            "exact_match": round(float(np.mean(exact)), 4),
            "per_category": cats,
        }
    out["hierarchical"] = micro(expand(ref, tier1), expand(pred, tier1))
    return out


def _ece(y: np.ndarray, prob: np.ndarray, bins: int) -> float:
    """Expected calibration error of flat arrays: |mean prob - mean outcome| per bin, weighted."""
    if not len(prob):
        return 0.0
    idx = np.clip(np.digitize(prob, np.linspace(0, 1, bins + 1)[1:-1]), 0, bins - 1)
    total = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            total += abs(prob[m].mean() - y[m].mean()) * m.sum()
    return total / len(prob)


def calibration(
    y: np.ndarray, prob: np.ndarray, label_ids: list[str], bins: int = 10, min_support: int = 20,
    confident: float = 0.05,
) -> dict:  # fmt: skip
    """Calibration of probabilities `prob` against 0/1 targets `y` (pages x labels).

    Pooled over every cell, ECE is dominated by the many near-zero negatives, so this also
    reports ECE over the cells with p >= `confident`, top-1 calibration (the most probable label
    of each page against whether the reference has it), and per-category ECE and Brier for the
    labels with at least `min_support` positives. Bins are equal-width over [0, 1].
    """
    y = y.astype(float)
    flat_y, flat_p = y.ravel(), prob.ravel()
    conf = flat_p >= confident
    top = prob.argmax(1)
    top_p = prob[np.arange(len(prob)), top]
    top_hit = y[np.arange(len(y)), top]
    keep = np.flatnonzero(y.sum(0) >= min_support)
    return {
        "bins": f"{bins} equal-width over [0, 1]",
        "ece_all_cells": round(_ece(flat_y, flat_p, bins), 5),
        "brier_all_cells": round(float(((flat_p - flat_y) ** 2).mean()), 5),
        f"ece_cells_p_ge_{confident}": round(_ece(flat_y[conf], flat_p[conf], bins), 4),
        f"cells_p_ge_{confident}": int(conf.sum()),
        "top1_ece": round(_ece(top_hit, top_p, bins), 4),
        "top1_mean_prob": round(float(top_p.mean()), 4),
        "top1_hit_rate": round(float(top_hit.mean()), 4),
        "per_category": {
            label_ids[j]: {
                "support": int(y[:, j].sum()),
                "ece": round(_ece(y[:, j], prob[:, j], bins), 5),
                "brier": round(float(((prob[:, j] - y[:, j]) ** 2).mean()), 5),
            }
            for j in keep
        },
        "per_category_min_support": min_support,
    }


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(z, -50, 50)))


def fit_temperature(y: np.ndarray, logits: np.ndarray) -> float:
    """One temperature for all labels, minimizing mean binary cross-entropy (grid in log space)."""
    best, best_t = np.inf, 1.0
    for t in np.exp(np.linspace(np.log(0.05), np.log(20), 121)):
        p = np.clip(sigmoid(logits / t), 1e-7, 1 - 1e-7)
        loss = -(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()
        if loss < best:
            best, best_t = loss, float(t)
    return best_t


GRID = np.round(np.concatenate([np.arange(0.01, 0.05, 0.005), np.arange(0.05, 0.96, 0.025)]), 3)


def _middle_of_best(scores: np.ndarray) -> int:
    """Index of the middle grid point among those tied for the best score, so a flat stretch
    does not snap to its lowest threshold (which is close to "always positive")."""
    best = np.flatnonzero(scores >= scores.max() - 1e-12)
    return int(best[len(best) // 2])


def fit_thresholds(
    y: np.ndarray, prob: np.ndarray, min_support: int = 5, margin: float = 0.05
) -> tuple[np.ndarray, float]:
    """The global threshold maximizing micro F1 on validation, and per-label thresholds.

    A label keeps the global threshold unless it has at least `min_support` positives and some
    threshold beats its F1 at the global threshold by at least `margin`; ties pick the middle of
    the tied stretch. So a label with no signal cannot buy a sliver of F1 with a threshold low
    enough to predict it nearly everywhere.
    """
    y = y.astype(bool)

    def f1(pred: np.ndarray, axis=None) -> np.ndarray:
        tp = (pred & y).sum(axis)
        denom = pred.sum(axis) + y.sum(axis)
        return np.where(denom > 0, 2 * tp / np.maximum(denom, 1), 0)

    glob_k = _middle_of_best(np.array([float(f1(prob >= t)) for t in GRID]))
    glob = float(GRID[glob_k])
    per = np.full(y.shape[1], glob)
    scores = np.stack([f1(prob >= t, axis=0) for t in GRID])  # thresholds x labels
    for j in np.flatnonzero(y.sum(0) >= min_support):
        if scores[:, j].max() >= scores[glob_k, j] + margin:
            per[j] = GRID[_middle_of_best(scores[:, j])]
    return per, glob
