"""S5 · verify — БАТЧ-грунт-чек по источнику + многомерный gate (+ пол по relevance) -> статус.

Факты бьются на батчи (cfg.verify_batch), батчи гоняются параллельно (cfg.workers).
"""
from __future__ import annotations

from pydantic import BaseModel

from .concurrency import pmap
from .context import ArticleState, Deps
from .llm.steps import run_step
from .provenance import context_snippet
from .schema import FactStatus


class _VerifyItem(BaseModel):
    id: int
    confidence: float = 0.0
    clarity: float = 0.0
    relevance: float = 0.0
    rationale: str = ""


def s5_verify(deps: Deps, st: ArticleState) -> ArticleState:
    if getattr(deps.cfg, "skip_verify", False):
        st.stage_status["s5_verify"] = "skip"   # bulk: не верифицируем массово, факты остаются unverified
        return st
    raw = st.paper.raw_text if getattr(st, "paper", None) else ""
    # табличные измерения доверяем (точный provenance из ячейки) -> авто-verified, БЕЗ LLM-вызова
    for f in st.facts:
        if f.source == "table" and f.status != FactStatus.CONTESTED:
            f.status = FactStatus.VERIFIED
            f.confidence = f.clarity = f.relevance = 1.0
            f.rationale = "табличное измерение: provenance из ячейки таблицы, авто-верифицировано"
    todo = [f for f in st.facts if f.status != FactStatus.CONTESTED and f.source != "table"]
    bs = max(1, deps.cfg.verify_batch)
    batches = [todo[i:i + bs] for i in range(0, len(todo), bs)]

    def run_batch(batch):
        facts_in = [{"id": i, "statement": (f.statement or ""),
                     "quantity": str(f.quantity.model_dump() if f.quantity else None),
                     "source": context_snippet(raw, f.provenance)} for i, f in enumerate(batch)]
        out = run_step(deps, "verify.check", schema=list[_VerifyItem], facts=facts_in) or []
        return {v.id: v for v in out}

    for batch, verdicts in zip(batches, pmap(run_batch, batches, deps.cfg.workers)):
        if not verdicts:
            continue
        for i, f in enumerate(batch):
            v = verdicts.get(i)
            if not v:
                continue
            f.confidence, f.clarity, f.relevance, f.rationale = v.confidence, v.clarity, v.relevance, v.rationale
            gate = (v.confidence + v.clarity + v.relevance) / 3
            ok = gate >= deps.cfg.verify_theta and v.relevance >= deps.cfg.verify_rel_floor
            f.status = FactStatus.VERIFIED if ok else FactStatus.UNVERIFIED
    st.stage_status["s5_verify"] = "ok"
    return st
