"""S3: NL-определения для НОВЫХ (open) предикатов — для канонизации на S4.

В v1 не вызывается из основного пути (open_edges пока не материализуются). Готово к подключению,
когда добавим causal/hypothesis-рёбра.
"""
from __future__ import annotations

from ..llm.steps import run_step


def _define(deps, rels: list[dict]) -> dict[str, str]:
    """rels = [{'rel': str, 'example': str}] -> {rel: NL-определение} (для канонизации на S4)."""
    if not rels:
        return {}
    out = run_step(deps, "extract.define", schema=dict, rels=rels,
                   language_code=deps.cfg.output_language)
    return out or {}
