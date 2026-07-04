"""Общее для S3: LLM-схемы вывода, маппинг слотов фрейма -> (EntityType, EdgeType), сборщики узлов."""
from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field, field_validator

from ..schema import (
    Edge, EdgeType, Entity, EntityType, Fact, FrameType, Provenance, Quantity, Span, TextLoc,
)


class _OpenEdgeOut(BaseModel):
    src_anchor: str
    dst_anchor: str
    rel: str


class _AboutOut(BaseModel):
    """Для Claim/Hypothesis: сущность, О КОТОРОЙ тезис (-> ребро MENTIONS)."""
    mention: str
    type: EntityType


class _FrameOut(BaseModel):
    frame_type: FrameType
    slots: dict[str, str] = Field(default_factory=dict)   # slot -> anchor-упоминание сущности
    quantity: Quantity | None = None
    statement: str = ""
    negated: bool = False
    about: list[_AboutOut] = Field(default_factory=list)  # для Claim/Hypothesis
    open_edges: list[_OpenEdgeOut] = Field(default_factory=list)

    @field_validator("frame_type", mode="before")
    @classmethod
    def _fix_frame_type(cls, v):
        # модель иногда кладёт в frame_type тип СУЩНОСТИ ("Location", "Material") -> не валим весь батч,
        # трактуем неизвестный frame_type как ClaimFact
        if isinstance(v, FrameType):
            return v
        if v not in {e.value for e in FrameType}:
            return FrameType.CLAIM_FACT.value
        return v

    @field_validator("slots", mode="before")
    @classmethod
    def _drop_null_slots(cls, v):
        # модель легитимно шлёт {"condition": null}, когда слота нет; dict[str,str] это отвергает.
        # (раньше instructor-reask «чинил» null->""; reask убран -> терпим null здесь сами)
        if isinstance(v, dict):
            return {k: s for k, s in v.items() if s is not None and str(s).strip()}
        return v

    @field_validator("statement", mode="before")
    @classmethod
    def _statement_none_to_empty(cls, v):
        return "" if v is None else v

    @field_validator("negated", mode="before")
    @classmethod
    def _negated_none_to_false(cls, v):
        return False if v is None else v

    @field_validator("open_edges", mode="before")
    @classmethod
    def _clean_open_edges(cls, v):
        # выкидываем ребро с null/пустым якорем или rel, чтобы не валить весь список фреймов из-за одного кривого
        if not isinstance(v, list):
            return [] if v is None else v
        return [it for it in v if not isinstance(it, dict)   # уже собранный инстанс -> пропускаем
                or all(str(it.get(k) or "").strip() for k in ("src_anchor", "dst_anchor", "rel"))]

    @field_validator("about", mode="before")
    @classmethod
    def _clean_about(cls, v):
        if not isinstance(v, list):
            return [] if v is None else v
        valid = {e.value for e in EntityType}   # дропаем и кривой enum (напр. "MATERIAL"), не только null
        return [it for it in v if not isinstance(it, dict)   # уже собранный инстанс -> пропускаем
                or (str(it.get("mention") or "").strip() and it.get("type") in valid)]


class LocalGraph(BaseModel):
    entities: list[Entity] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


# slot -> (тип сущности, тип ребра Fact->Entity)
FRAME_SLOTS: dict[FrameType, dict[str, tuple[EntityType, EdgeType]]] = {
    FrameType.MATERIAL_MEASUREMENT: {
        "material": (EntityType.MATERIAL, EdgeType.HAS_MATERIAL),
        "property": (EntityType.PROPERTY, EdgeType.HAS_PROPERTY),
        "technique": (EntityType.TECHNIQUE, EdgeType.USES_TECHNIQUE),
        "condition": (EntityType.CONDITION, EdgeType.UNDER_CONDITION),
        "equipment": (EntityType.EQUIPMENT, EdgeType.USES_EQUIPMENT),
        "location": (EntityType.LOCATION, EdgeType.LOCATED_IN),
    },
    FrameType.SYNTHESIS_PROCEDURE: {
        "material": (EntityType.MATERIAL, EdgeType.PRODUCES),
        "process": (EntityType.PROCESS, EdgeType.VIA_PROCESS),
        "condition": (EntityType.CONDITION, EdgeType.UNDER_CONDITION),
        "equipment": (EntityType.EQUIPMENT, EdgeType.USES_EQUIPMENT),
        "location": (EntityType.LOCATION, EdgeType.LOCATED_IN),
    },
}


def _slug(s: str) -> str:
    return re.sub(r"\s+", "-", s.strip().lower())[:80]


def _uuid() -> str:
    return uuid.uuid4().hex


def _prov(paper, anchor: str, fallback: Span) -> Provenance:
    from ..provenance import find_anchor
    sp = find_anchor(paper.raw_text, anchor) if anchor else None
    return Provenance(paper_ref=paper.paper_ref, text_hash=paper.text_hash,
                      title=(paper.title or None),
                      loc=TextLoc(span=sp or fallback, anchor=(anchor or None)))


def _mk_entity(etype: EntityType, mention: str, paper, span: Span) -> Entity:
    return Entity(uuid=_uuid(), key=f"{etype.value}:{_slug(mention)}", type=etype,
                  canonical_name=mention.strip(),
                  provenance=[Provenance(paper_ref=paper.paper_ref, text_hash=paper.text_hash,
                                         loc=TextLoc(span=span))])


def build_from_frames(frames: list[_FrameOut], paper, base_span: Span, source: str = "text") -> LocalGraph:
    """Фреймы LLM -> локальные Entity/Fact/Edge. open_edges пока пропускаем (causal — позже)."""
    lg = LocalGraph()
    for fr in frames:
        # якорим провенанс на ДОСЛОВНОМ упоминании (слот/about), а не на парафразе statement
        mentions = [m for m in (fr.slots or {}).values() if m] + [a.mention for a in fr.about if a.mention]
        anchor = mentions[0] if mentions else " ".join((fr.statement or "").split()[:8])
        fact = Fact(uuid=_uuid(), frame_type=fr.frame_type, paper_ref=paper.paper_ref, source=source,
                    statement=(fr.statement or None), quantity=fr.quantity, negated=fr.negated,
                    year=getattr(paper, "year", None),
                    provenance=_prov(paper, anchor, base_span))
        lg.facts.append(fact)
        # типизированные слоты фрейма -> рёбра ядра
        slotmap = FRAME_SLOTS.get(fr.frame_type, {})
        for slot, mention in (fr.slots or {}).items():
            spec = slotmap.get(slot)
            if not spec or not mention:
                continue
            etype, edge_type = spec
            ent = _mk_entity(etype, mention, paper, base_span)
            lg.entities.append(ent)
            lg.edges.append(Edge(src=fact.uuid, dst=ent.uuid, type=edge_type,
                                 provenance=fact.provenance))
        # about (Claim/Hypothesis): сущности, о которых тезис -> рёбра MENTIONS
        for ab in fr.about:
            if not ab.mention:
                continue
            ent = _mk_entity(ab.type, ab.mention, paper, base_span)
            lg.entities.append(ent)
            lg.edges.append(Edge(src=fact.uuid, dst=ent.uuid, type=EdgeType.MENTIONS,
                                 provenance=fact.provenance))
    return lg
