from collections import Counter, defaultdict

import pytest

from hayate.data.splits import Page, assign, components, near_duplicates

FRACS = {"val": 0.1, "test": 0.1}
LOREM = "the quick brown fox jumps over the lazy dog while seven wizards box nimbly at dawn " * 4


def sample(n_domains: int = 2000) -> tuple[list[Page], dict[str, str]]:
    pages, texts = [], {}
    for i in range(n_domains):
        lang = "por" if i % 2 else "eng"
        for j in range(1 + i % 3):
            pid = f"d{i}-{j}"
            pages.append(Page(pid, f"site{i}.test", lang))
            texts[pid] = f"page {i} {j} unique words number{i} and more{j}"
    pages.append(Page("mixed-en", "site1.test", "eng"))  # one domain in both languages
    texts["mixed-en"] = "a bilingual page"
    return pages, texts


def test_components_join_brand_same_text_and_near_duplicates():
    pages = [
        Page("a", "news.com", "eng"),
        Page("b", "news.com.br", "por"),  # same brand
        Page("c", "x.org", "eng"),
        Page("d", "y.net", "eng"),  # same text as c
        Page("e", "z.io", "eng"),
        Page("f", "w.io", "eng"),  # near-duplicate of e
        Page("g", "alone.pt", "por"),
        Page("h", "empty.pt", "por"),
        Page("i", "empty2.pt", "por"),  # empty texts do not join
    ]
    texts = {
        "a": "one", "b": "two", "c": "Same TEXT here!", "d": "same text here",
        "e": LOREM, "f": LOREM + " extra", "g": LOREM[:40] + " different ending entirely",
        "h": "", "i": "",
    }  # fmt: skip
    comp, links = components(pages, texts, 0.8)
    assert comp["news.com"] == comp["news.com.br"]
    assert comp["x.org"] == comp["y.net"]
    assert comp["z.io"] == comp["w.io"]
    assert len({comp[d] for d in ("alone.pt", "empty.pt", "empty2.pt", "x.org", "z.io")}) == 5
    assert links == {"brand": 1, "same_text": 1, "near_duplicate": 1}
    assert near_duplicates({"e": LOREM, "f": LOREM + " extra"}, 0.8) == [("e", "f")]


def test_split_is_leak_free_and_forced_components_stay_put():
    pages, texts = sample()
    texts["d7-0"] = texts["d4-0"]  # site7 joins site4, a forced-train domain
    comp, _ = components(pages, texts, 0.8)
    out = assign(pages, comp, {"site4.test"}, {"site5.test"}, 7, FRACS)
    splits_of = defaultdict(set)
    for p in pages:
        splits_of[comp[p.domain]].add(out[p.page_id][0])
    assert all(len(s) == 1 for s in splits_of.values())
    for p in pages:
        if p.domain in ("site4.test", "site7.test"):
            assert out[p.page_id] == ("train", "train")
        if p.domain == "site5.test":
            assert out[p.page_id] == ("test", "test")


@pytest.mark.parametrize("col", [0, 1])
def test_fractions_per_language(col):
    pages, texts = sample()
    comp, _ = components(pages, texts, 0.8)
    out = assign(pages, comp, set(), set(), 7, FRACS)
    for lang in ("por", "eng"):
        ps = [p for p in pages if p.lang == lang]
        c = Counter(out[p.page_id][col] for p in ps)
        assert abs(c["test"] / len(ps) - 0.1) < 0.03
        assert abs(c["val"] / len(ps) - 0.1) < 0.03


def test_stable_when_pages_are_added():
    pages, texts = sample()
    comp, _ = components(pages, texts, 0.8)
    a = assign(pages, comp, set(), set(), 7, FRACS)
    more = pages + [Page(f"new{i}", f"new{i}.test", "eng") for i in range(500)]
    texts |= {f"new{i}": f"fresh page {i}" for i in range(500)}
    comp2, _ = components(more, texts, 0.8)
    b = assign(more, comp2, set(), set(), 7, FRACS)
    assert all(b[p] == a[p] for p in a)
    assert a != assign(pages, comp, set(), set(), 8, FRACS)


def test_clash_raises():
    pages, texts = sample()
    texts["d9-0"] = texts["d3-0"]
    comp, _ = components(pages, texts, 0.8)
    with pytest.raises(ValueError):
        assign(pages, comp, {"site3.test"}, {"site9.test"}, 7, FRACS)
