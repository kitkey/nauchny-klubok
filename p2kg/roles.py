"""S2 · roles — list[Chunk] -> list[Unit]. Первый LLM-этап.

1 вызов/чанк: модель делит чанк на пассажи и метит роль (закрытая таксономия), отдаёт якоря —
код привязывает к raw_text через find_anchor. Атомарный чанк (таблица/фигура) -> один Unit.
"""
from __future__ import annotations

from pydantic import BaseModel

from .concurrency import pmap
from .context import ArticleState, Deps
from .llm.steps import run_step
from .provenance import find_anchor, slice_span
from .schema import Chunk, Paper, Role, Unit

_ROLES = [r.value for r in Role]


class _PassageTag(BaseModel):
    anchor: str
    role: Role
    role_confidence: float = 1.0


def _tag_chunk(deps: Deps, chunk: Chunk, paper: Paper) -> list[Unit]:
    # атомарный чанк (таблица/фигура) — целиком один Unit, роль на весь чанк (обычно result)
    if chunk.atomic_ref is not None:
        return [Unit(unit_id=f"{chunk.chunk_id}-u0", chunk_id=chunk.chunk_id,
                     paper_ref=chunk.paper_ref, span=chunk.span, text=chunk.text,
                     role=Role.RESULT, role_confidence=0.5)]

    tags = run_step(deps, "roles.tag", schema=list[_PassageTag],
                    chunk_text=chunk.text, roles=_ROLES,
                    hint=(chunk.role_hint.value if chunk.role_hint else "неизвестно")) or []
    units: list[Unit] = []
    for i, tag in enumerate(tags):
        sp = find_anchor(paper.raw_text, tag.anchor, search_from=chunk.span.start)
        if sp is None:
            span, text = chunk.span, chunk.text       # якорь не нашёлся -> весь чанк
        else:
            span, text = sp, slice_span(paper.raw_text, sp)
        units.append(Unit(unit_id=f"{chunk.chunk_id}-u{i}", chunk_id=chunk.chunk_id,
                          paper_ref=chunk.paper_ref, span=span, text=text,
                          role=tag.role, role_confidence=tag.role_confidence))
    if not units:                                     # ничего не разметилось -> один Unit на чанк
        units.append(Unit(unit_id=f"{chunk.chunk_id}-u0", chunk_id=chunk.chunk_id,
                          paper_ref=chunk.paper_ref, span=chunk.span, text=chunk.text,
                          role=Role.OTHER, role_confidence=0.0))
    return units


def s2_roles(deps: Deps, st: ArticleState) -> ArticleState:
    if st.paper is None or getattr(deps.cfg, "skip_roles", False):
        st.stage_status["s2_roles"] = "skip"   # bulk: роли графу не нужны (extract берёт role_hint секции)
        return st
    lists = pmap(lambda ch: _tag_chunk(deps, ch, st.paper), st.chunks, deps.cfg.workers)
    st.units = [u for lst in lists if lst for u in lst]
    st.stage_status["s2_roles"] = "ok"
    return st


class _SectionRole(BaseModel):
    title: str
    role: Role


def label_sections(deps: Deps, paper: Paper) -> None:
    """LLM-классификация секций, которым словарь не проставил role_hint. Мутирует paper.parsed.sections.

    Секций немного (после layout ~9–14), поэтому 1 батч-вызов на статью — дёшево.
    """
    if paper is None:
        return
    todo = [s for s in paper.parsed.sections if s.role_hint is None and s.name and s.name != "body"]
    if not todo:
        return
    out = run_step(deps, "roles.section", schema=list[_SectionRole],
                   titles=[s.name for s in todo], roles=_ROLES) or []
    by_title = {r.title.strip().lower(): r.role for r in out}
    for s in todo:
        r = by_title.get(s.name.strip().lower())
        if r is not None:
            s.role_hint = r
