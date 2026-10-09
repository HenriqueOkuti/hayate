"""HTML -> text with both extractors, plus the cheap fields (title, meta description).

Both extractors run on the same decoded HTML, and each one is timed, since extraction is
reported as its own latency stage (docs/data.md).
"""

import time
from dataclasses import dataclass

import trafilatura
from resiliparse.extract.html2text import extract_plain_text
from resiliparse.parse.encoding import bytes_to_str, detect_encoding
from resiliparse.parse.html import HTMLTree


@dataclass
class Extracted:
    title: str
    meta_description: str
    text_trafilatura: str
    text_resiliparse: str
    ms_trafilatura: float
    ms_resiliparse: float


def decode(body: bytes, content_type: str = "") -> str:
    """Decode with the charset from the HTTP header if any, else detect it."""
    charset = ""
    if "charset=" in content_type.lower():
        charset = content_type.lower().split("charset=", 1)[1].split(";")[0].strip(" \"'")
    return bytes_to_str(body, charset or detect_encoding(body))


def meta_description(tree: HTMLTree) -> str:
    for el in tree.head.get_elements_by_tag_name("meta") if tree.head else []:
        name = (el.getattr("name") or el.getattr("property") or "").lower()
        if name in ("description", "og:description"):
            return (el.getattr("content") or "").strip()
    return ""


def extract(html: str) -> Extracted:
    t0 = time.perf_counter_ns()
    text_t = trafilatura.extract(html, include_comments=False, include_tables=True) or ""
    t1 = time.perf_counter_ns()
    tree = HTMLTree.parse(html)
    text_r = extract_plain_text(tree, main_content=True)
    t2 = time.perf_counter_ns()
    return Extracted(
        title=(tree.title or "").strip(),
        meta_description=meta_description(tree),
        text_trafilatura=text_t,
        text_resiliparse=text_r,
        ms_trafilatura=(t1 - t0) / 1e6,
        ms_resiliparse=(t2 - t1) / 1e6,
    )
