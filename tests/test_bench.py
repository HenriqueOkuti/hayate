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


def test_reference_check_keeps_quiet_baseline(tmp_path):
    from hayate.bench import reference

    path = tmp_path / reference.FILE
    k = reference.key("python", "local", "0123456789abcdef0123")
    quiet = {"p50_us_per_page": 600.0, "p99_us_per_page": 1500.0}
    busy = {"p50_us_per_page": 720.0, "p99_us_per_page": 2000.0}
    r = reference.check(path, k, quiet, quiet, False, "t0", "c0", "first")
    assert r["status"] == "no-baseline" and r["baseline_updated"]
    r = reference.check(path, k, quiet, busy, False, "t1", "c1", "busy")
    assert r["status"] == "busy" and r["slowdown"] == 0.2 and not r["baseline_updated"]
    r = reference.check(path, k, quiet, {**quiet, "p50_us_per_page": 660.0}, False, "t2", "c2", "q")
    assert r["status"] == "quiet" and r["slowdown"] == 0.1 and r["baseline"]["source"] == "first"
    slower = {"p50_us_per_page": 800.0, "p99_us_per_page": 2000.0}  # 21% over the new 660
    r = reference.check(path, k, slower, slower, True, "t3", "c3", "accepted")
    assert r["status"] == "busy" and r["baseline"]["source"] == "q" and r["baseline_updated"]
    assert reference.judge(quiet, quiet, None) == (None, "no-baseline")
