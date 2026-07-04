from p2kg.config import Config
from p2kg.context import ArticleState, Deps
from p2kg.embedder import HashEmbedder
from p2kg.link import s4_link
from p2kg.link.canon import _RelVerdict, _canon_predicates
from p2kg.link.dedup import _dedup_entities, _dedup_facts
from p2kg.link.stitch import _StitchOut, _stitch
from p2kg.llm.prompts import PromptManager
from p2kg.schema import (
    Edge, EdgeType, Entity, EntityType, Fact, FactStatus, FrameType, Provenance, Quantity, Span, TextLoc,
)


class FakeLLM:
    def __init__(self, ret):
        self.ret = ret

    def complete(self, prompt, *, model, schema=None, **kw):
        return self.ret


def _deps(ret=None, embed=None):
    return Deps(llm=FakeLLM(ret), embed=embed, prompts=PromptManager(), cfg=Config(),
                graph=None, docs=None)


def _prov():
    return Provenance(paper_ref="p", loc=TextLoc(span=Span(start=0, end=1)))


def _ent(key, name, uuid):
    return Entity(uuid=uuid, key=key, type=EntityType.MATERIAL, canonical_name=name, provenance=[_prov()])


def _fact(uuid, frame=FrameType.MATERIAL_MEASUREMENT, q=None, statement="s"):
    return Fact(uuid=uuid, frame_type=frame, paper_ref="p", statement=statement, quantity=q, provenance=_prov())


def test_dedup_entities_key_merge_and_rewire():
    st = ArticleState(paper_ref="p", entities=[_ent("Material:ni", "Ni", "u1"),
                                               _ent("Material:ni", "Nickel", "u2")],
                      facts=[_fact("f1")],
                      edges=[Edge(src="f1", dst="u1", type=EdgeType.HAS_MATERIAL, provenance=_prov()),
                             Edge(src="f1", dst="u2", type=EdgeType.HAS_MATERIAL, provenance=_prov())])
    _dedup_entities(_deps(), st)
    assert len(st.entities) == 1
    assert {ed.dst for ed in st.edges} == {st.entities[0].uuid}


def test_dedup_facts_merges_duplicate():
    st = ArticleState(paper_ref="p", entities=[_ent("Material:ni", "Ni", "u1")],
                      facts=[_fact("f1", q=Quantity(value=540, unit="MPa")),
                             _fact("f2", q=Quantity(value=540, unit="MPa"))],
                      edges=[Edge(src="f1", dst="u1", type=EdgeType.HAS_MATERIAL, provenance=_prov()),
                             Edge(src="f2", dst="u1", type=EdgeType.HAS_MATERIAL, provenance=_prov())])
    _dedup_facts(_deps(), st)
    assert len(st.facts) == 1


def test_dedup_facts_contests_conflicting_value():
    st = ArticleState(paper_ref="p", entities=[_ent("Material:ni", "Ni", "u1")],
                      facts=[_fact("f1", q=Quantity(value=540, unit="MPa")),
                             _fact("f2", q=Quantity(value=600, unit="MPa"))],
                      edges=[Edge(src="f1", dst="u1", type=EdgeType.HAS_MATERIAL, provenance=_prov()),
                             Edge(src="f2", dst="u1", type=EdgeType.HAS_MATERIAL, provenance=_prov())])
    _dedup_facts(_deps(), st)
    assert all(f.status == FactStatus.CONTESTED for f in st.facts)
    assert any(ed.type == EdgeType.CONTRADICTED_BY for ed in st.edges)


def test_canon_predicates_retypes_open():
    st = ArticleState(paper_ref="p", entities=[_ent("Material:ni", "Ni", "u1")], facts=[_fact("f1")],
                      edges=[Edge(src="f1", dst="u1", type=EdgeType.OPEN, rel="passivates", provenance=_prov())])
    _canon_predicates(_deps(_RelVerdict(core_type="INHIBITS")), st)
    assert st.edges[0].type == EdgeType.INHIBITS


def test_stitch_adds_supported_by():
    st = ArticleState(paper_ref="p", entities=[_ent("Material:ni", "Ni", "u1")],
                      facts=[_fact("c1", frame=FrameType.CLAIM_FACT, statement="Ni is strong"),
                             _fact("m1", frame=FrameType.MATERIAL_MEASUREMENT, q=Quantity(value=540, unit="MPa"))],
                      edges=[Edge(src="c1", dst="u1", type=EdgeType.MENTIONS, provenance=_prov()),
                             Edge(src="m1", dst="u1", type=EdgeType.HAS_MATERIAL, provenance=_prov())])
    _stitch(_deps(_StitchOut(supported_ids=[0])), st)
    assert any(ed.type == EdgeType.SUPPORTED_BY for ed in st.edges)


def test_s4_link_runs_end_to_end():
    st = ArticleState(paper_ref="p", entities=[_ent("Material:ni", "Ni", "u1")], facts=[_fact("f1")],
                      edges=[Edge(src="f1", dst="u1", type=EdgeType.HAS_MATERIAL, provenance=_prov())])
    st = s4_link(_deps(_StitchOut(supported_ids=[]), embed=HashEmbedder()), st)
    assert st.stage_status["s4_link"] == "ok"
