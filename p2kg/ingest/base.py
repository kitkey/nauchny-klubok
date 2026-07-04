"""Роутер источников: выбирает адаптер по can_handle, возвращает Paper (или граф-фрагмент)."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SourceAdapter(Protocol):
    def can_handle(self, ref: str) -> bool: ...
    def load(self, ref: str, *, paper_ref: str | None = None): ...


def _adapters(use_layout: bool = False) -> list[SourceAdapter]:
    # импорт внутри — чтобы избежать тяжёлых зависимостей при импорте пакета
    from .arxiv import ArxivAdapter
    if use_layout:
        from .pdf_layout import get_layout_adapter   # PP-DocLayout (torch/transformers, модель грузится 1 раз)
        return [ArxivAdapter(), get_layout_adapter()]
    from .pdf import PdfAdapter
    return [ArxivAdapter(), PdfAdapter()]   # arxiv-id раньше, чем pdf-путь


def ingest(ref: str, *, paper_ref: str | None = None, use_layout: bool = False, **opts):
    for ad in _adapters(use_layout):
        if ad.can_handle(ref):
            return ad.load(ref, paper_ref=paper_ref, **opts)
    raise ValueError(f"no adapter for ref: {ref!r}")
