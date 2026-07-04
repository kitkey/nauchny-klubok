"""S4: канонизация open-предикатов -> ядро EdgeType (или оставить OPEN)."""
from __future__ import annotations

from pydantic import BaseModel

from ..llm.steps import run_step
from ..provenance import context_snippet
from ..schema import EdgeType


class _RelVerdict(BaseModel):
    core_type: str | None = None   # имя EdgeType из ядра, либо None (оставить OPEN)


_CORE = {t.value for t in EdgeType} - {"OPEN"}


def _canon_predicates(deps, st) -> None:
    raw = st.paper.raw_text if getattr(st, "paper", None) else ""
    for ed in st.edges:
        if ed.type != EdgeType.OPEN:
            continue
        v = run_step(deps, "link.canon_rel", schema=_RelVerdict,
                     rel=(ed.rel or ""), rel_def=(ed.rel_def or ""),
                     example=context_snippet(raw, ed.provenance))
        if v and v.core_type and v.core_type in _CORE:
            ed.type = EdgeType(v.core_type)
            ed.rel = None
            ed.rel_def = None
