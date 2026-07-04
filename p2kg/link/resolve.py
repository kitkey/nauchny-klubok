"""S4: канонизация сущностей — key-merge + LLM-кластеризация с контекстом (merge) + иерархия (relations).

Заменяет попарный эмбеддинг-дедуп: один LLM-вызов на ТИП кластеризует имена (ловит синонимы/аббревиатуры,
которые не берут косинус/строка) и заодно строит рёбра иерархии SUBTYPE_OF/PART_OF между «почти-дублями».
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from ..concurrency import pmap
from ..llm.steps import run_step
from ..schema import Edge, EdgeType

_REL_TYPES = {"SUBTYPE_OF": EdgeType.SUBTYPE_OF, "PART_OF": EdgeType.PART_OF}


class _Relation(BaseModel):
    child: str
    parent: str
    rel: str = "SUBTYPE_OF"


class _ResolveOut(BaseModel):
    merge: list[list[str]] = Field(default_factory=list)
    relations: list[_Relation] = Field(default_factory=list)

    @field_validator("merge", mode="before")
    @classmethod
    def _clean_merge(cls, v):
        # null/пустые имена в кластере выкидываем; кластер <2 имён бесполезен (нечего сливать)
        if not isinstance(v, list):
            return [] if v is None else v
        out = []
        for cl in v:
            if isinstance(cl, list):
                names = [s for s in cl if s is not None and str(s).strip()]
                if len(names) >= 2:
                    out.append(names)
        return out

    @field_validator("relations", mode="before")
    @classmethod
    def _clean_relations(cls, v):
        # выкидываем связь с null/пустым child|parent, чтобы один кривой элемент не валил весь resolve типа
        if not isinstance(v, list):
            return [] if v is None else v
        return [r for r in v if not isinstance(r, dict)   # уже собранный _Relation -> пропускаем
                or (str(r.get("child") or "").strip() and str(r.get("parent") or "").strip())]


def _resolve_entities(deps, st) -> None:
    # 0) key-merge (детерминированно): точный slug
    canon_by_key: dict = {}
    remap: dict[str, str] = {}
    for e in st.entities:
        if e.key in canon_by_key:
            c = canon_by_key[e.key]
            c.aliases = sorted((set(c.aliases) | set(e.aliases) | {e.canonical_name}) - {c.canonical_name})
            c.provenance = c.provenance + e.provenance
            remap[e.uuid] = c.uuid
        else:
            canon_by_key[e.key] = e
            remap[e.uuid] = e.uuid
    ents = list(canon_by_key.values())

    # контекст: канон-сущность -> statement'ы её фактов (ed.src=факт, ed.dst=сущность)
    stmt_of = {f.uuid: (f.statement or "") for f in st.facts}
    ctx: dict[str, list[str]] = {}
    for ed in st.edges:
        s = stmt_of.get(ed.src)
        if s:
            ctx.setdefault(remap.get(ed.dst, ed.dst), []).append(s)

    by_type: dict = {}
    for e in ents:
        by_type.setdefault(e.type, []).append(e)
    groups = [g for g in by_type.values() if len(g) >= 2]

    def _resolve(group):
        payload = [{"name": e.canonical_name, "aliases": e.aliases,
                    "context": "; ".join(s[:120] for s in ctx.get(e.uuid, [])[:3])} for e in group]
        return run_step(deps, "link.resolve", schema=_ResolveOut,
                        type=group[0].type.value, entities=payload)

    results = pmap(_resolve, groups, deps.cfg.workers)

    merged_keys: set[str] = set()
    rel_pending: list[tuple] = []   # (child_uuid, parent_uuid, EdgeType, provenance)
    for group, out in zip(groups, results):
        if not out:
            continue
        nmap: dict[str, object] = {}
        for e in group:
            nmap[e.canonical_name] = e
            for a in e.aliases:
                nmap.setdefault(a, e)

        for cluster in (out.merge or []):
            members, seen_u = [], set()
            for n in cluster:
                e = nmap.get(n)
                if e and e.uuid not in seen_u:
                    seen_u.add(e.uuid)
                    members.append(e)
            if len(members) < 2:
                continue
            canon = members[0]
            for victim in members[1:]:
                if victim.key in merged_keys or victim.uuid == canon.uuid:
                    continue
                canon.aliases = sorted((set(canon.aliases) | set(victim.aliases) | {victim.canonical_name}) - {canon.canonical_name})
                canon.provenance = canon.provenance + victim.provenance
                for k, v in list(remap.items()):
                    if v == victim.uuid:
                        remap[k] = canon.uuid
                remap[victim.uuid] = canon.uuid
                merged_keys.add(victim.key)

        for r in (out.relations or []):
            et = _REL_TYPES.get((r.rel or "").upper())
            c, p = nmap.get(r.child), nmap.get(r.parent)
            if et is None or not c or not p:
                continue
            prov = (c.provenance or p.provenance or [None])[0]
            if prov is not None:
                rel_pending.append((c.uuid, p.uuid, et, prov))

    ents = [e for e in ents if e.key not in merged_keys]

    # перевесить fact->entity рёбра на канонические uuid
    for ed in st.edges:
        ed.src = remap.get(ed.src, ed.src)
        ed.dst = remap.get(ed.dst, ed.dst)

    # добавить Entity->Entity рёбра иерархии, если такой пары ещё нет
    existing = {(ed.src, ed.dst, ed.type) for ed in st.edges}
    for c_uuid, p_uuid, et, prov in rel_pending:
        src, dst = remap.get(c_uuid, c_uuid), remap.get(p_uuid, p_uuid)
        if src == dst or (src, dst, et) in existing:
            continue
        existing.add((src, dst, et))
        st.edges.append(Edge(src=src, dst=dst, type=et, provenance=prov))

    st.entities = ents
