from p2kg.config import Config
from p2kg.context import ArticleState, Deps
from p2kg.llm.prompts import PromptManager
from p2kg.provenance import text_hash
from p2kg.roles import _PassageTag, _tag_chunk, s2_roles
from p2kg.schema import Chunk, Paper, Role, Span

RAW = "The method works well. It is fast and cheap to produce."


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


def test_tag_chunk_maps_anchor_to_unit():
    ret = [_PassageTag(anchor="The method works", role=Role.METHOD, role_confidence=0.9)]
    units = _tag_chunk(_deps(ret), _chunk(), _paper())
    assert len(units) == 1
    u = units[0]
    assert u.role == Role.METHOD and u.span.start == 0 and "method works" in u.text


def test_tag_chunk_anchor_not_found_falls_back_to_chunk():
    ret = [_PassageTag(anchor="totally absent phrase", role=Role.RESULT, role_confidence=0.7)]
    units = _tag_chunk(_deps(ret), _chunk(), _paper())
    assert len(units) == 1 and units[0].span.start == 0 and units[0].span.end == len(RAW)


def test_atomic_chunk_single_result_unit():
    units = _tag_chunk(_deps([]), _chunk(atomic="tbl-0"), _paper())
    assert len(units) == 1 and units[0].role == Role.RESULT


def test_empty_tags_yields_other_unit():
    units = _tag_chunk(_deps([]), _chunk(), _paper())
    assert len(units) == 1 and units[0].role == Role.OTHER


def test_s2_roles_populates_units():
    ret = [_PassageTag(anchor="The method works", role=Role.METHOD, role_confidence=0.9)]
    st = ArticleState(paper_ref="p", paper=_paper(), chunks=[_chunk()])
    st = s2_roles(_deps(ret), st)
    assert st.stage_status["s2_roles"] == "ok" and len(st.units) == 1
