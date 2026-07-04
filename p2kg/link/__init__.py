"""S4 · link — внутри-статейное слияние: дедуп + канон предикатов + дедуп фактов + сшивка."""
from __future__ import annotations

from ..context import ArticleState, Deps
from .canon import _canon_predicates
from .dedup import _dedup_entities, _dedup_facts
from .resolve import _resolve_entities
from .stitch import _stitch

__all__ = ["s4_link"]


def s4_link(deps: Deps, st: ArticleState) -> ArticleState:
    # каждый под-шаг в try/except: сбой линковки (напр. IncompleteOutput на большом батче) НЕ должен
    # ронять весь док и терять уже извлечённые факты — они всё равно попадут в persist
    resolve = _dedup_entities if getattr(deps.cfg, "resolve_mode", "llm") == "embed" else _resolve_entities
    for step in (resolve, _canon_predicates, _dedup_facts, _stitch):
        try:
            step(deps, st)
        except Exception:
            pass
    st.stage_status["s4_link"] = "ok"
    return st
