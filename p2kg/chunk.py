"""S1 · chunk — Paper -> list[Chunk]. Под капотом langchain RecursiveCharacterTextSplitter.

Чанкуем ВНУТРИ секций; атомарные единицы (таблицы/фигуры) — отдельными целыми чанками;
бьём только промежутки. overlap в токенах.

ВАЖНО: chunk.span — BEST-EFFORT (langchain нормализует whitespace при склейке, точное
raw_text[span]==text не гарантируется). Точные офсеты — на уровне ФАКТОВ (find_anchor в S3),
chunk.span нужен лишь для грубой навигации/провенанса.
"""
from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .ingest.pdf import count_tokens
from .schema import Chunk, Paper, Section, Span


def _splitter(token_budget: int, overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=token_budget, chunk_overlap=overlap, length_function=count_tokens,
    )


def _atomic_spans(paper: Paper) -> list[tuple[Span, str]]:
    out: list[tuple[Span, str]] = []
    for t in paper.parsed.tables:
        if t.span is not None:
            out.append((t.span, t.tbl_id))
    for f in paper.parsed.figures:
        if f.span is not None:
            out.append((f.span, f.fig_id))
    out.sort(key=lambda x: x[0].start)
    return out


def _regions(sec_span: Span, atomic: list[tuple[Span, str]]) -> list[tuple[Span, bool, str | None]]:
    """Чередующиеся (промежуток, атомарная единица) по порядку внутри секции."""
    inside = []
    for sp, ref in atomic:
        s = max(sp.start, sec_span.start)
        e = min(sp.end, sec_span.end)
        if s < e:
            inside.append((s, e, ref))
    inside.sort()
    out: list[tuple[Span, bool, str | None]] = []
    cur = sec_span.start
    for s, e, ref in inside:
        s = max(s, cur)
        if s > cur:
            out.append((Span(start=cur, end=s, page=sec_span.page), False, None))
        if e > s:
            out.append((Span(start=s, end=e, page=sec_span.page), True, ref))
        cur = max(cur, e)
    if cur < sec_span.end:
        out.append((Span(start=cur, end=sec_span.end, page=sec_span.page), False, None))
    return out


def chunk_paper(paper: Paper, *, token_budget: int = 1200, overlap: int = 120) -> list[Chunk]:
    splitter = _splitter(token_budget, overlap)
    atomic = _atomic_spans(paper)
    has_secs = bool(paper.parsed.sections)
    secs = paper.parsed.sections or [
        Section(sec_id="sec-0", name="body", span=Span(start=0, end=len(paper.raw_text), page=None))
    ]
    chunks: list[Chunk] = []
    idx = 0
    for sec in secs:
        sec_id = sec.sec_id if has_secs else None
        for region, is_atomic, ref in _regions(sec.span, atomic):
            text = paper.raw_text[region.start:region.end]
            if is_atomic:
                chunks.append(Chunk(
                    chunk_id=f"chunk-{idx}", paper_ref=paper.paper_ref, index=idx,
                    span=region, text=text, sec_id=sec_id, role_hint=sec.role_hint,
                    atomic_ref=ref, token_count=count_tokens(text),
                ))
                idx += 1
                continue
            if not text.strip():
                continue
            cursor = 0
            for di, piece in enumerate(splitter.split_text(text)):
                if not piece.strip():
                    continue
                pos = text.find(piece, cursor)        # точное вхождение от курсора
                if pos < 0:
                    pos = text.find(piece)            # запасной поиск с начала
                if pos < 0:
                    pos = min(cursor, max(0, len(text) - 1))  # whitespace-нормализация — грубо
                start_abs = region.start + pos
                end_abs = min(region.end, start_abs + len(piece))
                if end_abs <= start_abs:
                    continue
                chunks.append(Chunk(
                    chunk_id=f"chunk-{idx}", paper_ref=paper.paper_ref, index=idx,
                    span=Span(start=start_abs, end=end_abs, page=region.page),
                    text=piece, sec_id=sec_id, role_hint=sec.role_hint, atomic_ref=None,
                    token_count=count_tokens(piece), overlap_prev=overlap if di > 0 else 0,
                ))
                idx += 1
                cursor = pos + 1
    return chunks
