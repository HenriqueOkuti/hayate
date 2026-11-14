"""Tier-1 input and features, without torch: page input string, hashing and TF-IDF.

Kept apart from hayate.students.hashed (which trains with torch) so a CPU inference bundle can
load the fitted featurizer without installing torch.
"""

import re

import numpy as np
import scipy.sparse as sp
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
