import hashlib

import pytest

from hayate.taxonomy import iab

# A tiny synthetic TSV in the same layout as the IAB file (not the real taxonomy).
TSV = (
    b"Relational ID System\t\t\tContent Taxonomy v3.1 Tiered Categories\t\t\t\tExtension\r\n"
    b"Unique ID\tParent\tName\tTier 1\tTier 2\tTier 3\tTier 4\t\r\n"
    b"1\t\tAutos\tAutos\t\t\t\t\r\n"
    b"2\t1\tCars\tAutos\tCars\t\t\t\r\n"
    b"3\t2\tVintage Cars\tAutos\tCars\tVintage Cars\t\t\r\n"
    b"X9\t\tHealth\tHealth\t\t\t\tSCD\r\n"
    b"X10\tX9\tDiseases\tHealth\tDiseases\t\t\tSCD\r\n"
    b"G1\t\tGenres\tGenres\t\t\t\t\r\n"
    b"G2\tG1\tWestern\tGenres\tWestern\t\t\t\r\n"
)


def test_parse():
    nodes = {n.id: n for n in iab.parse(TSV)}
    assert len(nodes) == 7
    assert nodes["3"].tier == 3
    assert nodes["3"].parent == "2"
    assert nodes["1"].parent is None
    assert nodes["X10"].scd and not nodes["2"].scd


def test_label_set_depth_and_exclusion():
    labels = iab.label_set(iab.parse(TSV), max_tier=2, exclude_tier1=["Genres"])
    assert [n.id for n in labels] == ["1", "2", "X9", "X10"]


def test_label_set_unknown_exclusion():
    with pytest.raises(ValueError):
        iab.label_set(iab.parse(TSV), max_tier=2, exclude_tier1=["Nope"])


def test_verify():
    iab.verify(TSV, hashlib.sha256(TSV).hexdigest())
    with pytest.raises(iab.ChecksumError):
        iab.verify(TSV + b"x", hashlib.sha256(TSV).hexdigest())


def test_raw_url_quotes_path():
    url = iab.raw_url("o/r", "abc", "Content Taxonomies/T 3.1.tsv")
    assert url == "https://raw.githubusercontent.com/o/r/abc/Content%20Taxonomies/T%203.1.tsv"
