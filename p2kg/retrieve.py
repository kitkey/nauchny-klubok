"""Ретрив: вопрос -> сущности-якоря -> факты (тег-оверлап + вектор + опц. PPR в духе HippoRAG) -> RRF.

LLM участвует только на краях: вычленить упоминания из вопроса и собрать финальный ответ.
Ранжирование — на графе и эмбеддингах. Работает поверх любого GraphStore с методами
all_entities / all_facts / all_edges (InMemoryGraph и Neo4jGraph их имеют).

Числа в ответе берутся из полей факта, не из модели. Точные совпадения (все якоря в факте) идут
выше ассоциативных (PPR/вектор), поэтому флагман «материал+режим -> свойство» отвечается точно.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from .embedder import cosine
from .llm.steps import run_step
from .schema import EntityType

_ENTITY_TYPES = {e.value for e in EntityType}
LINK_TOPK = 3
LINK_TH = 0.55        # косинус-порог привязки упоминания к сущности (для семантического эмбеддера)
RRF_C = 60
# рёбра, которые НЕ считаем «участник факта» (дискурс и Entity->Entity)
_NON_PARTICIPANT = {"SUPPORTED_BY", "CONTRADICTED_BY", "SUBTYPE_OF", "PART_OF", "INSTANCE_OF",
                    "IS_A", "AUTHORED_BY", "AFFILIATED_WITH"}


def _v(x):
    return getattr(x, "value", x)


class _Mention(BaseModel):
    text: str
    type: str | None = None


class _MentionsOut(BaseModel):
    mentions: list[_Mention] = Field(default_factory=list)


# ---------- снапшот графа ----------
@dataclass
class _Snap:
    ents: list
    facts: list
    fact_ents: dict          # fact_uuid -> set(entity_uuid)
    ent_by_uuid: dict
    fact_by_uuid: dict


def _snapshot(graph) -> _Snap:
    ents = list(graph.all_entities())
    facts = list(graph.all_facts())
    edges = list(graph.all_edges())
    ent_uuids = {e.uuid for e in ents}
    fact_uuids = {f.uuid for f in facts}
    fact_ents: dict = {}
    for ed in edges:
        if _v(ed.type) in _NON_PARTICIPANT:
            continue
        if ed.src in fact_uuids and ed.dst in ent_uuids:
            fact_ents.setdefault(ed.src, set()).add(ed.dst)
    return _Snap(ents, facts, fact_ents,
                 {e.uuid: e for e in ents}, {f.uuid: f for f in facts})


def _ent_text(e) -> str:
    parts = [e.canonical_name] + list(getattr(e, "aliases", []) or [])
    return " ; ".join(dict.fromkeys(p for p in parts if p))


# ---------- линковка упоминаний к узлам ----------
def _link(deps, mentions, snap: _Snap) -> set:
    anchors: set = set()
    if not snap.ents:
        return anchors
    names = [_ent_text(e) for e in snap.ents]
    embed = getattr(deps, "embed", None)
    evecs = embed.encode(names) if embed else None
    for m in mentions:
        mt = (getattr(m, "text", "") or "").strip()
        if not mt:
            continue
        mtl = mt.lower()
        typ = getattr(m, "type", None)
        typ = typ if typ in _ENTITY_TYPES else None
        # 1) точное/подстрочное совпадение (марки, коды, названия)
        for e, nm in zip(snap.ents, names):
            if typ and _v(e.type) != typ:
                continue
            nl = nm.lower()
            if mtl == nl or (len(mtl) >= 3 and (mtl in nl or nl in mtl)):
                anchors.add(e.uuid)
        # 2) эмбеддинг-топ-k (семантика)
        if embed and evecs:
            mv = embed.encode([mt])[0]
            scored = sorted(
                ((cosine(mv, evecs[i]), snap.ents[i]) for i in range(len(snap.ents))
                 if not typ or _v(snap.ents[i].type) == typ),
                key=lambda x: -x[0])[:LINK_TOPK]
            for s, e in scored:
                if s >= LINK_TH:
                    anchors.add(e.uuid)
    return anchors


# ---------- сигналы + RRF ----------
def _rrf(rankings, c: int = RRF_C) -> dict:
    score: dict = {}
    for r in rankings:
        for pos, u in enumerate(r):
            score[u] = score.get(u, 0.0) + 1.0 / (c + pos)
    return score


def _ppr_facts(snap: _Snap, anchors: set) -> list:
    """HippoRAG-стиль: Personalized PageRank от якорей по графу (сущности+факты). Опц. (нужен igraph)."""
    if not anchors:
        return []
    try:
        import igraph
    except Exception:
        return []
    ids = [e.uuid for e in snap.ents] + [f.uuid for f in snap.facts]
    idx = {u: i for i, u in enumerate(ids)}
    edges = [(idx[fu], idx[eu]) for fu, es in snap.fact_ents.items() if fu in idx
             for eu in es if eu in idx]
    seeded = [idx[a] for a in anchors if a in idx]
    if not edges or not seeded:
        return []
    g = igraph.Graph(n=len(ids), edges=edges, directed=False)
    reset = [0.0] * len(ids)
    for i in seeded:
        reset[i] = 1.0 / len(seeded)
    pr = g.personalized_pagerank(reset=reset)
    fact_uuids = {f.uuid for f in snap.facts}
    scored = sorted(((pr[idx[u]], u) for u in ids if u in fact_uuids), key=lambda x: -x[0])
    return [u for s, u in scored if s > 0][:30]


def _rank_facts(deps, question: str, snap: _Snap, anchors: set) -> list:
    overlap = {f.uuid: len(snap.fact_ents.get(f.uuid, set()) & anchors) for f in snap.facts}
    rankings: list = []
    tag = sorted([u for u, o in overlap.items() if o > 0], key=lambda u: -overlap[u])
    if tag:
        rankings.append(tag)
    embed = getattr(deps, "embed", None)
    if embed and snap.facts:
        qv = embed.encode([question])[0]
        svecs = embed.encode([f.statement or "" for f in snap.facts])
        vec = sorted(((cosine(qv, svecs[i]), snap.facts[i].uuid) for i in range(len(snap.facts))),
                     key=lambda x: -x[0])
        rankings.append([u for _, u in vec[:30]])
    ppr = _ppr_facts(snap, anchors)
    if ppr:
        rankings.append(ppr)
    rrf = _rrf(rankings)
    cand = set(rrf) | {u for u, o in overlap.items() if o > 0}
    # точные совпадения (больше якорей в факте) — выше; внутри — по RRF (вектор/PPR)
    return sorted(cand, key=lambda u: (overlap.get(u, 0), rrf.get(u, 0.0)), reverse=True)


# ---------- сборка результата ----------
def _qstr(q) -> str:
    if q is None:
        return ""
    raw = getattr(q, "raw", None)
    if raw:
        return raw
    val = getattr(q, "value", None)
    if val is None:
        return ""
    op = getattr(q, "operator", "") or ""
    unit = getattr(q, "unit", "") or ""
    return f"{op}{val} {unit}".strip()


@dataclass
class Evidence:
    uuid: str
    statement: str
    quantity: str
    participants: dict          # тип сущности -> [имена]
    source: str
    year: object
    status: str


@dataclass
class RetrieveResult:
    question: str
    anchors: list               # имена сущностей-якорей
    facts: list                 # list[Evidence]
    related: list               # связанные сущности (соседи по фактам)


def _evidence(snap: _Snap, uuid: str) -> Evidence:
    f = snap.fact_by_uuid[uuid]
    parts: dict = {}
    for eu in snap.fact_ents.get(uuid, ()):
        e = snap.ent_by_uuid.get(eu)
        if e:
            parts.setdefault(_v(e.type), []).append(e.canonical_name)
    return Evidence(uuid=uuid, statement=getattr(f, "statement", "") or "",
                    quantity=_qstr(getattr(f, "quantity", None)),
                    participants=parts, source=getattr(f, "paper_ref", "") or "",
                    year=getattr(f, "year", None), status=str(_v(getattr(f, "status", "") or "")))


def _extract_mentions(deps, question: str) -> list:
    try:
        out = run_step(deps, "retrieve.extract", schema=_MentionsOut, question=question)
        if out and out.mentions:
            return list(out.mentions)
    except Exception:
        pass
    return [_Mention(text=question)]      # фолбэк: весь вопрос как одно упоминание


def _retrieve_inmem(deps, question: str, *, k: int = 8, mentions=None) -> RetrieveResult:
    snap = _snapshot(deps.graph)
    if mentions is None:
        mentions = _extract_mentions(deps, question)
    anchors = _link(deps, mentions, snap)
    ranked = _rank_facts(deps, question, snap, anchors)[:k]
    ev = [_evidence(snap, u) for u in ranked]
    seen: set = set()
    related: list = []
    for e in ev:
        for names in e.participants.values():
            for n in names:
                if n not in seen:
                    seen.add(n)
                    related.append(n)
    anchor_names = [snap.ent_by_uuid[a].canonical_name for a in anchors if a in snap.ent_by_uuid]
    return RetrieveResult(question=question, anchors=anchor_names, facts=ev, related=related)


# ---------- масштабируемый путь (Neo4j vector-index): не грузим весь граф в память ----------
class _SubQOut(BaseModel):
    subqueries: list[str] = Field(default_factory=list)


def _decompose(deps, question: str) -> list[str]:
    """Мультивопрос -> под-вопросы по одной теме каждый (или [question], если простой)."""
    try:
        out = run_step(deps, "retrieve.decompose", schema=_SubQOut, question=question)
        subs = [s.strip() for s in (out.subqueries or []) if s and s.strip()]
        return subs[:6] or [question]
    except Exception:
        return [question]


def _retrieve_vector(deps, question: str, k: int) -> RetrieveResult:
    subs = _decompose(deps, question)
    qvecs = deps.embed.encode(subs)
    per = max(4, (k // max(1, len(subs))) + 2)
    lists = [deps.graph.search_facts(v, per) for v in qvecs]
    # PPR (структурный обход графа через GDS): якоря = топ-сущности по под-темам -> факты, связанные
    # с ними по рёбрам (+ мост по key даёт кросс-док). Второй сигнал рядом с вектором.
    if hasattr(deps.graph, "ppr"):
        try:
            anchors = {e["uuid"] for v in qvecs for e in deps.graph.search_entities(v, 4)}
            ppr = deps.graph.ppr(anchors, k=max(k, 20))
            if ppr:
                lists.append([{"uuid": r["uuid"]} for r in ppr])
        except Exception:
            pass   # нет GDS / ошибка -> работаем на одном векторе
    # round-robin по сигналам: каждая тема/сигнал представлены, один не забивает top-k (диверсификация)
    order, seen = [], set()
    for i in range(max((len(l) for l in lists), default=0)):
        for l in lists:
            if i < len(l) and l[i]["uuid"] not in seen:
                seen.add(l[i]["uuid"])
                order.append(l[i]["uuid"])
    top = order[:max(k, len(subs) * 3)]
    detail = deps.graph.facts_with_participants(top)
    ev, related, seenr = [], [], set()
    for u in top:
        d = detail.get(u)
        if not d:
            continue
        ev.append(Evidence(uuid=u, statement=d.statement, quantity=_qstr(d.quantity),
                           participants=d.participants, source=d.paper_ref or "",
                           year=d.year, status=str(_v(d.status or ""))))
        for names in d.participants.values():
            for n in names:
                if n not in seenr:
                    seenr.add(n)
                    related.append(n)
    return RetrieveResult(question=question, anchors=subs, facts=ev, related=related[:40])


def retrieve(deps, question: str, *, k: int = 8, mentions=None) -> RetrieveResult:
    """Neo4j (vector-index) -> масштабируемый путь; иначе (InMemory/тесты) -> in-memory."""
    if getattr(deps, "embed", None) is not None and hasattr(deps.graph, "search_facts") and mentions is None:
        try:
            return _retrieve_vector(deps, question, k)
        except Exception:
            pass   # деградируем в in-memory при любой проблеме vector-пути
    return _retrieve_inmem(deps, question, k=k, mentions=mentions)


def _trace_graph(res: RetrieveResult) -> dict:
    """Подграф ТРЕЙСА ответа: из каких фактов и сущностей собран ответ (для визуализации на графе)."""
    nodes, edges, seen = [], [], set()
    for i, e in enumerate(res.facts):
        fid = "f:" + e.uuid
        nodes.append({"id": fid, "kind": "Fact", "label": (e.statement or "")[:90],
                      "source": e.source, "value": e.quantity, "status": e.status, "rank": i})
        for etype, names in (e.participants or {}).items():
            for n in names:
                eid = "e:" + n
                if eid not in seen:
                    seen.add(eid)
                    nodes.append({"id": eid, "kind": etype, "label": n})
                edges.append({"src": fid, "dst": eid})
    return {"nodes": nodes, "edges": edges}


def answer(deps, question: str, *, k: int = 8) -> dict:
    """Полный путь: ретрив + LLM-синтез. Числа — из evidence, не из модели. + подграф трейса."""
    res = retrieve(deps, question, k=k)
    evidence = [{"statement": e.statement, "value": e.quantity, "participants": e.participants,
                 "source": e.source, "year": e.year, "status": e.status} for e in res.facts]
    text = ""
    try:
        text = run_step(deps, "retrieve.answer", question=question,
                        evidence=json.dumps(evidence, ensure_ascii=False, indent=1)) or ""
    except Exception:
        text = ""
    src: dict = {}          # точные файлы, из которых реально собран ответ (по фактам evidence)
    for e in res.facts:
        if e.source:
            src[e.source] = src.get(e.source, 0) + 1
    sources = [{"file": f, "facts": c} for f, c in sorted(src.items(), key=lambda x: -x[1])]
    return {"question": question, "answer": text, "anchors": res.anchors,
            "related": res.related, "evidence": evidence, "graph": _trace_graph(res),
            "sources": sources}
