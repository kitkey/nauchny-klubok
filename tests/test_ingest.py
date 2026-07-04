from pathlib import Path

import pytest

from p2kg.ingest import pdf as PDF
from p2kg.ingest.arxiv import ArxivAdapter
from p2kg.ingest.base import ingest
from p2kg.ingest.pdf import PdfAdapter
from p2kg.provenance import text_hash

FIX = Path(__file__).parent / "fixtures" / "sample.pdf"


def test_count_tokens():
    assert PDF.count_tokens("") == 1
    assert PDF.count_tokens("a" * 40) == 10


def test_detect_lang():
    assert PDF.detect_lang("hello world this is english text") == "en"
    assert PDF.detect_lang("привет это русский научный текст здесь") == "ru"
    assert PDF.detect_lang("1234 5678") is None


def test_needs_ocr_true_on_empty():
    assert PDF.needs_ocr("", 3) is True
    assert PDF.needs_ocr("a" * 5000 + " word " * 500, 3) is False


def test_extract_text_offsets_consistent():
    ex = PDF.extract_text(FIX)
    assert len(ex.raw_text) > 500
    assert ex.page_map[-1][1] == len(ex.raw_text)   # cursor == len(raw_text)
    assert len(ex.page_map) >= 1 and ex.parser == "pymupdf"


def test_detect_sections_valid_and_stitched():
    ex = PDF.extract_text(FIX)
    secs, reliable = PDF.detect_sections_heuristic(ex.raw_text, ex.page_map)
    assert isinstance(secs, list) and len(secs) >= 1 and isinstance(reliable, bool)
    for i, s in enumerate(secs):
        assert 0 <= s.span.start < s.span.end <= len(ex.raw_text)
        if i + 1 < len(secs):
            assert s.span.end == secs[i + 1].span.start   # стыкуются


def test_detect_tables_figures_are_lists():
    ex = PDF.extract_text(FIX)
    assert isinstance(PDF.detect_tables(ex.raw_text, ex.page_map), list)
    assert isinstance(PDF.detect_figures(ex.raw_text, ex.page_map), list)
    assert isinstance(PDF.detect_refs(ex.raw_text), list)


def test_pdf_adapter_load():
    paper = PdfAdapter().load(str(FIX))
    assert paper.raw_text and paper.text_hash == text_hash(paper.raw_text)
    assert paper.parse_meta.n_chars == len(paper.raw_text)
    assert paper.parse_meta.n_pages >= 1
    assert paper.paper_ref == "sample"


def test_ingest_router_dispatches_pdf():
    paper = ingest(str(FIX))
    assert paper.parse_meta.parser == "pymupdf"


def test_arxiv_adapter_can_handle():
    a = ArxivAdapter()
    assert a.can_handle("2502.06472")
    assert a.can_handle("arxiv:2502.06472v1")
    assert a.can_handle("https://arxiv.org/abs/2502.06472")
    assert not a.can_handle("sample.pdf")


def test_llm_segment_stub_raises():
    with pytest.raises(NotImplementedError):
        PDF.llm_segment("x", [(0, 1, 0)])
