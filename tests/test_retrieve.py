from types import SimpleNamespace

from p2kg.config import Config
from p2kg.context import Deps
from p2kg.embedder import HashEmbedder
from p2kg.llm.prompts import PromptManager
from p2kg.retrieve import retrieve
from p2kg.schema import (
    Edge, EdgeType, Entity, EntityType, Fact, FrameType, Provenance, Quantity, Span, TextLoc,
)
from p2kg.stores.graphstore import InMemoryGraph


def _prov():
    return Provenance(paper_ref="p1", loc=TextLoc(span=Span(start=0, end=1)))


def _graph():
    g = InMemoryGraph()
    g.upsert_entities([
        Entity(uuid="m1", key="Material:mos2", type=EntityType.MATERIAL, canonical_name="MoS2"),
        Entity(uuid="m2", key="Material:wse2", type=EntityType.MATERIAL, canonical_name="WSe2"),
        Entity(uuid="pr", key="Property:bandgap", type=EntityType.PROPERTY, canonical_name="bandgap"),
    ])
    g.upsert_facts([
        Fact(uuid="f1", frame_type=FrameType.MATERIAL_MEASUREMENT, paper_ref="paper-A",
             statement="MoS2 has bandgap 1.8 eV", quantity=Quantity(value=1.8, unit="eV", raw="1.8 eV"),
             provenance=_prov()),
        Fact(uuid="f2", frame_type=FrameType.MATERIAL_MEASUREMENT, paper_ref="paper-B",
             statement="WSe2 has bandgap 1.6 eV", quantity=Quantity(value=1.6, unit="eV", raw="1.6 eV"),
             provenance=_prov()),
    ])
    g.upsert_edges([
        Edge(src="f1", dst="m1", type=EdgeType.HAS_MATERIAL, provenance=_prov()),
        Edge(src="f1", dst="pr", type=EdgeType.HAS_PROPERTY, provenance=_prov()),
        Edge(src="f2", dst="m2", type=EdgeType.HAS_MATERIAL, provenance=_prov()),
        Edge(src="f2", dst="pr", type=EdgeType.HAS_PROPERTY, provenance=_prov()),
    ])
    return g


def _deps(g):
    return Deps(llm=None, embed=HashEmbedder(), prompts=PromptManager(), cfg=Config(), graph=g, docs=None)


def test_tag_overlap_ranks_matching_fact_first():
    g = _graph()
    mentions = [SimpleNamespace(text="MoS2", type="Material"),
                SimpleNamespace(text="bandgap", type="Property")]
    res = retrieve(_deps(g), "какой bandgap у MoS2?", mentions=mentions)
    assert res.facts, "нет фактов в ответе"
    top = res.facts[0]
    assert "MoS2" in sum(top.participants.values(), []), "верхний факт не про MoS2"
    assert top.quantity == "1.8 eV"          # число из поля графа, не из модели
    assert top.source == "paper-A"           # провенанс/источник


def test_anchor_and_related_populated():
    g = _graph()
    mentions = [SimpleNamespace(text="MoS2", type="Material")]
    res = retrieve(_deps(g), "что известно про MoS2", mentions=mentions)
    assert "MoS2" in res.anchors
    assert "bandgap" in res.related          # сосед по факту
