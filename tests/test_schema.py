import pytest
from pydantic import ValidationError

from p2kg import schema as S


def test_quantity_defaults():
    q = S.Quantity(value=540.0, unit="MPa")
    assert q.operator == "=" and q.uncertainty is None


def test_raw_text_frozen():
    p = S.Paper(paper_ref="arxiv:1v1", raw_text="abc", text_hash="x")
    with pytest.raises(ValidationError):
        p.raw_text = "changed"


def test_edge_open_exists_and_fact_axes():
    assert S.EdgeType.OPEN.value == "OPEN"
    f = S.Fact(
        uuid="u1",
        frame_type=S.FrameType.MATERIAL_MEASUREMENT,
        paper_ref="p",
        provenance=S.Provenance(paper_ref="p", loc=S.TextLoc(span=S.Span(start=0, end=3))),
    )
    assert f.negated is False and f.status == S.FactStatus.UNVERIFIED
    assert f.confidence == 0.0 and f.clarity == 0.0 and f.relevance == 0.0


def test_provenance_locator_union():
    pr = S.Provenance(paper_ref="p", loc=S.TableLoc(table_ref="tbl-0", row=1, col=2))
    assert pr.loc.kind == "table" and pr.loc.row == 1


def test_role_has_other():
    assert S.Role.OTHER.value == "other"
