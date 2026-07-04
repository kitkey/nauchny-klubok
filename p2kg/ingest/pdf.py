"""PdfAdapter (S0) — сырой PDF -> Paper. Детерминированно (PyMuPDF); LLM только на фолбэке секций.

Поток load: extract_text -> detect_sections_heuristic (или llm_segment при use_llm_structure) ->
detect_tables/figures/refs -> ParseMeta -> Paper. raw_text иммутабелен, офсеты — символьные.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

from ..provenance import text_hash
from ..schema import (
    Figure, Paper, ParsedDoc, ParseMeta, Ref, Role, Section, Span, Table,
)

PageMap = list[tuple[int, int, int]]   # (char_start, char_end, page)


@dataclass
class Extracted:
    raw_text: str
    page_map: PageMap
    parser: str
    ocr_used: bool
    lang: str | None


# --- утилиты -----------------------------------------------------------------

def count_tokens(text: str) -> int:
    """Грубая оценка токенов (~4 символа/токен)."""
    return max(1, len(text) // 4)


def detect_lang(text: str) -> str | None:
    sample = text[:4000]
    cyr = sum("Ѐ" <= c <= "ӿ" for c in sample)
    lat = sum("a" <= c.lower() <= "z" for c in sample)
    if cyr == 0 and lat == 0:
        return None
    return "ru" if cyr > lat else "en"


def needs_ocr(text: str, n_pages: int) -> bool:
    """Мало текста на страницу / низкая доля букв -> текст-слой не годен, нужен OCR."""
    if n_pages <= 0:
        return True
    per_page = len(text) / n_pages
    alpha_ratio = (sum(c.isalpha() for c in text) / len(text)) if text else 0.0
    return per_page < 100 or alpha_ratio < 0.5


def page_of(offset: int, page_map: PageMap) -> int | None:
    for s, e, p in page_map:
        if s <= offset < e:
            return p
    return None


# --- извлечение текста -------------------------------------------------------

def extract_text_pymupdf(pdf_path: str | Path) -> Extracted:
    doc = fitz.open(pdf_path)
    parts: list[str] = []
    page_map: PageMap = []
    cursor = 0
    for pno, page in enumerate(doc):
        t = page.get_text("text")
        start = cursor
        parts.append(t)
        cursor += len(t)
        page_map.append((start, cursor, pno))
    doc.close()
    raw = "".join(parts)
    return Extracted(raw, page_map, "pymupdf", False, detect_lang(raw))


def extract_text(pdf_path: str | Path, *, force_ocr: bool = False,
                 lang: str | None = None) -> Extracted:
    ex = extract_text_pymupdf(pdf_path)
    if force_ocr or needs_ocr(ex.raw_text, len(ex.page_map)):
        # OCR-путь (PaddleOCR) подключается позже; пока помечаем намерение.
        ex.ocr_used = True
    if lang:
        ex.lang = lang
    return ex


# --- структура ---------------------------------------------------------------

SECTION_ROLE_PRIORS: dict[str, Role] = {
    "abstract": Role.BACKGROUND, "introduction": Role.BACKGROUND, "related work": Role.BACKGROUND,
    "background": Role.BACKGROUND, "motivation": Role.BACKGROUND,
    "method": Role.METHOD, "methods": Role.METHOD, "methodology": Role.METHOD,
    "approach": Role.METHOD, "computational details": Role.METHOD,
    "experiments": Role.RESULT, "experimental setup": Role.RESULT, "results": Role.RESULT,
    "evaluation": Role.RESULT, "discussion": Role.COMPARISON, "limitations": Role.LIMITATION,
    "conclusion": Role.CLAIM, "conclusions": Role.CLAIM, "summary": Role.CLAIM,
    "future work": Role.FUTURE,
    # не-контент -> OTHER (пропускаем в S3)
    "references": Role.OTHER, "bibliography": Role.OTHER, "acknowledgments": Role.OTHER,
    "acknowledgements": Role.OTHER, "data availability": Role.OTHER,
    "code and data availability": Role.OTHER, "author contributions": Role.OTHER,
    "funding": Role.OTHER, "conflict of interest": Role.OTHER, "competing interests": Role.OTHER,
    "supplemental references": Role.OTHER, "supplementary references": Role.OTHER,
}

# ведущий номер секции: римский (I./IV)), арабский многоуровневый (2.3), буква (A.)
_NUM_PREFIX = re.compile(r"^(?:[ivxlcdm]+|\d+(?:\.\d+)*|[a-z])[.)]?\s+", re.IGNORECASE)


def _norm_heading(name: str) -> str:
    s = " ".join(name.split())          # схлопнуть \n и двойные пробелы
    s = _NUM_PREFIX.sub("", s)          # срезать ведущий номер "I." / "2.3" / "A."
    return s.strip().lower().rstrip(":")


def role_hint_from_heading(name: str) -> Role | None:
    norm = _norm_heading(name)
    if not norm:
        return None
    if norm in SECTION_ROLE_PRIORS:
        return SECTION_ROLE_PRIORS[norm]
    for key, role in SECTION_ROLE_PRIORS.items():   # подстрочно: "results and discussion" -> results
        if re.search(rf"\b{re.escape(key)}\b", norm):
            return role
    return None


def _is_heading(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 80:
        return False
    words = s.split()
    if len(words) > 12:
        return False
    if _norm_heading(s) in SECTION_ROLE_PRIORS:
        return True
    if re.match(r"^\d+(\.\d+)*\.?\s+\S", s):      # нумерованный заголовок "3.1 Foo"
        return True
    if s.isupper() and len(words) <= 8:           # ALLCAPS-заголовок
        return True
    return False


def _line_starts(raw_text: str) -> list[tuple[int, str]]:
    spans: list[tuple[int, str]] = []
    pos = 0
    for line in raw_text.split("\n"):
        spans.append((pos, line))
        pos += len(line) + 1
    return spans


def detect_sections_heuristic(raw_text: str, page_map: PageMap) -> tuple[list[Section], bool]:
    """Эвристика по заголовкам. -> (sections, structure_reliable). Секции стыкуются и покрывают док."""
    if not raw_text:
        return [], False
    heads = [(off, line) for off, line in _line_starts(raw_text) if _is_heading(line)]
    if not heads:
        body = Section(sec_id="sec-0", name="body", role_hint=None,
                       span=Span(start=0, end=len(raw_text), page=page_of(0, page_map)))
        return [body], False

    secs: list[Section] = []
    if heads[0][0] > 0:
        secs.append(Section(sec_id="sec-0", name="frontmatter", role_hint=None,
                            span=Span(start=0, end=heads[0][0], page=page_of(0, page_map))))
    for i, (off, line) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(raw_text)
        secs.append(Section(
            sec_id=f"sec-{len(secs)}", name=line.strip(),
            role_hint=role_hint_from_heading(line),
            span=Span(start=off, end=end, page=page_of(off, page_map)),
        ))
    return secs, len(heads) >= 3


def llm_segment(raw_text: str, page_map: PageMap) -> list[Section]:
    """Фолбэк секций через LLM (якоря границ -> split). Подключается в M3."""
    raise NotImplementedError("llm_segment подключается в M3 (LLM-этап)")


def detect_tables(raw_text: str, page_map: PageMap) -> list[Table]:
    out: list[Table] = []
    for i, m in enumerate(re.finditer(r"(?im)^\s*table\s+\d+", raw_text)):
        caption = raw_text[m.start():m.start() + 140].split("\n")[0].strip()
        out.append(Table(tbl_id=f"tbl-{i}", caption=caption,
                         span=Span(start=m.start(), end=m.end(), page=page_of(m.start(), page_map))))
    return out


def detect_figures(raw_text: str, page_map: PageMap) -> list[Figure]:
    out: list[Figure] = []
    for i, m in enumerate(re.finditer(r"(?im)^\s*(?:figure|fig\.?)\s+\d+", raw_text)):
        caption = raw_text[m.start():m.start() + 140].split("\n")[0].strip()
        out.append(Figure(fig_id=f"fig-{i}", caption=caption,
                          span=Span(start=m.start(), end=m.end(), page=page_of(m.start(), page_map))))
    return out


def detect_refs(raw_text: str) -> list[Ref]:
    m = re.search(r"(?im)^\s*references\s*$", raw_text)
    if not m:
        return []
    tail = raw_text[m.end():]
    refs: list[Ref] = []
    for line in (ln.strip() for ln in tail.split("\n")):
        if re.match(r"^\[?\d+\]?[.\)]?\s+\w", line):
            refs.append(Ref(ref_id=f"ref-{len(refs)}", raw=line[:300]))
    return refs


# --- адаптер -----------------------------------------------------------------

class PdfAdapter:
    def can_handle(self, ref: str) -> bool:
        return str(ref).lower().endswith(".pdf")

    def load(self, ref: str, *, paper_ref: str | None = None, force_ocr: bool = False,
             lang: str | None = None, use_llm_structure: bool = False) -> Paper:
        path = Path(ref)
        ex = extract_text(path, force_ocr=force_ocr, lang=lang)
        secs, reliable = detect_sections_heuristic(ex.raw_text, ex.page_map)
        if not reliable and use_llm_structure:
            secs = llm_segment(ex.raw_text, ex.page_map)
        tables = detect_tables(ex.raw_text, ex.page_map)
        figures = detect_figures(ex.raw_text, ex.page_map)
        refs = detect_refs(ex.raw_text)
        meta = ParseMeta(
            parser=ex.parser, ocr_used=ex.ocr_used, lang=ex.lang,
            n_pages=len(ex.page_map), n_chars=len(ex.raw_text),
            n_tokens=count_tokens(ex.raw_text), structure_reliable=reliable,
        )
        return Paper(
            paper_ref=paper_ref or path.stem,
            source_pdf=str(path),
            raw_text=ex.raw_text,
            text_hash=text_hash(ex.raw_text),
            parsed=ParsedDoc(sections=secs, tables=tables, figures=figures, refs=refs),
            parse_meta=meta,
        )
