"""Config — пути, бюджеты, пороги, модели per-step, conn-стринги (значения из env)."""
from __future__ import annotations

import os

from pydantic import BaseModel, Field


class Config(BaseModel):
    models: dict[str, str] = Field(default_factory=dict)  # {"roles.tag": "<slug>", ...}
    embed_model: str = "intfloat/e5-base-v2"
    chunk_token_budget: int = 6000   # запас: у плотных доков вывод фреймов не превышает max_tokens (IncompleteOutput)
    chunk_overlap: int = 20
    workers: int = 8              # параллельные LLM-вызовы внутри стадии
    verify_batch: int = 25        # фактов на один verify-вызов
    relevance_threshold: float = 0.2
    verify_theta: float = 0.6
    verify_rel_floor: float = 0.4   # verified требует ещё и relevance >= floor (не пускать оффдомен)
    skip_roles: bool = False   # bulk: не гонять S2 roles (граф их не использует) — минус полный проход по тексту
    skip_verify: bool = False  # bulk: не гонять S5 verify (факты остаются unverified) — верифицируем лениво по запросу
    verify_on_read: bool = True  # ленивая верификация: факты, попавшие в ответ, проверяются 1 раз и статус кэшируется в граф
    resolve_mode: str = "llm"  # "llm" (LLM-кластеризация+иерархия) | "embed" (эмбеддинг-блокинг дедуп, дёшево/быстро)
    use_rudder: bool = False
    use_llm_structure: bool = False
    use_layout: bool = False   # S0-v2: PP-DocLayout вместо PyMuPDF-эвристики
    use_llm_section_roles: bool = True   # LLM-классификация секций без role_hint после словаря
    output_language: str = "en"          # язык генерируемых statement/определений (en/ru/…)
    neo4j_uri: str = "bolt://localhost:7687"
    mongo_uri: str = "mongodb://localhost:27017"
    pdf_dir: str = "data/raw"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            neo4j_uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            mongo_uri=os.environ.get("MONGO_URI", "mongodb://localhost:27017"),
            pdf_dir=os.environ.get("P2KG_PDF_DIR", "data/raw"),
        )
