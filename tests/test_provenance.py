from p2kg import provenance as P
from p2kg.schema import Span

RAW = "Intro. The proposed method CAM-Net achieves\n540 MPa.  The proposed method is fast."


def test_text_hash_deterministic():
    assert P.text_hash("abc") == P.text_hash("abc") != P.text_hash("abd")


def test_slice_span():
    assert P.slice_span(RAW, Span(start=0, end=5)) == "Intro"


def test_find_anchor_exact():
    sp = P.find_anchor(RAW, "CAM-Net achieves")
    assert sp is not None and P.slice_span(RAW, sp) == "CAM-Net achieves"


def test_find_anchor_whitespace_robust():
    sp = P.find_anchor(RAW, "achieves 540 MPa")
    assert sp is not None
    seg = P.slice_span(RAW, sp)
    assert "achieves" in seg and "540" in seg


def test_find_anchor_search_from_second_occurrence():
    first = P.find_anchor(RAW, "The proposed method")
    second = P.find_anchor(RAW, "The proposed method", search_from=first.end)
    assert second is not None and second.start > first.start


def test_find_anchor_not_found_returns_none():
    assert P.find_anchor(RAW, "nonexistent phrase") is None


def test_find_anchor_with_end_anchor():
    sp = P.find_anchor(RAW, "The proposed method", end_anchor="CAM-Net")
    assert sp is not None and P.slice_span(RAW, sp).endswith("CAM-Net")


def test_verify_span_bounds_and_anchor():
    sp = P.find_anchor(RAW, "CAM-Net")
    assert P.verify_span(RAW, sp, expected_anchor="CAM-Net") is True
    assert P.verify_span(RAW, Span(start=10, end=5)) is False
