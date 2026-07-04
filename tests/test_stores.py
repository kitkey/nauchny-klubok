from p2kg.embedder import HashEmbedder, cosine
from p2kg.schema import Entity, EntityType, Provenance, Span, TextLoc
from p2kg.stores.graphstore import InMemoryGraph


def _ent(key, name, uuid):
    return Entity(uuid=uuid, key=key, type=EntityType.MATERIAL, canonical_name=name,
                  provenance=[Provenance(paper_ref="p", loc=TextLoc(span=Span(start=0, end=1)))])


def test_inmemory_upsert_and_find():
    g = InMemoryGraph()
    g.upsert_entities([_ent("Material:ni", "Ni", "u1")])
    assert g.find_entity_by_key("Material:ni").uuid == "u1"


def test_inmemory_merges_same_key():
    g = InMemoryGraph()
    g.upsert_entities([_ent("Material:ni", "Ni", "u1")])
    g.upsert_entities([_ent("Material:ni", "Nickel", "u2")])
    assert len(g.entities) == 1
    assert "Nickel" in g.find_entity_by_key("Material:ni").aliases


def test_paper_subgraph_filters_by_paper():
    g = InMemoryGraph()
    g.upsert_entities([_ent("Material:ni", "Ni", "u1")])
    sub = g.paper_subgraph("p")
    assert "entities" in sub and len(sub["entities"]) == 1


def test_embedder_deterministic_and_cosine():
    e = HashEmbedder()
    a = e.encode(["yield strength"])[0]
    b = e.encode(["yield strength"])[0]
    c = e.encode(["hardness"])[0]
    assert a == b and cosine(a, b) > 0.999
    assert cosine(a, c) < 0.999


def test_neo4j_module_importable():
    import importlib
    m = importlib.import_module("p2kg.stores.graphstore")
    assert hasattr(m, "Neo4jGraph")
