from pathlib import Path

from p2kg.chunk import chunk_paper
from p2kg.ingest.pdf import PdfAdapter, count_tokens

FIX = Path(__file__).parent / "fixtures" / "sample.pdf"


def _paper():
    return PdfAdapter().load(str(FIX))


def test_chunk_spans_valid_and_within_bounds():
    paper = _paper()
    chunks = chunk_paper(paper, token_budget=300, overlap=30)
    assert len(chunks) > 1
    n = len(paper.raw_text)
    for c in chunks:
        assert 0 <= c.span.start < c.span.end <= n   # best-effort span в границах
        assert c.text.strip()


def test_first_chunk_text_present_in_raw():
    # offset-санити: содержимое первого куска реально есть в исходнике
    paper = _paper()
    chunks = chunk_paper(paper, token_budget=300, overlap=30)
    needle = chunks[0].text.strip()[:40]
    assert needle and needle in paper.raw_text


def test_chunk_indices_sequential():
    paper = _paper()
    chunks = chunk_paper(paper, token_budget=300, overlap=30)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert all(c.chunk_id == f"chunk-{c.index}" for c in chunks)


def test_chunks_respect_token_budget():
    paper = _paper()
    chunks = chunk_paper(paper, token_budget=300, overlap=30)
    non_atomic = [c for c in chunks if c.atomic_ref is None]
    assert non_atomic
    assert all(count_tokens(c.text) <= 400 for c in non_atomic)


def test_paper_ref_propagated():
    paper = _paper()
    chunks = chunk_paper(paper)
    assert all(c.paper_ref == paper.paper_ref for c in chunks)
