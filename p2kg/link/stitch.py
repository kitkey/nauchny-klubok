"""S4: сшивка claim/hypothesis -> evidence (SUPPORTED_BY).

На каждый тезис — ОДИН батч-вызов со всеми кандидатами-измерениями; тезисы гоняются параллельно.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..concurrency import pmap
from ..llm.steps import run_step
from ..schema import Edge, EdgeType, FrameType


class _StitchOut(BaseModel):
    supported_ids: list[int] = Field(default_factory=list)


def _stitch(deps, st) -> None:
    ent_of: dict[str, set] = {}
    for ed in st.edges:
        ent_of.setdefault(ed.src, set()).add(ed.dst)
    claims = [f for f in st.facts if f.frame_type in (FrameType.CLAIM_FACT, FrameType.HYPOTHESIS_FACT)]
    results = [f for f in st.facts if f.frame_type == FrameType.MATERIAL_MEASUREMENT]

    def for_claim(c):
        ce = ent_of.get(c.uuid, set())
        if not ce:
            return []
        cands = [(j, r) for j, r in enumerate(results) if ce & ent_of.get(r.uuid, set())]
        if not cands:
            return []
        evidence = [{"id": j, "text": (r.statement or "")} for j, r in cands]
        out = run_step(deps, "link.stitch", schema=_StitchOut,
                       claim=(c.statement or ""), evidence=evidence)
        sup = set(out.supported_ids) if out else set()
        return [(c.uuid, results[j].uuid, c.provenance) for j, _ in cands if j in sup]

    for pairs in pmap(for_claim, claims, deps.cfg.workers):
        for src, dst, prov in (pairs or []):
            st.edges.append(Edge(src=src, dst=dst, type=EdgeType.SUPPORTED_BY, provenance=prov))
