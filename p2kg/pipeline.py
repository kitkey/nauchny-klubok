"""Оркестрация: source -> Paper (S0) -> S1..S5 -> persist. Этапы = чистые функции (Deps, State)."""
from __future__ import annotations

import time

from .chunk import chunk_paper
from .context import ArticleState, Deps
from .extract import s3_extract
from .ingest import ingest
from .link import s4_link
from .persist import persist
from .roles import label_sections, s2_roles
from .verify import s5_verify


def s1_chunk(deps: Deps, st: ArticleState) -> ArticleState:
    if st.paper is None:
        st.stage_status["s1_chunk"] = "skip"
        return st
    st.chunks = chunk_paper(st.paper, token_budget=deps.cfg.chunk_token_budget,
                            overlap=deps.cfg.chunk_overlap)
    st.stage_status["s1_chunk"] = "ok"
    return st


STAGES = [s1_chunk, s2_roles, s3_extract, s4_link, s5_verify, persist]


def process_source(deps: Deps, ref: str, *, paper_ref: str | None = None) -> ArticleState:
    """Полный прогон по одной статье: S0 ingest -> S1..S5 -> persist (с трассировкой)."""
    tr = deps.tracer
    t0 = time.perf_counter()
    paper = ingest(ref, paper_ref=paper_ref, use_layout=deps.cfg.use_layout)   # S0
    st = ArticleState(paper_ref=paper.paper_ref, paper=paper)
    st.stage_status["s0_ingest"] = "ok"
    tr.start_paper(st.paper_ref)
    tr.log_stage(st.paper_ref, "s0_ingest", time.perf_counter() - t0)
    if deps.cfg.use_llm_section_roles:           # S0b: классификация секций без role_hint
        with tr.stage(st.paper_ref, "s0b_label_sections"):
            label_sections(deps, st.paper)
        st.stage_status["s0b_label_sections"] = "ok"
    for stage in STAGES:
        with tr.stage(st.paper_ref, stage.__name__):
            st = stage(deps, st)
    tr.end_paper(st.paper_ref, chunks=len(st.chunks), units=len(st.units),
                 entities=len(st.entities), facts=len(st.facts), edges=len(st.edges),
                 status=dict(st.stage_status))
    return st
