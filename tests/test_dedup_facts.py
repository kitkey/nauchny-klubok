from p2kg.config import Config
from p2kg.context import ArticleState, Deps
from p2kg.link.dedup import _FactDedupOut, _dedup_facts
from p2kg.llm.prompts import PromptManager
from p2kg.schema import (
    Edge, EdgeType, Fact, FactStatus, FrameType, Provenance, Quantity, Span, TextLoc,
)


class FakeLLM:
    def __init__(self, ret):
        self.ret = ret
        self.calls = 0

    def complete(self, user, *, system=None, model, schema=None, **kw):
        self.calls += 1
        return self.ret


def _deps(ret=None):
    return Deps(llm=FakeLLM(ret), embed=None, prompts=PromptManager(), cfg=Config(),
                graph=None, docs=None)


def _prov():
    return Provenance(paper_ref="p", loc=TextLoc(span=Span(start=0, end=1)))


def _mm(uuid, val):
    return Fact(uuid=uuid, frame_type=FrameType.MATERIAL_MEASUREMENT, paper_ref="p",
                statement=f"bandgap {val} eV", quantity=Quantity(value=val, unit="eV", operator="="),
                provenance=_prov())


def _edges(n, slots=("m", "p", "t", "c")):
    return [Edge(src=f"f{i}", dst=s, type=EdgeType.HAS_MATERIAL, provenance=_prov())
            for i in range(n) for s in slots]


def test_dedup_collapses_exact_dups_then_llm_contests():
    # 1.6 ПЕРВЫМ + 6×1.7 + 1.8: точный дедуп сам схлопнет 1.7 -> один; LLM решает конфликт
    vals = [1.6, 1.7, 1.7, 1.7, 1.7, 1.7, 1.7, 1.8]
    st = ArticleState(paper_ref="p", entities=[],
                      facts=[_mm(f"f{i}", v) for i, v in enumerate(vals)], edges=_edges(len(vals)))
    deps = _deps(_FactDedupOut(contradictions=[[0, 1, 2]]))   # reps=[1.6,1.7,1.8] -> все конфликт

    _dedup_facts(deps, st)

    assert sorted(f.quantity.value for f in st.facts) == [1.6, 1.7, 1.8]   # точные дубли 1.7 схлопнуты
    assert deps.llm.calls == 1                                             # LLM позван 1 раз на группу
    assert all(f.status == FactStatus.CONTESTED for f in st.facts)
    assert sum(1 for e in st.edges if e.type == EdgeType.CONTRADICTED_BY) == 2


def test_llm_merges_near_duplicates():
    # 1.70 и 1.7 — LLM считает дублями -> остаётся один, без конфликта
    st = ArticleState(paper_ref="p", entities=[],
                      facts=[_mm("f0", 1.70), _mm("f1", 1.7)], edges=_edges(2))
    deps = _deps(_FactDedupOut(duplicates=[[0, 1]]))

    _dedup_facts(deps, st)

    assert len(st.facts) == 1
    assert not any(e.type == EdgeType.CONTRADICTED_BY for e in st.edges)


def test_pure_duplicates_no_llm():
    # все одинаковые -> детерминированный дедуп, LLM НЕ зовётся
    st = ArticleState(paper_ref="p", entities=[],
                      facts=[_mm(f"f{i}", 1.7) for i in range(5)], edges=_edges(5))
    deps = _deps(_FactDedupOut())

    _dedup_facts(deps, st)

    assert len(st.facts) == 1 and deps.llm.calls == 0
