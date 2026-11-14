import pytest

from hayate.evaluation import agreement

TIER1 = {"1": "1", "2": "1", "3": "1", "9": "9"}  # 2 and 3 are children of 1


def test_prf_counts_label_overlap_across_pages():
    pairs = [(["2", "9"], ["2"]), (["3"], ["2"]), ([], [])]
    assert agreement.prf(pairs) == pytest.approx({"precision": 1 / 3, "recall": 0.5, "f1": 0.4})
    assert agreement.prf([([], [])]) == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_rollup_merges_siblings_in_order():
    assert agreement.rollup(["9", "2", "3"], TIER1) == ["9", "1"]


def test_summary_gives_tier1_credit_for_a_sibling():
    pairs = [(["3"], ["2"]), (["9"], ["9"]), ([], [])]
    out = agreement.summary(pairs, TIER1, boot=50)
    assert out["pages"] == 3 and out["both_empty"] == 1
    assert out["tier2"]["f1"]["value"] == 0.5 and out["tier1"]["f1"]["value"] == 1.0
    assert out["tier2"]["top_match"]["value"] == pytest.approx(0.667)
    assert out["tier2"]["exact_match"]["value"] == pytest.approx(0.667)
    lo, hi = out["tier2"]["f1"]["ci95"]
    assert 0 <= lo <= 0.5 <= hi <= 1
    assert agreement.summary([], TIER1) == {"pages": 0}


def test_top_in_reference_accepts_a_secondary_reference_label():
    out = agreement.summary([(["9"], ["2", "9"])], TIER1, boot=10)["tier2"]
    assert out["top_match"]["value"] == 0 and out["top_in_reference"]["value"] == 1


def test_f1_diff_is_group_a_minus_group_b():
    right, wrong = [(["2"], ["2"])] * 5, [(["2"], ["9"])] * 5
    diff = agreement.f1_diff([(right, wrong)], TIER1, boot=20)
    assert diff["tier2"] == {"value": 1.0, "ci95": [1.0, 1.0]}
    assert agreement.f1_diff([([], wrong)], TIER1) is None
    # two strata: +1 in one and -1 in the other average to 0, whatever their sizes
    mixed = agreement.f1_diff([(right, wrong), (wrong[:2], right)], TIER1, boot=20)
    assert mixed["tier2"]["value"] == 0.0 and mixed["pages_a"] == 7


def test_f1_diff_paired_resamples_the_same_pages():
    a = [(["2"], ["2"]), (["2"], ["2"])]
    b = [(["2"], ["2"]), (["3"], ["2"])]
    diff = agreement.f1_diff_paired(a, b, TIER1, boot=200)
    assert diff["tier2"]["value"] == 0.5 and diff["tier1"]["value"] == 0.0
    assert diff["tier2"]["ci95"][0] >= 0  # b is never better on any resample
    assert agreement.f1_diff_paired(a, b[:1], TIER1) is None


def test_per_tier1_reports_support_and_f1():
    out = agreement.per_tier1([(["3"], ["2"]), (["9"], ["2"])], TIER1)
    assert out["1"] == {"support": 2, "predicted": 1, "precision": 1.0, "recall": 0.5, "f1": 0.667}
    assert out["9"]["support"] == 0 and out["9"]["f1"] == 0.0
