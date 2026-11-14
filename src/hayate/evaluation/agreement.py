"""Set-based agreement between two label lists per page: micro P/R/F1, top label, Jaccard.

A pair is (predicted ids, reference ids), each ordered with the main label first. Tier-1 numbers
roll every label up to its Tier-1 ancestor first. Intervals are 95% bootstrap over pages. A page
where both sides are empty adds nothing to precision or recall, and counts as a match for the top
label, the exact match and Jaccard.
"""

import random
import statistics

Pair = tuple[list[str], list[str]]
BOOT = 2000


def rollup(ids: list[str], tier1: dict[str, str]) -> list[str]:
    """Tier-1 ancestors of `ids`, in order, without repeats."""
    out: list[str] = []
    for i in ids:
        if tier1[i] not in out:
            out.append(tier1[i])
    return out


def prf(pairs: list[Pair]) -> dict:
    tp = sum(len(set(p) & set(g)) for p, g in pairs)
    n_pred = sum(len(set(p)) for p, _ in pairs)
    n_ref = sum(len(set(g)) for _, g in pairs)
    precision = tp / n_pred if n_pred else 0.0
    recall = tp / n_ref if n_ref else 0.0
    f1 = 2 * tp / (n_pred + n_ref) if n_pred + n_ref else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def jaccard(p: list[str], g: list[str]) -> float:
    sp, sg = set(p), set(g)
    return 1.0 if not sp | sg else len(sp & sg) / len(sp | sg)


def _stats(pairs: list[Pair]) -> dict[str, float]:
    return prf(pairs) | {
        "top_match": statistics.fmean(p[:1] == g[:1] for p, g in pairs),
        "top_in_reference": statistics.fmean((p[0] in g) if p else not g for p, g in pairs),
        "exact_match": statistics.fmean(set(p) == set(g) for p, g in pairs),
        "jaccard": statistics.fmean(jaccard(p, g) for p, g in pairs),
    }


def _interval(values: list[float]) -> list[float]:
    values, n = sorted(values), len(values)
    return [round(values[int(0.025 * n)], 3), round(values[int(0.975 * n) - 1], 3)]


def _with_ci(pairs: list[Pair], boot: int, seed: int) -> dict:
    point = _stats(pairs)
    rng = random.Random(seed)
    draws = [_stats(rng.choices(pairs, k=len(pairs))) for _ in range(boot)]
    return {
        k: {"value": round(v, 3), "ci95": _interval([d[k] for d in draws])}
        for k, v in point.items()
    }


def summary(pairs: list[Pair], tier1: dict[str, str], boot: int = BOOT, seed: int = 0) -> dict:
    """Agreement at Tier 2 (the ids as given) and rolled up to Tier 1."""
    if not pairs:
        return {"pages": 0}
    rolled = [(rollup(p, tier1), rollup(g, tier1)) for p, g in pairs]
    return {
        "pages": len(pairs),
        "both_empty": sum(not p and not g for p, g in pairs),
        "tier2": _with_ci(pairs, boot, seed),
        "tier1": _with_ci(rolled, boot, seed),
    }


def _tiers(pairs: list[Pair], tier1: dict[str, str]) -> dict[str, list[Pair]]:
    return {"tier2": pairs, "tier1": [(rollup(p, tier1), rollup(g, tier1)) for p, g in pairs]}


def f1_diff(
    strata: list[tuple[list[Pair], list[Pair]]],
    tier1: dict[str, str],
    boot: int = BOOT,
    seed: int = 0,
) -> dict | None:
    """F1 of group a minus F1 of group b, two separate sets of pages (unpaired bootstrap).

    With several (a, b) strata, such as one per language, the result is the equal-weight mean of
    the per-stratum differences, resampled within each stratum, so a different mix of strata in
    a and b does not leak into the difference.
    """
    if not strata or any(not a or not b for a, b in strata):
        return None
    out = {"pages_a": sum(len(a) for a, _ in strata), "pages_b": sum(len(b) for _, b in strata)}
    for name in ("tier2", "tier1"):
        groups = [(_tiers(a, tier1)[name], _tiers(b, tier1)[name]) for a, b in strata]
        rng = random.Random(seed)

        def mean_diff(draw, groups=groups) -> float:
            return statistics.fmean(prf(draw(a))["f1"] - prf(draw(b))["f1"] for a, b in groups)

        draws = [mean_diff(lambda x, rng=rng: rng.choices(x, k=len(x))) for _ in range(boot)]
        out[name] = {"value": round(mean_diff(lambda x: x), 3), "ci95": _interval(draws)}
    return out


def f1_diff_paired(
    a: list[Pair], b: list[Pair], tier1: dict[str, str], boot: int = BOOT, seed: int = 0
) -> dict | None:
    """F1 of `a` minus F1 of `b` where a[i] and b[i] are the same page (pages resampled once)."""
    if not a or len(a) != len(b):
        return None
    out = {"pages": len(a)}
    for name in ("tier2", "tier1"):
        xa, xb = _tiers(a, tier1)[name], _tiers(b, tier1)[name]
        rng = random.Random(seed)
        draws = []
        for _ in range(boot):
            pick = rng.choices(range(len(xa)), k=len(xa))
            draws.append(prf([xa[i] for i in pick])["f1"] - prf([xb[i] for i in pick])["f1"])
        out[name] = {"value": round(prf(xa)["f1"] - prf(xb)["f1"], 3), "ci95": _interval(draws)}
    return out


def per_tier1(pairs: list[Pair], tier1: dict[str, str]) -> dict[str, dict]:
    """Per Tier-1 category: reference support, predictions and P/R/F1 on rolled-up labels."""
    rolled = [(set(rollup(p, tier1)), set(rollup(g, tier1))) for p, g in pairs]
    out = {}
    for cat in sorted({c for p, g in rolled for c in p | g}):
        one = [([cat] if cat in p else [], [cat] if cat in g else []) for p, g in rolled]
        out[cat] = {
            "support": sum(bool(g) for _, g in one),
            "predicted": sum(bool(p) for p, _ in one),
        } | {k: round(v, 3) for k, v in prf(one).items()}
    return out
