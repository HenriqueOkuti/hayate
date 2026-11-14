import numpy as np

from hayate.evaluation import metrics

TIER1 = {"1": "1", "2": "1", "3": "1", "9": "9", "10": "9"}
NAMES = {i: f"L{i}" for i in TIER1}


def test_f1_report_tiers_and_hierarchy():
    ref = [["2"], ["10"], [], ["2", "10"]]
    pred = [["3"], ["10"], ["9"], ["2"]]
    rep = metrics.f1_report(ref, pred, TIER1, NAMES)
    # tier 2: tp 2 (10 on page 2, 2 on page 4); predicted 4; reference 4
    assert rep["tier2"]["micro"]["f1"] == 0.5
    # tier 1: ref [1],[9],[],[1,9]; pred [1],[9],[9],[1] -> tp 3, pred 4, ref 4
    assert rep["tier1"]["micro"]["f1"] == 0.75
    # hierarchical: ref {2,1},{10,9},{},{2,10,1,9}; pred {3,1},{10,9},{9},{2,1} -> tp 1+2+0+2
    assert rep["hierarchical"]["f1"] == round(2 * 5 / (7 + 8), 4)
    cats = rep["tier2"]["per_category"]
    assert cats["3"]["support"] == 0 and cats["3"]["predicted"] == 1
    assert rep["tier2"]["labels_with_support"] == 2  # 3 and 9 have no support: not in macro
    assert rep["tier2"]["macro_f1"] == round((cats["2"]["f1"] + cats["10"]["f1"]) / 2, 4)


def test_calibration_perfect_and_off():
    y = np.array([[1], [0], [1], [0]], dtype=float)
    perfect = metrics.calibration(y, y.copy(), ["a"], min_support=1)
    assert perfect["ece_all_cells"] == 0 and perfect["brier_all_cells"] == 0
    half = metrics.calibration(y, np.full_like(y, 0.5), ["a"], min_support=1)
    assert half["ece_all_cells"] == 0 and half["brier_all_cells"] == 0.25  # right on average
    off = metrics.calibration(y, np.full_like(y, 0.9), ["a"], min_support=1)
    assert abs(off["ece_all_cells"] - 0.4) < 1e-9
    assert off["top1_hit_rate"] == 0.5 and off["per_category"]["a"]["support"] == 2


def test_temperature_and_thresholds():
    rng = np.random.default_rng(0)
    z = rng.normal(0, 3, size=(2000, 3))
    y = (rng.random((2000, 3)) < metrics.sigmoid(z / 3)).astype(float)
    assert 2.4 < metrics.fit_temperature(y, z * 1.0) < 3.6  # logits 3x too sharp
    y[:, 2] = 0
    y[:3, 2] = 1  # a rare label falls back to the global threshold
    thr, glob = metrics.fit_thresholds(y, metrics.sigmoid(z / 3), min_support=5)
    assert thr[2] == glob and 0.05 <= glob <= 0.95


def test_no_signal_label_keeps_global_threshold():
    rng = np.random.default_rng(1)
    prob = rng.random((1000, 2)) * 0.3
    y = np.zeros((1000, 2))
    y[:300, 0] = 1
    prob[:300, 0] += 0.6  # label 0 is learnable
    y[[5, 50, 500], 1] = 1  # label 1: three positives with low scores
    prob[[5, 50, 500], 1] = 0.02
    thr, glob = metrics.fit_thresholds(y, prob, min_support=2)
    assert thr[1] == glob  # not 0.01, which would predict it nearly everywhere
    assert 0.3 <= glob <= 0.6
