from p2kg.config import Config
from p2kg.context import ArticleState, Deps
from p2kg.link.resolve import _Relation, _ResolveOut, _resolve_entities
from p2kg.llm.prompts import PromptManager
from p2kg.schema import (
    Edge, EdgeType, Entity, EntityType, Fact, FrameType, Provenance, Span, TextLoc,
)


class FakeLLM:
    def __init__(self, ret):
        self.ret = ret

    def complete(self, user, *, system=None, model, schema=None, **kw):
        return self.ret


def _deps(ret):
    return Deps(llm=FakeLLM(ret), embed=None, prompts=PromptManager(), cfg=Config(),
                graph=None, docs=None)


def _prov():
    return Provenance(paper_ref="p", loc=TextLoc(span=Span(start=0, end=1)))


def _ent(key, name, uuid):
    return Entity(uuid=uuid, key=key, type=EntityType.PROPERTY, canonical_name=name, provenance=[_prov()])


def _fact(uuid):
    return Fact(uuid=uuid, frame_type=FrameType.MATERIAL_MEASUREMENT, paper_ref="p",
                statement="x", provenance=_prov())


def test_resolve_merges_and_adds_hierarchy():
    st = ArticleState(
        paper_ref="p",
        entities=[_ent("Property:electronic-bandgap", "electronic bandgap", "u1"),
                  _ent("Property:egap", "Egap", "u2"),
                  _ent("Property:topological-band-gap", "topological band gap", "u3")],
        facts=[_fact("f1")],
        edges=[Edge(src="f1", dst="u2", type=EdgeType.HAS_PROPERTY, provenance=_prov())])
    ret = _ResolveOut(
        merge=[["electronic bandgap", "Egap"]],
        relations=[_Relation(child="topological band gap", parent="electronic bandgap", rel="SUBTYPE_OF")])
    _resolve_entities(_deps(ret), st)

    names = {e.canonical_name for e in st.entities}
    assert names == {"electronic bandgap", "topological band gap"}   # Egap слит в канон
    assert "Egap" in st.entities[0].aliases or any("Egap" in e.aliases for e in st.entities)
    # ребро факта перевешено на канон u1
    assert any(ed.dst == "u1" and ed.type == EdgeType.HAS_PROPERTY for ed in st.edges)
    # добавлено ребро иерархии topological band gap -> electronic bandgap
    assert any(ed.type == EdgeType.SUBTYPE_OF and ed.src == "u3" and ed.dst == "u1" for ed in st.edges)


def test_resolve_skips_singleton_types():
    # один Property -> группа <2 -> LLM не зовётся, ret игнорируется
    st = ArticleState(paper_ref="p", entities=[_ent("Property:density", "density", "u1")],
                      facts=[], edges=[])
    _resolve_entities(_deps(None), st)
    assert len(st.entities) == 1 and st.entities[0].canonical_name == "density"
