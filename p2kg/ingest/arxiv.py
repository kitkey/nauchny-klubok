"""ArxivAdapter (S0) — arxiv id/URL -> Paper из ar5iv HTML/LaTeX (структура размечена).

В M2 реализован только can_handle (роутинг). Сам fetch — сетевой, подключается в M3+.
"""
from __future__ import annotations

import re

_ARXIV_RE = re.compile(r"(?i)^(?:arxiv:)?\d{4}\.\d{4,5}(?:v\d+)?$")
_ARXIV_URL_RE = re.compile(r"(?i)arxiv\.org/(?:abs|html|pdf)/\d{4}\.\d{4,5}")


class ArxivAdapter:
    def can_handle(self, ref: str) -> bool:
        s = str(ref).strip()
        return bool(_ARXIV_RE.match(s) or _ARXIV_URL_RE.search(s))

    def load(self, ref: str, *, paper_ref: str | None = None, **opts):
        raise NotImplementedError("ArxivAdapter (ar5iv fetch) — сетевой; подключается в M3+")
