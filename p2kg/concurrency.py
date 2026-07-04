"""Параллельный map для I/O-bound LLM-вызовов.

Вызовы к OpenRouter — сетевые (GIL отпускается), поэтому пул потоков даёт near-linear ускорение.
pmap сохраняет порядок; упавший элемент -> None (ошибка уже залогирована в run_step через tracer).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable


def _safe(fn: Callable, x):
    try:
        return fn(x)
    except Exception:
        return None


def pmap(fn: Callable, items: Iterable, workers: int = 8) -> list:
    items = list(items)
    if not items:
        return []
    if workers <= 1 or len(items) == 1:
        return [_safe(fn, x) for x in items]
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as ex:
        return list(ex.map(lambda x: _safe(fn, x), items))
