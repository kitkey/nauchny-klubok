from p2kg.config import Config
from p2kg.context import ArticleState, Deps
from p2kg.extract import s3_extract
from p2kg.extract._common import _AboutOut, _FrameOut
from p2kg.extract.text import _extract_text
from p2kg.llm.prompts import PromptManager
from p2kg.provenance import text_hash
from p2kg.schema import Chunk, EdgeType, EntityType, FrameType, Paper, Quantity, Role, Span

RAW = "Ni-15Cr alloy shows yield strength of 540 MPa after annealing at 800 C."


class FakeLLM:
    def __init__(self, ret):
        self.ret = ret

    def complete(self, prompt, *, model, schema=None, **kw):
        return self.ret


def _deps(ret):
    return Deps(llm=FakeLLM(ret), embed=None, prompts=PromptManager(),
                cfg=Config(), graph=None, docs=None)


def _paper():
    return Paper(paper_ref="p", raw_text=RAW, text_hash=text_hash(RAW))


def _chunk(atomic=None):
    return Chunk(chunk_id="chunk-0", paper_ref="p", index=0,
                 span=Span(start=0, end=len(RAW)), text=RAW, atomic_ref=atomic)


def test_extract_text_builds_fact_entities_edges():
    ret = [_FrameOut(
        frame_type=FrameType.MATERIAL_MEASUREMENT,
        slots={"material": "Ni-15Cr alloy", "property": "yield strength",
               "condition": "annealing at 800 C"},
        quantity=Quantity(value=540, unit="MPa"),
        statement="Ni-15Cr shows yield strength 540 MPa",
    )]
    lg = _extract_text(_deps(ret), _chunk(), [], _paper())
    assert len(lg.facts) == 1 and lg.facts[0].quantity.value == 540
    assert len(lg.entities) == 3
    etypes = {e.type for e in lg.entities}
    assert EntityType.MATERIAL in etypes and EntityType.PROPERTY in etypes
    edge_types = {e.type for e in lg.edges}
    assert EdgeType.HAS_MATERIAL in edge_types and EdgeType.HAS_PROPERTY in edge_types
    fid = lg.facts[0].uuid
    ent_ids = {e.uuid for e in lg.entities}
    assert all(e.src == fid and e.dst in ent_ids for e in lg.edges)


def test_entity_key_deterministic():
    def mk():
        return _extract_text(
            _deps([_FrameOut(frame_type=FrameType.MATERIAL_MEASUREMENT,
                             slots={"material": "Ni-15Cr"}, statement="x")]),
            _chunk(), [], _paper())
    assert mk().entities[0].key == mk().entities[0].key == "Material:ni-15cr"


def test_claim_fact_statement_only():
    ret = [_FrameOut(frame_type=FrameType.CLAIM_FACT, statement="Annealing improves strength")]
    lg = _extract_text(_deps(ret), _chunk(), [], _paper())
    assert len(lg.facts) == 1 and lg.facts[0].statement == "Annealing improves strength"
    assert len(lg.entities) == 0


def test_s3_extract_populates_state():
    ret = [_FrameOut(frame_type=FrameType.MATERIAL_MEASUREMENT,
                     slots={"material": "Ni-15Cr"}, statement="x")]
    st = ArticleState(paper_ref="p", paper=_paper(), chunks=[_chunk()])
    st = s3_extract(_deps(ret), st)
    assert st.stage_status["s3_extract"] == "ok" and len(st.facts) == 1 and len(st.entities) == 1


def test_table_chunk_uses_table_path():
    ret = [_FrameOut(frame_type=FrameType.MATERIAL_MEASUREMENT,
                     slots={"material": "Ni-15Cr", "property": "hardness"},
                     quantity=Quantity(value=180, unit="HV"), statement="t")]
    st = ArticleState(paper_ref="p", paper=_paper(), chunks=[_chunk(atomic="tbl-0")])
    st = s3_extract(_deps(ret), st)
    assert len(st.facts) == 1


def test_s3_skips_references_section():
    ret = [_FrameOut(frame_type=FrameType.MATERIAL_MEASUREMENT, slots={"material": "Ni"}, statement="x")]
    ref_chunk = Chunk(chunk_id="c-ref", paper_ref="p", index=0,
                      span=Span(start=0, end=len(RAW)), text=RAW, role_hint=Role.OTHER)
    st = ArticleState(paper_ref="p", paper=_paper(), chunks=[ref_chunk])
    st = s3_extract(_deps(ret), st)
    assert len(st.facts) == 0   # секция references/acknowledgments пропущена


def test_about_link_creates_mentions_edges():
    ret = [_FrameOut(frame_type=FrameType.CLAIM_FACT,
                     statement="Cr improves corrosion resistance",
                     about=[_AboutOut(mention="Cr", type=EntityType.ELEMENT),
                            _AboutOut(mention="corrosion resistance", type=EntityType.PROPERTY)])]
    lg = _extract_text(_deps(ret), _chunk(), [], _paper())
    assert len(lg.facts) == 1 and len(lg.entities) == 2
    assert len(lg.edges) == 2 and all(e.type == EdgeType.MENTIONS for e in lg.edges)
    fid = lg.facts[0].uuid
    assert all(e.src == fid for e in lg.edges)
