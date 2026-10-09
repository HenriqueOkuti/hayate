import gzip

from hayate.pages import ccindex, extract, warc

# Synthetic HTML (not crawled text).
HTML = """<html><head><title> Receita de bolo </title>
<meta name="description" content="Um bolo simples de laranja.">
</head><body><nav>Menu Inicio Contato</nav><article><h1>Bolo de laranja</h1>
<p>Este bolo leva laranja, farinha, ovos e acucar. Bata tudo no liquidificador por cinco
minutos, despeje na forma untada e asse por quarenta minutos em forno medio.</p>
<p>Sirva frio com cafe. Rende doze fatias e dura tres dias fora da geladeira.</p>
</article><footer>Todos os direitos reservados</footer></body></html>"""


def test_extract_fields():
    ex = extract.extract(HTML)
    assert ex.title == "Receita de bolo"
    assert ex.meta_description == "Um bolo simples de laranja."
    assert "farinha" in ex.text_resiliparse
    assert ex.ms_trafilatura >= 0 and ex.ms_resiliparse >= 0


def test_decode_uses_header_charset():
    body = "acao: ação".encode("latin-1")
    assert extract.decode(body, "text/html; charset=ISO-8859-1") == "acao: ação"


def test_parse_record():
    http = b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n" + HTML.encode()
    head = (
        "WARC/1.0\r\nWARC-Type: response\r\nWARC-Target-URI: https://example.com/bolo\r\n"
        "WARC-Record-ID: <urn:uuid:00000000-0000-0000-0000-000000000000>\r\n"
        "WARC-Date: 2026-09-20T00:00:00Z\r\nContent-Type: application/http; msgtype=response\r\n"
        f"Content-Length: {len(http)}\r\n\r\n"
    ).encode()
    rec = warc.parse_record(gzip.compress(head + http + b"\r\n\r\n"))
    assert rec.target_uri == "https://example.com/bolo"
    assert rec.status == 200
    assert rec.content_type.startswith("text/html")
    assert rec.body == HTML.encode()


def test_draw_clusters_is_proportional_and_seeded():
    draws = ccindex.draw_clusters([0, 1, 99], 1000, seed=1)
    assert draws[0] == 0
    assert draws[2] > draws[1]
    assert sum(draws.values()) == 1000
    assert draws == ccindex.draw_clusters([0, 1, 99], 1000, seed=1)


def test_cap_domains_keeps_rank_order():
    pages = [
        {"domain": "a.com", "rank_key": "3"},
        {"domain": "a.com", "rank_key": "1"},
        {"domain": "b.com", "rank_key": "2"},
        {"domain": "a.com", "rank_key": "0"},
    ]
    kept = ccindex.cap_domains(pages, cap=2)
    assert [p["rank_key"] for p in kept] == ["0", "1", "2"]


def test_per_cluster():
    assert ccindex.per_cluster(13000, 120) == 109


def test_rate_limiter_spaces_calls():
    import time

    limiter = warc.RateLimiter(per_second=50)
    start = time.monotonic()
    for _ in range(6):
        limiter.wait()
    assert time.monotonic() - start >= 5 / 50 * 0.9
