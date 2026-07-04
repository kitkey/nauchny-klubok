"""Embedder — для дедупа/канонизации (S4) и вектор-индекса.

HashEmbedder — детерминированный оффлайн-эмбеддер (тесты/без сети; НЕ семантический).
STEmbedder — реальный (sentence-transformers, lazy import).
"""
from __future__ import annotations

import hashlib
import math


def cosine(a: list[float], b: list[float]) -> float:
    s = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return s / (na * nb)


class HashEmbedder:
    dim = 64

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def _vec(self, t: str) -> list[float]:
        h = hashlib.sha256(t.strip().lower().encode("utf-8")).digest()  # 32 байта
        raw = (h * 2)[: self.dim]
        v = [b / 255.0 for b in raw]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]


class STEmbedder:
    def __init__(self, model: str) -> None:
        from sentence_transformers import SentenceTransformer
        self._m = SentenceTransformer(model)

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, vec)) for vec in self._m.encode(list(texts))]


class OpenRouterEmbedder:
    """Эмбеддинги через OpenRouter /embeddings (OpenAI-совместимый). По умолчанию intfloat/e5-base-v2.

    e5 ждёт префикс "query:"/"passage:"; для симметричного сравнения имён сущностей используем "query:".
    """

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str | None = None, model: str = "intfloat/e5-base-v2",
                 base_url: str | None = None) -> None:
        import os
        from openai import OpenAI
        self.model = model
        self._cli = OpenAI(api_key=api_key or os.environ["OPENROUTER_API_KEY"],
                           base_url=base_url or self.BASE_URL)

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import time
        last: Exception | None = None
        for attempt in range(3):   # эмбеддер под нагрузкой иногда отдаёт пусто -> ретрай с backoff
            try:
                resp = self._cli.embeddings.create(model=self.model,
                                                   input=[f"query: {t}" for t in texts])
                if resp.data and len(resp.data) == len(texts):
                    return [d.embedding for d in resp.data]
                last = ValueError("No embedding data received")
            except Exception as e:   # noqa: BLE001
                last = e
            time.sleep(1.5 * (attempt + 1))
        raise last or ValueError("No embedding data received")
