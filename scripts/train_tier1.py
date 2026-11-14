"""Train the tier-1 student (hashed n-grams + linear) on a label run and score it.

Usage:
  uv run python scripts/train_tier1.py --name tier1-v0 --labels-run bulk-v2 --splits splits-v1

Trains on the `--split-column` train pages (split by component, or split_by_page for the
comparison) with the teacher's main-pass labels as targets. Everything tuned is tuned on that
column's val pages: the learning rate (--lrs, picked by val micro F1 at Tier 2), the
epoch (lowest val loss), one temperature and per-label thresholds (hayate.evaluation.metrics).
Test is scored once, after.
A page's predicted labels are those at or above their threshold, most probable first, at most
--max-labels; none means "no topic", like the teacher's empty answer. With --top1-floors, a
page where no label passes keeps its most probable label if that probability is at least the
floor; the floor (or "off", -1) is chosen with the threshold policy by cross-fitted val F1, and
test is also scored with the rule off on the same model (`test_rule_off`, `top1_rule_minus_off`,
paired over the same pages; the val pairing is in-sample).

Writes results/<name>.json (counts and scores only, no page text), and to artifacts/<name>/
(never committed) the model (featurizer.joblib, head.pt) and predictions.jsonl (label ids per
val and test page, for paired comparisons in scripts/compare_students.py). Scores:
- val_in_sample: val scored with thresholds fitted on val, so optimistic; selection uses the
  cross-fitted val F1 instead (thresholds fitted on one half of val, scored on the other, halves
  split by component so one site's pages stay on one side);
- test: against the teacher on the column's test pages, overall, per language and for "no
  topic" as a pseudo-label, plus calibration before and after the temperature;
- test_leak: test pages with a page of the same component in this column's train against those
  without. Empty for the component split; for the by-page split it is the leakage measure
  (decision 0011), with an unpaired, language-stratified difference;
- panel: against the panel reference on the 300 holdout pages, rebuilt from its votes without
  --panel-leave-out (the teacher's own model, which the student imitates), scored like
  scripts/panel_report.py scores the teachers; the teacher run on the same pages is the ceiling.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import duckdb
import joblib
import numpy as np
import scipy.sparse as sp
import torch

from hayate import provenance
from hayate.evaluation import agreement, metrics, panel
from hayate.students.hashed import (
    Featurizer,
    HeadConfig,
    LinearHead,
    device,
    logits,
    page_input,
    train_head,
)
from hayate.teacher import claude


def metrics_half(key: str, seed: int = 0) -> bool:
    return hashlib.sha256(f"{seed}:half:{key}".encode()).digest()[0] % 2 == 0


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment() -> dict:
    import platform

    import sklearn

    cpu = next(
        (ln.split(":", 1)[1].strip() for ln in Path("/proc/cpuinfo").read_text().splitlines()
         if ln.startswith("model name")), platform.processor(),
    )  # fmt: skip
    return {
        "cpu": cpu,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "sklearn": sklearn.__version__,
        "numpy": np.__version__,
    }


def read_main(path: Path) -> dict[str, list[dict]]:
    out = {}
    with path.open() as f:
        for line in f:
            r = json.loads(line)
            if r["pass"] == "main":
                out[r["page_id"]] = r["labels"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", required=True)
    ap.add_argument("--labels-run", required=True)
    ap.add_argument("--splits", required=True)
    ap.add_argument("--split-column", choices=["split", "split_by_page"], default="split")
    ap.add_argument("--text-field", default="text_trafilatura")
    ap.add_argument("--fallback-field", default="text_resiliparse")
    ap.add_argument("--min-chars", type=int, default=200, help="use the fallback below this")
    ap.add_argument("--max-chars", type=int, default=3000)
    ap.add_argument("--lrs", type=float, nargs="+", default=[3e-3, 1e-2, 3e-2])
    ap.add_argument("--weight-decay", type=float, default=0.0)
    ap.add_argument("--max-epochs", type=int, default=20)
    ap.add_argument("--word-bits", type=int, default=18)
    ap.add_argument("--char-bits", type=int, default=18)
    ap.add_argument("--max-labels", type=int, default=5)
    ap.add_argument(
        "--top1-floors", type=float, nargs="+", default=[-1.0],
        help="candidate floors for keeping the top label when none passes (-1: rule off)",
    )  # fmt: skip
    ap.add_argument(
        "--min-supports", type=int, nargs="+", default=[5, 20, 50, 10**9],
        help="candidate val positives for a label's own threshold (10**9: global only)",
    )  # fmt: skip
    ap.add_argument("--reference", type=Path, default=Path("data/labels/panel-v0/reference.jsonl"))
    ap.add_argument("--panel-leave-out", default="holdout-v2", help="the teacher model's vote")
    ap.add_argument("--min-votes", type=int, default=2)
    ap.add_argument("--pages", type=Path, default=Path("data/pages/pages.parquet"))
    ap.add_argument("--labels-json", type=Path, default=Path("data/taxonomy/labels.json"))
    ap.add_argument("--labels-dir", type=Path, default=Path("data/labels"))
    ap.add_argument("--splits-dir", type=Path, default=Path("data/splits"))
    args = ap.parse_args()

    labels_json = json.loads(args.labels_json.read_text())
    tier1 = {lab.id: lab.parent or lab.id for lab in claude.load_labels(labels_json)}
    names = {lab["id"]: lab["name"] for lab in labels_json["labels"]}
    teacher = read_main(args.labels_dir / args.labels_run / "labels.jsonl")
    inp = {"text_field": args.text_field, "fallback_field": args.fallback_field,
           "min_chars": args.min_chars}  # fmt: skip
    splits_path = args.splits_dir / f"{args.splits}.parquet"
    rows = duckdb.sql(
        f"""select p.page_id, p.lang, s.split, s.split_by_page, p.url,
                   coalesce(p.title, ''), coalesce(p.meta_description, ''), {claude.text_sql(inp)},
                   s.component
            from '{args.pages}' p join '{splits_path}' s using (page_id) order by p.page_id"""
    ).fetchall()
    if {r[0] for r in rows} != teacher.keys():
        raise SystemExit("the label run does not cover exactly the split's pages")
    col = 2 if args.split_column == "split" else 3
    docs = {r[0]: page_input(r[4], r[5], r[6], r[7], args.max_chars) for r in rows}
    lang = {r[0]: r[1] for r in rows}
    part = {s: [r[0] for r in rows if r[col] == s] for s in ("train", "val", "test")}
    component = {r[0]: r[8] for r in rows}

    def ids(labels: list[dict]) -> list[str]:
        return [x["id"] for x in labels]

    train_sets = [ids(teacher[p]) for p in part["train"]]
    label_ids = sorted({i for s in train_sets for i in s})  # labels never seen can't be learned
    y_train = metrics.to_matrix(train_sets, label_ids)

    def ref_sets(pages: list[str]) -> list[list[str]]:
        return [[i for i in ids(teacher[p]) if i in label_ids] for p in pages]

    def decide(prob: np.ndarray, thr: np.ndarray, floor: float | None = None) -> list[list[str]]:
        """Labels at or above their threshold, most probable first. With a `floor`, a page where
        none passes keeps its most probable label if that label's probability is >= floor."""
        out = []
        for row in prob:
            keep = np.flatnonzero(row >= thr)
            keep = keep[np.argsort(-row[keep])][: args.max_labels]
            if not len(keep) and floor is not None and row.max() >= floor:
                keep = [int(row.argmax())]
            out.append([label_ids[k] for k in keep])
        return out

    full_ref = {p: ids(teacher[p]) for p in teacher}  # with labels unseen in train, for scoring

    t0 = time.time()
    feat = Featurizer(args.word_bits, args.char_bits)
    order = [r[0] for r in rows]
    pos = {p: k for k, p in enumerate(order)}
    hashed = feat.hash([docs[p] for p in order])
    feat.fit(hashed[[pos[p] for p in part["train"]]])  # TF-IDF weights from train pages only
    x_all = feat.weigh(hashed)
    del hashed
    feat_s = time.time() - t0
    print(f"features: {x_all.shape[1]} hashed, {x_all.nnz} nonzeros, {feat_s:.0f}s")

    def rows_x(pages: list[str]) -> sp.csr_matrix:
        return x_all[[pos[p] for p in pages]]

    x_train = rows_x(part["train"])
    x_val = rows_x(part["val"])
    y_val = metrics.to_matrix(ref_sets(part["val"]), label_ids)

    val_ref = [full_ref[p] for p in part["val"]]
    # seeded val halves by component, so pages of one site never sit on both sides
    half = np.array([metrics_half(component[p]) for p in part["val"]])

    floors = [None if f < 0 else f for f in args.top1_floors]

    def cross_f1(prob: np.ndarray, min_support: int) -> dict:
        """Thresholds fitted on one val half and scored on the other, both ways, pooled, for each
        top-1 floor. An honest estimate of what the rule gives on unseen pages."""
        preds = {f: [None] * len(val_ref) for f in floors}
        for fit_on in (half, ~half):
            thr, _ = metrics.fit_thresholds(y_val[fit_on], prob[fit_on], max(min_support // 2, 1))
            idx = np.flatnonzero(~fit_on)
            for f in floors:
                for k, row in zip(idx, decide(prob[~fit_on], thr, f), strict=True):
                    preds[f][k] = row
        return {f: metrics.micro(val_ref, preds[f])["f1"] for f in floors}

    def tune(head: LinearHead) -> dict:
        """Temperature on val; the min support for a label's own threshold by cross-fitted val F1;
        then thresholds on all of val with that min support."""
        z_val = logits(head, x_val)
        temp = metrics.fit_temperature(y_val, z_val)
        prob = metrics.sigmoid(z_val / temp)
        grid = {(ms, f): v for ms in args.min_supports for f, v in cross_f1(prob, ms).items()}
        # ties go to the larger min support and to no floor (off first, then higher floors)
        (ms, floor) = max(
            grid, key=lambda k: (grid[k], k[0], k[1] is None, k[1] if k[1] is not None else 0)
        )
        thr, glob = metrics.fit_thresholds(y_val, prob, ms)
        in_sample = metrics.micro(val_ref, decide(prob, thr, floor))["f1"]
        cross = {f"{m}|{'off' if f is None else f}": v for (m, f), v in grid.items()}
        return {"temp": temp, "thr": thr, "glob": glob, "min_support": ms, "floor": floor,
                "cross": cross, "val_f1_cross": grid[(ms, floor)],
                "val_f1_cross_rule_off": grid[(ms, None)] if None in floors else None,
                "val_f1_in_sample": in_sample}  # fmt: skip

    candidates, best = [], None
    for lr in args.lrs:
        cfg = HeadConfig(lr=lr, weight_decay=args.weight_decay, max_epochs=args.max_epochs)
        t0 = time.time()
        head, hist = train_head(x_train, y_train, x_val, y_val, cfg)
        fit_s = time.time() - t0
        t = tune(head)
        print(f"lr {lr:g}: val micro F1 cross-fitted {t['val_f1_cross']:.4f} "
              f"(in-sample {t['val_f1_in_sample']:.4f}), min support {t['min_support']}, "
              f"T {t['temp']:.2f}, epoch {hist['best_epoch']}, fit {fit_s:.0f}s")  # fmt: skip
        candidates.append(
            {"lr": lr, **{k: v for k, v in t.items() if k not in ("thr", "temp", "glob")},
             "cross": {str(k): v for k, v in t["cross"].items()}, **hist, "fit_s": round(fit_s, 1)}
        )  # fmt: skip
        if best is None or t["val_f1_cross"] > best[0]["val_f1_cross"]:
            best = (t, lr, head, fit_s, hist)
    t, lr, head, fit_s, hist = best
    temp, thr, glob, floor = t["temp"], t["thr"], t["glob"], t["floor"]

    def predict(pages: list[str]) -> tuple[np.ndarray, np.ndarray, list[list[str]]]:
        z = logits(head, rows_x(pages))
        prob = metrics.sigmoid(z / temp)
        return z, prob, decide(prob, thr, floor)

    def score(pages: list[str], pred: list[list[str]]) -> dict:
        return metrics.f1_report([full_ref[p] for p in pages], pred, tier1, names)

    def compact(rep: dict) -> dict:
        """The report without per-category rows (kept only for the main test score)."""
        return {k: ({kk: vv for kk, vv in v.items() if kk != "per_category"}
                    if isinstance(v, dict) else v) for k, v in rep.items()}  # fmt: skip

    _, prob_v, pred_v = predict(part["val"])
    z_t, prob_t, pred_t = predict(part["test"])
    pred_of = dict(zip(part["test"], pred_t, strict=True))
    y_test = metrics.to_matrix(ref_sets(part["test"]), label_ids)
    test = score(part["test"], pred_t)
    pred_t_off = decide(prob_t, thr, None)  # the same model with the v0 rule, for a clean pairing
    pred_v_off = decide(prob_v, thr, None)
    rule_effect = {
        split: agreement.f1_diff_paired(
            [(a, full_ref[p]) for a, p in zip(on, pages, strict=True)],
            [(b, full_ref[p]) for b, p in zip(off, pages, strict=True)],
            tier1,
        )
        for split, pages, on, off in (
            ("val", part["val"], pred_v, pred_v_off),
            ("test", part["test"], pred_t, pred_t_off),
        )
    }
    by_lang = {
        lg: compact(score(ps, [pred_of[p] for p in ps]))
        for lg in sorted(set(lang.values()))
        if (ps := [p for p in part["test"] if lang[p] == lg])
    }
    empty_ref = [not full_ref[p] for p in part["test"]]
    empty_pred = [not x for x in pred_t]
    tp = sum(a and b for a, b in zip(empty_ref, empty_pred, strict=True))
    no_topic = {"support": sum(empty_ref), "predicted": sum(empty_pred)} | metrics.prf(
        tp, sum(empty_pred), sum(empty_ref)
    )

    # leakage: test pages whose component also has a page in this column's train
    train_comps = {component[p] for p in part["train"]}
    leaky = [p for p in part["test"] if component[p] in train_comps]
    clean = [p for p in part["test"] if component[p] not in train_comps]

    def pairs(pages: list[str]) -> list[tuple[list[str], list[str]]]:
        return [(pred_of[p], full_ref[p]) for p in pages]

    test_leak = {"leaky_pages": len(leaky), "clean_pages": len(clean)}
    if leaky and clean:
        test_leak |= {
            "leaky": compact(score(leaky, [pred_of[p] for p in leaky])),
            "clean": compact(score(clean, [pred_of[p] for p in clean])),
            "leaky_minus_clean_f1": agreement.f1_diff(
                [
                    (pairs([p for p in leaky if lang[p] == lg]),
                     pairs([p for p in clean if lang[p] == lg]))
                    for lg in sorted(set(lang.values()))
                ],
                tier1,
            ),
        }  # fmt: skip

    # panel reference without the teacher model's own vote
    ref = {}
    with args.reference.open() as f:
        for line in f:
            r = json.loads(line)
            votes = [[{"id": i} for i in v] for m, v in sorted(r["votes"].items())
                     if m != args.panel_leave_out]  # fmt: skip
            ref[r["page_id"]] = panel.consensus(votes, tier1, args.min_votes)
    not_test = [p for p in ref if p not in pred_of]
    if not_test:
        raise SystemExit(f"{len(not_test)} panel pages are not in test")
    on2 = [p for p in ref if panel.has_reference(ref[p], 2)]
    on1 = [p for p in ref if panel.has_reference(ref[p], 1)]

    def against_panel(pred: dict[str, list[str]]) -> dict:
        return {
            "tier2": agreement.summary([(pred[p], ref[p]["labels"]) for p in on2], tier1).get(
                "tier2"
            ),
            "tier1": agreement.summary([(pred[p], ref[p]["tier1"]) for p in on1], tier1).get(
                "tier1"
            ),
        }

    student_panel = against_panel(pred_of)
    teacher_panel = against_panel(full_ref)
    teacher_run = json.loads((args.labels_dir / args.labels_run / "run.json").read_text())
    if teacher_run["config"]["taxonomy_sha256"] != labels_json["source"]["sha256"]:
        raise SystemExit("the label run used a different taxonomy file")
    label_summary = Path(f"results/labels-{args.labels_run}.json")
    splits_report = Path(f"results/{args.splits}.json")

    def pick(path: Path, *keys: str):
        if not path.exists():
            return None
        v = json.loads(path.read_text())
        for k in keys:
            v = v[k]
        return v

    report = {
        **provenance.stamp(
            {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}, "train_tier1"
        ),
        "inputs": {
            "taxonomy_sha256": labels_json["source"]["sha256"],
            "label_set_sha256": pick(label_summary, "manifest", "label_set_sha256"),
            "splits_assignment_sha256": pick(splits_report, "assignment_sha256"),
            "panel_reference_sha256": sha256_file(args.reference),
            "seed": 0,
        },
        "environment": environment(),
        "model": {
            "lr": lr,
            "weight_decay": args.weight_decay,
            "best_epoch": hist["best_epoch"],
            "features": x_all.shape[1],
            "featurize_s": round(feat_s, 1),
            "device": device(),
            "temperature": round(temp, 3),
            "global_threshold": glob,
            "labels_learned": len(label_ids),
            "min_support": t["min_support"],
            "top1_floor": floor,
            "labels_with_own_threshold": int((thr != glob).sum()),
            "fit_s": round(fit_s, 1),
            "note": "fit and featurize times are training costs, not inference latency",
            "candidates": candidates,
        },
        "pages": {k: len(v) for k, v in part.items()},
        "val_cross_fitted_micro_f1": t["val_f1_cross"],
        "val_in_sample": compact(score(part["val"], pred_v)),
        "test": test,
        "test_supported_labels_never_predicted": sum(
            c["support"] > 0 and c["predicted"] == 0 for c in test["tier2"]["per_category"].values()
        ),
        "test_by_lang": by_lang,
        "test_rule_off": compact(score(part["test"], pred_t_off)),
        "top1_rule_minus_off": rule_effect,
        "test_no_topic": no_topic,
        "test_calibration": {
            "raw": metrics.calibration(y_test, metrics.sigmoid(z_t), label_ids),
            "temperature": metrics.calibration(y_test, prob_t, label_ids),
        },
        "test_leak": test_leak,
        "panel": {
            "reference": f"panel-v0 votes without {args.panel_leave_out}",
            "min_votes": args.min_votes,
            "coverage": {"pages": len(ref), "tier2": len(on2), "tier1": len(on1)},
            "student": student_panel,
            "teacher_same_pages": teacher_panel,
        },
    }
    Path("results").mkdir(exist_ok=True)
    Path(f"results/{args.name}.json").write_text(json.dumps(report, indent=1) + "\n")
    art = Path("artifacts") / args.name
    art.mkdir(parents=True, exist_ok=True)
    joblib.dump({"featurizer": feat, "temperature": temp, "thresholds": thr,
                 "label_ids": label_ids}, art / "featurizer.joblib")  # fmt: skip
    torch.save(head.state_dict(), art / "head.pt")
    with (art / "predictions.jsonl").open("w") as f:
        for split, pages, preds in (("val", part["val"], pred_v), ("test", part["test"], pred_t)):
            for p, pr in zip(pages, preds, strict=True):
                f.write(json.dumps({"page_id": p, "split": split, "labels": pr}) + "\n")
    t2, sp2 = report["test"], report["panel"]
    print(
        f"val cross-fitted {t['val_f1_cross']}; test micro F1 tier2 {t2['tier2']['micro']['f1']} "
        f"tier1 {t2['tier1']['micro']['f1']}; panel tier2 {sp2['student']['tier2']['f1']['value']}"
        f" (teacher {sp2['teacher_same_pages']['tier2']['f1']['value']}); leaky test pages "
        f"{test_leak['leaky_pages']}"
    )


if __name__ == "__main__":
    main()
