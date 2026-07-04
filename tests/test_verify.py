from p2kg.config import Config
from p2kg.context import ArticleState, Deps
from p2kg.llm.prompts import PromptManager
from p2kg.schema import Fact, FactStatus, FrameType, Provenance, Span, TextLoc
from p2kg.verify import _VerifyItem, s5_verify


class FakeLLM:
    def __init__(self, ret):
        self.ret = ret

    def complete(self, prompt, *, model, schema=None, **kw):
        return self.ret


def _deps(ret):
    return Deps(llm=FakeLLM(ret), embed=None, prompts=PromptManager(), cfg=Config(),
                graph=None, docs=None)


def _fact(uuid, status=FactStatus.UNVERIFIED):
    return Fact(uuid=uuid, frame_type=FrameType.MATERIAL_MEASUREMENT, paper_ref="p",
                status=status, statement="s",
                provenance=Provenance(paper_ref="p", loc=TextLoc(span=Span(start=0, end=1))))


def test_verify_sets_verified_above_theta():
    st = ArticleState(paper_ref="p", facts=[_fact("f1")])
    s5_verify(_deps([_VerifyItem(id=0, confidence=0.9, clarity=0.8, relevance=0.7, rationale="solid")]), st)
    assert st.facts[0].status == FactStatus.VERIFIED and st.facts[0].confidence == 0.9
    assert st.facts[0].rationale == "solid"


def test_verify_unverified_below_theta():
    st = ArticleState(paper_ref="p", facts=[_fact("f1")])
    s5_verify(_deps([_VerifyItem(id=0, confidence=0.2, clarity=0.2, relevance=0.2)]), st)
    assert st.facts[0].status == FactStatus.UNVERIFIED


def test_verify_rel_floor_blocks_offdomain():
    st = ArticleState(paper_ref="p", facts=[_fact("f1")])
    s5_verify(_deps([_VerifyItem(id=0, confidence=1.0, clarity=1.0, relevance=0.3)]), st)
    assert st.facts[0].status == FactStatus.UNVERIFIED   # gate ок, но relevance < 0.4


def test_verify_skips_contested():
    st = ArticleState(paper_ref="p", facts=[_fact("f1", status=FactStatus.CONTESTED)])
    s5_verify(_deps([_VerifyItem(id=0, confidence=0.9, clarity=0.9, relevance=0.9)]), st)
    assert st.facts[0].status == FactStatus.CONTESTED
