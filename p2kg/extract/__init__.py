"""S3 · extract — чанки -> локальные Entity/Fact/Edge (n-арный EDC)."""
from __future__ import annotations

from ..concurrency import pmap
from ..context import ArticleState, Deps
from ..schema import Role
from ._common import FRAME_SLOTS, LocalGraph, _FrameOut, _OpenEdgeOut
from .table import _extract_table
from .text import _extract_text

__all__ = ["s3_extract", "LocalGraph", "_FrameOut", "_OpenEdgeOut", "FRAME_SLOTS"]


def s3_extract(deps: Deps, st: ArticleState) -> ArticleState:
    if st.paper is None:
        st.stage_status["s3_extract"] = "skip"
        return st
    chunks = [ch for ch in st.chunks if ch.role_hint != Role.OTHER]  # references/ack пропускаем

    def _one(ch):
        try:
            return _extract_table(deps, ch, st.paper) if ch.atomic_ref else _extract_text(deps, ch, st.units, st.paper)
        except Exception:
            return None   # кривой чанк (IncompleteOutput / зацикливание модели / парсинг) не роняет весь документ

    for lg in pmap(_one, chunks, deps.cfg.workers):
        if not lg:
            continue
        st.entities += lg.entities
        st.facts += lg.facts
        st.edges += lg.edges
    st.stage_status["s3_extract"] = "ok"
    return st
