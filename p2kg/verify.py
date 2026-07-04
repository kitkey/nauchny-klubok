"""S5 · verify — БАТЧ-грунт-чек по источнику + многомерный gate (+ пол по relevance) -> статус.

Факты бьются на батчи (cfg.verify_batch), батчи гоняются параллельно (cfg.workers).
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from .concurrency import pmap
from .context import ArticleState, Deps
from .llm.steps import run_step
from .provenance import context_snippet
from .schema import FactStatus

_WORD = re.compile(r"[А-Яа-яЁёA-Za-z0-9]{4,}")


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


# ---------------- ленивая верификация в момент ответа ----------------
def _window(raw: str, statement: str, win: int = 700) -> str:
    """Окно из raw_text вокруг наибольшей плотности слов factа (фолбэк, если нет units)."""
    if not raw or not statement:
        return (raw or "")[:1200]
    toks = [t.lower() for t in _WORD.findall(statement)][:14]
    low = raw.lower()
    pos = [p for p in (low.find(t) for t in toks) if p >= 0]
    if not pos:
        return raw[:1200]
    best_p, best_hits = pos[0], -1
    for p in pos:
        hits = sum(1 for q in pos if p - win // 2 <= q <= p + win // 2)
        if hits > best_hits:
            best_hits, best_p = hits, p
    return raw[max(0, best_p - win // 2): best_p + win // 2]


def _source_snippet(deps: Deps, paper_ref: str, statement: str, cache: dict) -> str:
    """Источник для проверки факта: лучший юнит(ы) статьи из Mongo (осмысленный пассаж),
    фолбэк — окно из raw_text. Факты и их provenance-оффсеты в Mongo не лежат, но units — да."""
    docs = getattr(deps, "docs", None)
    if docs is None or not paper_ref:
        return ""
    if paper_ref not in cache:
        try:
            cache[paper_ref] = {"units": docs.get_units(paper_ref) or []}
        except Exception:
            cache[paper_ref] = {"units": []}
    units = cache[paper_ref]["units"]
    toks = set(t.lower() for t in _WORD.findall(statement or ""))
    if units and toks:
        scored = sorted(units, key=lambda u: len(toks & set(t.lower() for t in _WORD.findall(getattr(u, "text", "") or ""))), reverse=True)
        top = [getattr(u, "text", "") or "" for u in scored[:2]
               if toks & set(t.lower() for t in _WORD.findall(getattr(u, "text", "") or ""))]
        if top:
            return "\n---\n".join(top)[:1400]
    # фолбэк: окно из raw_text
    if "raw" not in cache[paper_ref]:
        p = None
        try:
            p = docs.get_paper(paper_ref)
        except Exception:
            pass
        cache[paper_ref]["raw"] = (getattr(p, "raw_text", "") or "") if p else ""
    return _window(cache[paper_ref]["raw"], statement)


def verify_on_read(deps: Deps, evidence) -> int:
    """Ленивая верификация фактов, попавших в ответ: проверяем ТОЛЬКО ещё не проверявшиеся,
    статус пишем в граф (флаг v_checked) — при следующих запросах не гоняем повторно.
    Мутирует evidence[i].status для подтверждённых. Возвращает число verified."""
    graph = getattr(deps, "graph", None)
    if graph is None or not hasattr(graph, "facts_needing_verification") or not hasattr(graph, "set_fact_verification"):
        return 0
    uuids = [e.uuid for e in evidence if getattr(e, "uuid", None)]
    if not uuids:
        return 0
    try:
        todo = graph.facts_needing_verification(uuids)
    except Exception:
        return 0
    if not todo:
        return 0
    todo = todo[:20]
    cache: dict = {}
    facts_in = [{"id": i, "statement": (t.get("statement") or ""),
                 "quantity": str(t.get("qraw")),
                 "source": _source_snippet(deps, t.get("paper_ref"), t.get("statement") or "", cache)}
                for i, t in enumerate(todo)]
    try:
        out = run_step(deps, "verify.check", schema=list[_VerifyItem], facts=facts_in) or []
    except Exception:
        return 0
    verdicts = {v.id: v for v in out}
    rows, ok_uuids = [], set()
    for i, t in enumerate(todo):
        v = verdicts.get(i)
        if not v:
            continue
        gate = (v.confidence + v.clarity + v.relevance) / 3
        ok = gate >= deps.cfg.verify_theta and v.relevance >= deps.cfg.verify_rel_floor
        if ok:
            ok_uuids.add(t["uuid"])
        rows.append({"uuid": t["uuid"],
                     "status": FactStatus.VERIFIED.value if ok else FactStatus.UNVERIFIED.value,
                     "conf": round(float(gate), 3), "rationale": (v.rationale or "")[:400]})
    if rows:
        try:
            graph.set_fact_verification(rows)
        except Exception:
            pass
    for e in evidence:
        if getattr(e, "uuid", None) in ok_uuids:
            e.status = FactStatus.VERIFIED.value
    return len(ok_uuids)
