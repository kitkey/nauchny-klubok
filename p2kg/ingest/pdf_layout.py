"""S0-v2: парс PDF через layout-модель PP-DocLayoutV3 (transformers, RT-DETR + reading order).

Рендерим страницы PyMuPDF -> картинки -> детектор даёт регионы (title/text/table/figure/...)
в порядке чтения. Берём текст PyMuPDF внутри title/text/table-регионов, а figure/formula/header/
footer ВЫКИДЫВАЕМ -> чистый ParsedDoc без мусора и пере-сегментации (замена эвристике).

torch/transformers/fitz/PIL грузятся лениво (внутри методов), чтобы импорт модуля был лёгким.
"""
from __future__ import annotations

import functools
import os
import threading

from ..provenance import text_hash
from ..schema import Paper, ParsedDoc, ParseMeta, Section, Span, Table
from .pdf import count_tokens, detect_lang, role_hint_from_heading

DEFAULT_LAYOUT_MODEL = os.environ.get("P2KG_LAYOUT_MODEL", "PaddlePaddle/PP-DocLayoutV3_safetensors")

_DROP_KW = ("figure", "image", "chart", "formula", "equation", "header", "footer",
            "number", "seal", "stamp", "watermark", "aside")

_INFER_LOCK = threading.Lock()   # сериализуем GPU-инференс при параллельной обработке статей


def _categorize(label: str) -> str:
    """RT-DETR-метка -> наша категория: 'title' | 'table' | 'text' | 'drop'."""
    s = label.lower()
    if "table" in s and "title" not in s and "caption" not in s:
        return "table"
    if "title" in s and not any(k in s for k in ("table", "figure", "chart", "image")):
        return "title"
    if any(k in s for k in _DROP_KW):
        return "drop"
    return "text"   # text / paragraph / abstract / reference / content / list


def _assemble(regions: list[tuple[str, str]]) -> tuple[str, ParsedDoc]:
    """regions = [(category, text), ...] в порядке чтения (drop уже отфильтрованы) -> (raw_text, ParsedDoc).

    Секция покрывает ТЕЛО — от своего заголовка до следующего заголовка (не только сам тайтл),
    иначе chunk_paper нарежет чанки-огрызки из одних заголовков.
    """
    parts: list[str] = []
    recs: list[tuple[str, int, int, str]] = []   # (cat, start, end, text)
    cur = 0
    for cat, txt in regions:
        txt = (txt or "").strip()
        if not txt:
            continue
        start = cur
        parts.append(txt)
        cur += len(txt) + 1   # +1 за "\n"
        recs.append((cat, start, start + len(txt), txt))
    raw = "\n".join(parts)
    total = len(raw)

    tables = [Table(tbl_id=f"tbl-{j}", caption=r[3][:120], span=Span(start=r[1], end=r[2]))
              for j, r in enumerate(t for t in recs if t[0] == "table")]

    title_pos = [i for i, r in enumerate(recs) if r[0] == "title"]
    sections: list[Section] = []
    if not title_pos:
        sections = [Section(sec_id="sec-0", name="body", role_hint=None,
                            span=Span(start=0, end=total))]
        return raw, ParsedDoc(sections=sections, tables=tables, figures=[])

    if title_pos[0] > 0:   # текст до первого заголовка
        sections.append(Section(sec_id="sec-0", name="frontmatter", role_hint=None,
                                span=Span(start=0, end=recs[title_pos[0]][1])))
    for k, ti in enumerate(title_pos):
        _, s, _, txt = recs[ti]
        sec_end = recs[title_pos[k + 1]][1] if k + 1 < len(title_pos) else total
        sections.append(Section(sec_id=f"sec-{len(sections)}", name=" ".join(txt.split())[:80],
                                role_hint=role_hint_from_heading(txt),
                                span=Span(start=s, end=sec_end)))
    return raw, ParsedDoc(sections=sections, tables=tables, figures=[])


def _ref_from(ref: str) -> str:
    return os.path.splitext(os.path.basename(str(ref)))[0]


_ADAPTER_LOCK = threading.Lock()


@functools.lru_cache(maxsize=1)
def _cached_adapter() -> "PdfLayoutAdapter":
    return PdfLayoutAdapter()


def get_layout_adapter() -> "PdfLayoutAdapter":
    """Кэш: модель грузится один раз на процесс. Лок сериализует тяжёлую первую загрузку
    (иначе при параллельных статьях гонка `from transformers import ...`)."""
    with _ADAPTER_LOCK:
        return _cached_adapter()


class PdfLayoutAdapter:
    def __init__(self, model_id: str = DEFAULT_LAYOUT_MODEL,
                 device: str | None = None, dpi: int = 200) -> None:
        import torch
        from transformers import AutoImageProcessor, AutoModelForObjectDetection
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.proc = AutoImageProcessor.from_pretrained(model_id)
        self.model = AutoModelForObjectDetection.from_pretrained(model_id).to(self.device).eval()
        self.dpi = dpi

    def can_handle(self, ref: str) -> bool:
        return str(ref).lower().endswith(".pdf")

    def _detect(self, pil_img) -> list[tuple[str, tuple[float, float, float, float]]]:
        """-> [(label, (x0,y0,x1,y1))] в порядке чтения."""
        import torch
        with _INFER_LOCK:
            inputs = self.proc(images=pil_img, return_tensors="pt").to(self.device)
            with torch.no_grad():
                out = self.model(**inputs)
            res = self.proc.post_process_object_detection(
                out, target_sizes=[pil_img.size[::-1]], threshold=0.5)[0]
            id2label = self.model.config.id2label
            return [(id2label[int(l)], tuple(map(float, b)))
                    for l, b in zip(res["labels"], res["boxes"])]

    def load(self, ref: str, *, paper_ref: str | None = None):
        import fitz
        from PIL import Image
        doc = fitz.open(ref)
        regions: list[tuple[str, str]] = []
        for page in doc:
            pm = page.get_pixmap(dpi=self.dpi)
            img = Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
            scale = page.rect.width / pm.width
            for label, bbox in self._detect(img):
                cat = _categorize(label)
                if cat == "drop":
                    continue
                rect = fitz.Rect([c * scale for c in bbox])
                txt = page.get_textbox(rect).strip()
                if txt:
                    regions.append((cat, txt))
        n_pages = doc.page_count
        doc.close()
        raw, parsed = _assemble(regions)
        meta = ParseMeta(parser="pp-doclayout-v3", lang=detect_lang(raw),
                         n_pages=n_pages, n_chars=len(raw), n_tokens=count_tokens(raw),
                         structure_reliable=len(parsed.sections) >= 2)
        return Paper(paper_ref=(paper_ref or _ref_from(ref)), source_pdf=str(ref),
                     raw_text=raw, text_hash=text_hash(raw),
                     title=(parsed.sections[0].name if parsed.sections else ""),
                     parse_meta=meta, parsed=parsed)
