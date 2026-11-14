"""Tier 1: hashed word and character n-grams, TF-IDF weighted, one linear layer over all labels.

The input is one string per page: URL words, title, meta description and the first `max_chars`
characters of the page text. Two `HashingVectorizer`s (word 1-2 grams and `char_wb` 3-5 grams,
so no vocabulary is stored and unseen words still hash somewhere) feed a TF-IDF reweighting
fitted on the training pages (`Featurizer`). The head is a single linear map from the hashed
features to one logit per label, trained jointly for all labels with binary cross-entropy
(`LinearHead`). On the GPU this is an `EmbeddingBag` in sum mode with the TF-IDF values as
weights: one sparse row times the weight matrix, the same model as one logistic regression per
label, without one pass over the data per label. The evaluation turns logits into probabilities
with a temperature and into labels with thresholds, both fitted on validation.
"""

import copy
import re
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
import torch
from sklearn.feature_extraction.text import HashingVectorizer, TfidfTransformer

URL_NOISE = {"https", "http", "www"}
URL_SPLIT = re.compile(r"[^0-9a-zA-ZÀ-ɏ]+")


def page_input(url: str, title: str, description: str, text: str, max_chars: int) -> str:
    url_words = " ".join(w for w in URL_SPLIT.split(url.lower()) if w and w not in URL_NOISE)
    return "\n".join([url_words, title or "", description or "", (text or "")[:max_chars]])


class Featurizer:
    def __init__(self, word_bits: int = 18, char_bits: int = 18) -> None:
        common = {"alternate_sign": False, "norm": None, "lowercase": True}
        self.word = HashingVectorizer(n_features=2**word_bits, ngram_range=(1, 2), **common)
        self.char = HashingVectorizer(
            n_features=2**char_bits, analyzer="char_wb", ngram_range=(3, 5), **common
        )
        self.n_features = 2**word_bits + 2**char_bits
        self.tfidf = TfidfTransformer(sublinear_tf=True)

    def hash(self, docs: list[str]) -> sp.csr_matrix:
        """Raw hashed counts; stateless, so any pages can be hashed once and reused."""
        return sp.hstack([self.word.transform(docs), self.char.transform(docs)]).tocsr()

    def fit(self, hashed_train: sp.csr_matrix) -> "Featurizer":
        self.tfidf.fit(hashed_train)
        return self

    def weigh(self, hashed: sp.csr_matrix) -> sp.csr_matrix:
        return self.tfidf.transform(hashed).astype(np.float32).tocsr()

    def transform(self, docs: list[str]) -> sp.csr_matrix:
        return self.weigh(self.hash(docs))


@dataclass
class HeadConfig:
    weight_decay: float = 1e-4
    lr: float = 3e-3
    max_epochs: int = 20
    patience: int = 3
    batch_size: int = 256
    seed: int = 0


def _bag(x: sp.csr_matrix, device: str) -> tuple[torch.Tensor, ...]:
    """CSR rows as EmbeddingBag inputs: flat feature ids, row offsets and TF-IDF weights."""
    return (
        torch.from_numpy(x.indices.astype(np.int64)).to(device),
        torch.from_numpy(x.indptr[:-1].astype(np.int64)).to(device),
        torch.from_numpy(x.data).to(device),
    )


class LinearHead(torch.nn.Module):
    def __init__(self, n_features: int, n_labels: int) -> None:
        super().__init__()
        self.weight = torch.nn.EmbeddingBag(n_features, n_labels, mode="sum")
        self.bias = torch.nn.Parameter(torch.zeros(n_labels))
        torch.nn.init.zeros_(self.weight.weight)

    def forward(self, ids, offsets, weights) -> torch.Tensor:
        return self.weight(ids, offsets, per_sample_weights=weights) + self.bias


def device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def logits(head: LinearHead, x: sp.csr_matrix, batch_size: int = 1024) -> np.ndarray:
    dev = next(head.parameters()).device
    out = []
    head.eval()
    with torch.no_grad():
        for i in range(0, x.shape[0], batch_size):
            out.append(head(*_bag(x[i : i + batch_size], dev)).float().cpu().numpy())
    return np.concatenate(out) if out else np.zeros((0, head.bias.shape[0]), np.float32)


def train_head(
    x: sp.csr_matrix, y: np.ndarray, x_val: sp.csr_matrix, y_val: np.ndarray, cfg: HeadConfig
) -> tuple[LinearHead, dict]:
    """AdamW on mean BCE; keeps the epoch with the lowest validation BCE (early stopping)."""
    torch.manual_seed(cfg.seed)
    rng = np.random.default_rng(cfg.seed)
    dev = device()
    head = LinearHead(x.shape[1], y.shape[1]).to(dev)
    # positive-class bias start: log odds of each label's base rate, so early epochs aren't spent
    # learning that most labels are off
    rate = np.clip(y.mean(0), 1e-4, 1 - 1e-4)
    head.bias.data = torch.tensor(np.log(rate / (1 - rate)), dtype=torch.float32, device=dev)
    opt = torch.optim.AdamW(head.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    loss_fn = torch.nn.BCEWithLogitsLoss()
    yt = torch.from_numpy(y.astype(np.float32))
    yv = torch.from_numpy(y_val.astype(np.float32))
    best, best_state, history, wait = np.inf, None, [], 0
    for _ in range(cfg.max_epochs):
        head.train()
        order = rng.permutation(x.shape[0])
        for i in range(0, len(order), cfg.batch_size):
            rows = order[i : i + cfg.batch_size]
            loss = loss_fn(head(*_bag(x[rows], dev)), yt[rows].to(dev))
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
        val_loss = float(loss_fn(torch.from_numpy(logits(head, x_val)), yv))
        history.append(round(val_loss, 6))
        if val_loss < best - 1e-6:
            best, best_state, wait = val_loss, copy.deepcopy(head.state_dict()), 0
        else:
            wait += 1
            if wait >= cfg.patience:
                break
    head.load_state_dict(best_state)
    return head, {"val_bce_by_epoch": history, "best_epoch": int(np.argmin(history)) + 1}
