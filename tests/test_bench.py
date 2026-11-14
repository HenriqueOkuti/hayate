from hayate.bench.micro import percentile, summarize, time_stages


def test_percentile_nearest_rank():
    v = list(range(1, 101))  # 1..100
    assert percentile(v, 50) == 50
    assert percentile(v, 99) == 99
    assert percentile(v, 100) == 100
    assert percentile([7], 99) == 7


def test_time_stages_chains_and_warms_up():
    seen = []
    stages = [("double", lambda xs: [2 * x for x in xs]), ("sum", lambda xs: seen.append(sum(xs)))]
    rows = time_stages(stages, [1, 2, 3], batch=2, calls=4, warmup=2)
    assert len(rows) == 4 and [r["call"] for r in rows] == [0, 1, 2, 3]
    assert len(seen) == 6  # warm-up calls run too, but are not kept
    assert all(r["ns_total"] >= r["ns_double"] + r["ns_sum"] for r in rows)
    s = summarize(rows, 2, ["double", "sum"])
    assert s["calls"] == 4
    assert s["us_per_page_total"]["p50"] == round(s["us_per_call_total"]["p50"] / 2, 2)
