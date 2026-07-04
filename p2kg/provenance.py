"""Provenance: якорь -> Span (устойчиво к whitespace), хэш текста, проверка span.

Инвариант: модель НЕ переписывает текст — она возвращает «якорь» (первые слова
фрагмента), а код находит его в иммутабельном raw_text и отдаёт Span.
"""
from __future__ import annotations

import hashlib
import re

from .schema import Span


def text_hash(raw_text: str) -> str:
    """sha1 от текста — связывает провенансы с конкретным снапшотом raw_text."""
    return hashlib.sha1(raw_text.encode("utf-8")).hexdigest()


def slice_span(raw_text: str, span: Span) -> str:
    """Подстрока оригинала по span — единая точка истины."""
    return raw_text[span.start:span.end]


def _anchor_regex(anchor: str) -> re.Pattern[str]:
    """Каждый пробел нормализованного якоря -> \\s+ ; остальное экранируем."""
    tokens = anchor.split()
    return re.compile(r"\s+".join(re.escape(t) for t in tokens))


def find_anchor(
    raw_text: str,
    anchor: str,
    *,
    search_from: int = 0,
    end_anchor: str | None = None,
) -> Span | None:
    """Найти фрагмент по начальному (и опц. конечному) якорю. None — если не нашли.

    Устойчиво к различию whitespace (перенос/двойные пробелы в PDF). Не «угадывает»:
    нет совпадения -> None, пусть верхний уровень понизит confidence/выкинет факт.
    """
    if not anchor.strip():
        return None
    m = _anchor_regex(anchor).search(raw_text, search_from)
    if m is None:
        return None
    start, end = m.start(), m.end()
    if end_anchor and end_anchor.strip():
        m2 = _anchor_regex(end_anchor).search(raw_text, m.end())
        if m2 is not None:
            end = m2.end()
    return Span(start=start, end=end)


def verify_span(raw_text: str, span: Span, expected_anchor: str | None = None) -> bool:
    """Проверить границы span и (опц.) что его текст начинается с expected_anchor."""
    if not (0 <= span.start < span.end <= len(raw_text)):
        return False
    if expected_anchor and expected_anchor.strip():
        seg = raw_text[span.start:span.end]
        return _anchor_regex(expected_anchor).match(seg) is not None
    return True


def context_snippet(raw_text: str, prov, *, window: int = 160, max_len: int = 600) -> str:
    """Текст вокруг провенанса (span ± window), не длиннее max_len — контекст для dedup/verify/canon.

    Кап max_len защищает от раздутого span (напр. anchor не нашёлся -> span на весь чанк).
    Возвращает "" если текста/спана нет (табличный loc или paper отсутствует в тестах).
    """
    loc = getattr(prov, "loc", None)
    span = getattr(loc, "span", None)
    if not raw_text or span is None:
        return ""
    start = max(0, span.start - window)
    end = min(len(raw_text), span.end + window)
    return raw_text[start:end][:max_len].strip()
