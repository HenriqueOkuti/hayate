"""Tier-1 inference on the CPU without torch: hashing, TF-IDF, one sparse x dense product.

A bundle (written by scripts/export_tier1.py) is a directory with:
- featurizer.joblib: the fitted hayate.students.hashed.Featurizer (hashing parameters, IDF);
- weights.npy (features x labels, float32) and bias.npy (labels);
- meta.json: label ids, temperature, per-label thresholds, top-1 floor, max labels.
The stages are separate methods so the benchmark can time tokenization (`featurize`), the
forward pass (`forward`) and the decision (`decide`) apart (docs/measurement.md).
"""

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import scipy.sparse as sp


@dataclass
class Tier1:
    featurizer: object
    weights: np.ndarray
    bias: np.ndarray
    label_ids: list[str]
    temperature: float
    thresholds: np.ndarray
    floor: float | None
    max_labels: int

    @classmethod
    def load(cls, path: Path) -> "Tier1":
        meta = json.loads((path / "meta.json").read_text())
        return cls(
            featurizer=joblib.load(path / "featurizer.joblib"),
            weights=np.load(path / "weights.npy"),
            bias=np.load(path / "bias.npy"),
            label_ids=meta["label_ids"],
            temperature=meta["temperature"],
            thresholds=np.array(meta["thresholds"], dtype=np.float32),
            floor=meta["top1_floor"],
            max_labels=meta["max_labels"],
        )

    def featurize(self, docs: list[str]) -> sp.csr_matrix:
        return self.featurizer.transform(docs)

    def forward(self, x: sp.csr_matrix) -> np.ndarray:
        """Probabilities (pages x labels) from TF-IDF rows."""
        z = x @ self.weights + self.bias
        return 1 / (1 + np.exp(-np.clip(z / self.temperature, -50, 50)))

    def decide(self, prob: np.ndarray) -> list[list[str]]:
        out = []
        for row in prob:
            keep = np.flatnonzero(row >= self.thresholds)
            keep = keep[np.argsort(-row[keep])][: self.max_labels]
            if not len(keep) and self.floor is not None and row.max() >= self.floor:
                keep = [int(row.argmax())]
            out.append([self.label_ids[k] for k in keep])
        return out

    def predict(self, docs: list[str]) -> list[list[str]]:
        return self.decide(self.forward(self.featurize(docs)))
