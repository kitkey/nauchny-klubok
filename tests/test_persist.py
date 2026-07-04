from p2kg.config import Config
from p2kg.context import ArticleState, Deps
from p2kg.persist import persist
from p2kg.schema import (
    Edge, EdgeType, Entity, EntityType, Fact, FrameType, Provenance, Span, TextLoc,
)
from p2kg.stores.graphstore import InMemoryGraph


def test_persist_writes_graph():
    g = InMemoryGraph()
    deps = Deps(llm=None, embed=None, prompts=None, cfg=Config(), graph=g, docs=None)
    prov = Provenance(paper_ref="p", loc=TextLoc(span=Span(start=0, end=1)))
    e = Entity(uuid="u1", key="Material:ni", type=EntityType.MATERIAL, canonical_name="Ni", provenance=[prov])
    f = Fact(uuid="f1", frame_type=FrameType.MATERIAL_MEASUREMENT, paper_ref="p", provenance=prov)
    ed = Edge(src="f1", dst="u1", type=EdgeType.HAS_MATERIAL, provenance=prov)
    st = ArticleState(paper_ref="p", entities=[e], facts=[f], edges=[ed])
    persist(deps, st)
    assert g.find_entity_by_key("Material:ni") is not None
    assert len(g.facts) == 1 and len(g.edges) == 1
    assert st.stage_status["persist"] == "ok"
