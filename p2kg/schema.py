"""Модель данных paper2kg — единый контракт для всех этапов (см. CONTRACTS.md).

Инварианты:
- Единица графа — реифицированный n-арный Fact-УЗЕЛ, не триплет.
- Источник неизменяем: Paper.raw_text frozen.
- Провенанс на каждом узле/ребре; координаты — символьные Span в raw_text.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Провенанс / локаторы
# =============================================================================


class Span(BaseModel):
    start: int
    end: int
    page: int | None = None


class TextLoc(BaseModel):
    kind: Literal["text"] = "text"
    span: Span
    anchor: str | None = None


class TableLoc(BaseModel):
    kind: Literal["table"] = "table"
    table_ref: str
    row: int
    col: int


class Provenance(BaseModel):
    paper_ref: str
    text_hash: str | None = None
    title: str | None = None
    loc: TextLoc | TableLoc
    confidence: float = 1.0


class Quantity(BaseModel):
    value: float | None = None
    unit: str | None = None
    operator: str = "="
    uncertainty: float | None = None
    lower: float | None = None
    upper: float | None = None
    raw: str | None = None


# =============================================================================
# Закрытые словари
# =============================================================================


class Role(str, Enum):
    BACKGROUND = "background"
    CLAIM = "claim"
    METHOD = "method"
    RESULT = "result"
    COMPARISON = "comparison"
    LIMITATION = "limitation"
    FUTURE = "future"
    OTHER = "other"


class EntityType(str, Enum):
    MATERIAL = "Material"
    PROPERTY = "Property"
    PROCESS = "Process"
    TECHNIQUE = "Technique"
    CONDITION = "Condition"
    PHASE = "Phase"
    ELEMENT = "Element"
    # --- горно-металлургический домен (сущности из документов) ---
    EQUIPMENT = "Equipment"      # установка/аппарат: ванна электроэкстракции, ПВП
    FACILITY = "Facility"        # площадка/лаборатория/институт: рудник, фабрика, Гипроникель
    PERSON = "Person"            # автор/эксперт
    LOCATION = "Location"        # география: Норильск, Россия, зарубеж


class FrameType(str, Enum):
    MATERIAL_MEASUREMENT = "MaterialMeasurement"
    SYNTHESIS_PROCEDURE = "SynthesisProcedure"
    CLAIM_FACT = "ClaimFact"
    HYPOTHESIS_FACT = "HypothesisFact"


class FactStatus(str, Enum):
    HYPOTHESIS = "hypothesis"
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    CONTESTED = "contested"
    REFUTED = "refuted"


class EdgeType(str, Enum):
    # A. n-арные слоты: Fact -> участник-сущность
    HAS_MATERIAL = "HAS_MATERIAL"
    HAS_PROPERTY = "HAS_PROPERTY"
    USES_TECHNIQUE = "USES_TECHNIQUE"
    UNDER_CONDITION = "UNDER_CONDITION"
    VIA_PROCESS = "VIA_PROCESS"
    PRODUCES = "PRODUCES"
    # B. состав / структура
    CONTAINS = "CONTAINS"
    HAS_PHASE = "HAS_PHASE"
    # C. причинные
    ENABLES = "ENABLES"
    INHIBITS = "INHIBITS"
    CAUSES = "CAUSES"
    CORRELATES_WITH = "CORRELATES_WITH"
    AFFECTS = "AFFECTS"
    # D. дискурсные
    SUPPORTED_BY = "SUPPORTED_BY"
    CONTRADICTED_BY = "CONTRADICTED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    # E. структурные / якорные
    REPORTS = "REPORTS"
    MENTIONS = "MENTIONS"
    CITES = "CITES"
    IS_A = "IS_A"
    INSTANCE_OF = "INSTANCE_OF"
    # G. таксономия сущностей (Entity -> Entity, из канонизации S4)
    SUBTYPE_OF = "SUBTYPE_OF"
    PART_OF = "PART_OF"
    # H. орг / оборудование / география (домен из документов)
    USES_EQUIPMENT = "USES_EQUIPMENT"    # Fact -> Equipment
    CONDUCTED_BY = "CONDUCTED_BY"        # Fact -> Person/Facility
    AUTHORED_BY = "AUTHORED_BY"          # Paper -> Person
    AFFILIATED_WITH = "AFFILIATED_WITH"  # Person -> Facility
    LOCATED_IN = "LOCATED_IN"            # Fact/Facility -> Location
    # F. открытый канал
    OPEN = "OPEN"


# =============================================================================
# Узлы графа
# =============================================================================


class Entity(BaseModel):
    uuid: str
    key: str
    type: EntityType
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    provenance: list[Provenance] = Field(default_factory=list)
    embedding_model: str | None = None
    embedding_dim: int | None = None


class Fact(BaseModel):
    uuid: str
    frame_type: FrameType
    paper_ref: str
    source: str = "text"   # "text" | "table" — табличные доверяем (точный provenance ячейки), verify их не гоняет
    statement: str | None = None
    quantity: Quantity | None = None
    provenance: Provenance
    negated: bool = False
    status: FactStatus = FactStatus.UNVERIFIED
    confidence: float = 0.0
    clarity: float = 0.0
    relevance: float = 0.0
    rationale: str = ""
    year: int | None = None   # год документа-источника (дата актуализации; для temporal-фильтра)


class Edge(BaseModel):
    src: str
    dst: str
    type: EdgeType
    rel: str | None = None
    rel_def: str | None = None
    props: dict = Field(default_factory=dict)
    provenance: Provenance


# =============================================================================
# S0-артефакты
# =============================================================================


class ParseMeta(BaseModel):
    parser: str
    ocr_used: bool = False
    lang: str | None = None
    n_pages: int
    n_chars: int
    n_tokens: int | None = None
    structure_reliable: bool = True
    notes: str = ""


class Section(BaseModel):
    sec_id: str
    name: str
    role_hint: Role | None = None
    span: Span


class Table(BaseModel):
    tbl_id: str
    caption: str = ""
    cells: list[list[str]] = Field(default_factory=list)
    span: Span | None = None


class Figure(BaseModel):
    fig_id: str
    caption: str = ""
    span: Span | None = None


class Ref(BaseModel):
    ref_id: str
    raw: str
    doi: str | None = None


class ParsedDoc(BaseModel):
    sections: list[Section] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    refs: list[Ref] = Field(default_factory=list)


class Paper(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    paper_ref: str
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    source_pdf: str = ""
    raw_text: str = Field(frozen=True)
    text_hash: str
    parsed: ParsedDoc = Field(default_factory=ParsedDoc)
    parse_meta: ParseMeta | None = None


class Chunk(BaseModel):
    chunk_id: str
    paper_ref: str
    index: int
    span: Span
    text: str
    sec_id: str | None = None
    role_hint: Role | None = None
    atomic_ref: str | None = None
    token_count: int | None = None
    overlap_prev: int = 0


class Unit(BaseModel):
    unit_id: str
    chunk_id: str
    paper_ref: str
    span: Span
    text: str
    role: Role
    role_confidence: float = 1.0
