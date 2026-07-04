"""Регрессия: после отключения instructor-reask (max_retries=0) схемы должны сами терпеть
легитимный null от модели, иначе один кривой элемент валит весь вызов -> потеря фактов."""
from p2kg.extract._common import _FrameOut
from p2kg.link.concepts import _DefineOut, _HierOut
from p2kg.link.resolve import _ResolveOut
from p2kg.schema import FrameType


def test_frame_drops_null_condition_slot():
    # модель шлёт condition: null, когда условия нет — раньше падало на dict[str,str]
    f = _FrameOut.model_validate({
        "frame_type": FrameType.MATERIAL_MEASUREMENT.value,
        "slots": {"material": "MAPbI3", "property": "bandgap", "condition": None},
    })
    assert f.slots == {"material": "MAPbI3", "property": "bandgap"}   # null-слот выкинут, фрейм цел


def test_frame_none_scalars_coerced():
    f = _FrameOut.model_validate({
        "frame_type": FrameType.CLAIM_FACT.value,
        "statement": None, "negated": None, "about": None, "open_edges": None,
    })
    assert f.statement == "" and f.negated is False and f.about == [] and f.open_edges == []


def test_frame_drops_malformed_list_items():
    f = _FrameOut.model_validate({
        "frame_type": FrameType.CLAIM_FACT.value,
        "about": [{"mention": "MAPbI3", "type": "Material"}, {"mention": None, "type": "Material"},
                  {"mention": "x", "type": "MATERIAL"}],   # null-mention и кривой enum -> оба выкинуты
        "open_edges": [{"src_anchor": "a", "dst_anchor": "b", "rel": "X"},
                       {"src_anchor": None, "dst_anchor": "b", "rel": "X"}],
    })
    assert len(f.about) == 1 and len(f.open_edges) == 1   # кривые элементы выкинуты, валидный остался


def test_resolve_drops_malformed():
    out = _ResolveOut.model_validate({
        "merge": [["a", "b"], ["solo"], ["x", None]],          # <2 валидных имён -> кластер выкинут
        "relations": [{"child": "a", "parent": "b"}, {"child": None, "parent": "b"}],
    })
    assert out.merge == [["a", "b"], ["x"]] or out.merge == [["a", "b"]]   # ["x", null]->["x"] (<2) выкинут
    assert out.merge == [["a", "b"]]
    assert len(out.relations) == 1


def test_concept_schemas_tolerate_null():
    assert _DefineOut.model_validate({"definition": None}).definition == ""
    h = _HierOut.model_validate({"relations": [{"id": 0, "rel": "parent"}, {"id": None, "rel": "child"}]})
    assert len(h.relations) == 1
