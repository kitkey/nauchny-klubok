"""Cross-paper концепт-слой: Entity --INSTANCE_OF--> Concept --SUBTYPE_OF--> Concept.

Неразрушающе: сущности статей не трогаем (провенанс цел), концепты — отдельный корпус-слой.
Линковка: косинус только БЛОКИНГ (кандидаты внутри типа) -> LLM РЕШАЕТ всегда (косинус ненадёжен).
Иерархия концептов строится инкрементально, ДВУНАПРАВЛЕННО (родитель/ребёнок), со вставкой посередине
(транзитивная редукция) и защитой от циклов (DAG).
"""
from __future__ import annotations

import re
import uuid as _uuidlib
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, field_validator

from ..concurrency import pmap
from ..embedder import cosine
from ..llm.steps import run_step
from ..schema import EntityType

TH_BLOCK = 0.45     # косинус-floor: ниже — LLM даже не спрашиваем (заведомо не тот концепт)
LINK_K = 6          # сколько кандидатов-концептов давать LLM на линковку
HIER_K = 8          # сколько близких концептов давать LLM на иерархию
CONTEXT_CAP = 360   # потолок провизорного пула statement'ов концепта (≈3 шт.)
DEFINE_AT = 3       # с какого числа инстансов выясняем определение концепта (refine-define)
MAX_NAME_WORDS = 8  # имя длиннее -> похоже на фразу-инстанс, не концепт
T_MERGE = 0.92      # пред-кластеризация: взаимно >=этого -> почти точно один концепт, LLM не зовём (экономия)
NAME_W = 0.7        # вес ИМЕНИ в блокинг-эмбеддинге (0.7 имя + 0.3 контекст)

# число-с-единицей (дамп параметров рецепта/условия): «500 W», «50 sccm», «300 nm», «20°C», «15 mins»…
_UNIT = re.compile(r"\d+(?:\.\d+)?\s*(?:W|kW|V|mV|A|mA|sccm|nm|µm|um|mm|cm|Å|K|°C|℃|µbar|ubar|bar|"
                   r"Pa|kPa|MPa|GPa|Torr|rpm|Hz|kHz|MHz|GHz|min|mins|hr|h|ms|eV|meV|wt%|at%|%)\b", re.I)


def _is_conceptual(name: str) -> bool:
    """Стоит ли заводить КОНЦЕПТ под эту сущность. False для гипер-специфичных одноразовых:
    длинная фраза-инстанс или дамп параметров (рецепт/многопараметрическое условие)."""
    if not name or not name.strip():
        return False
    if len(name.split()) > MAX_NAME_WORDS:
        return False
    if len(_UNIT.findall(name)) >= 2:
        return False
    return True


def _new_uuid() -> str:
    return _uuidlib.uuid4().hex


@dataclass
class Concept:
    uuid: str
    name: str
    type: EntityType
    aliases: list = field(default_factory=list)
    vec: list = field(default_factory=list)
    context: str = ""        # провизорный пул statement'ов (пока n<DEFINE_AT) ИЛИ определение (после refine)
    n: int = 0               # сколько инстансов слинковано (порог для refine-define и иерархии)
    defined: bool = False    # вызван ли concept.define (иначе context — сырой пул упоминаний)
    hierarchy_done: bool = False   # строили ли иерархию (ровно один раз, когда концепт дозрел n>=DEFINE_AT)


@dataclass
class ConceptGraph:
    concepts: dict = field(default_factory=dict)   # uuid -> Concept
    subtype: set = field(default_factory=set)      # (child_uuid, parent_uuid)  Concept->Concept
    instance: list = field(default_factory=list)   # (entity_uuid, concept_uuid)  Entity->Concept

    def add_concept(self, c: Concept) -> None:
        self.concepts[c.uuid] = c

    def parents(self, u: str) -> set:
        return {p for (c, p) in self.subtype if c == u}


# ---------- LLM-схемы ----------
class _LinkOut(BaseModel):
    match_id: int | None = None   # id кандидата или null (=> новый концепт)


class _HierItem(BaseModel):
    id: int
    rel: str = "none"             # "parent" (C подтип кандидата) | "child" (кандидат подтип C) | "same" | "none"


class _HierOut(BaseModel):
    relations: list[_HierItem] = Field(default_factory=list)

    @field_validator("relations", mode="before")
    @classmethod
    def _clean_relations(cls, v):
        # выкидываем элемент с null id, чтобы один кривой не валил всю иерархию концепта
        if not isinstance(v, list):
            return [] if v is None else v
        return [r for r in v if not isinstance(r, dict) or r.get("id") is not None]   # инстанс -> пропускаем


class _DefineOut(BaseModel):
    definition: str = ""

    @field_validator("definition", mode="before")
    @classmethod
    def _none_to_empty(cls, v):
        return "" if v is None else v


# ---------- хелперы ----------
def _name_text(name: str, aliases) -> str:
    parts = [name] + list(aliases or [])
    return " ; ".join(dict.fromkeys(p for p in parts if p))   # имя + ВСЕ вариации, без дублей


def _norm(v):
    import math
    s = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / s for x in v]


def _blend(name_vec, ctx_vec):
    """Вектор для БЛОКИНГА = взвешенная сумма имя/контекст (NAME_W=0.7): одноимённые сущности с разным
    контекстом всё равно близки -> одна канопия. Полный контекст идёт в LLM-решение, не в блокинг."""
    nv, cv = _norm(name_vec), _norm(ctx_vec)
    return [NAME_W * a + (1 - NAME_W) * b for a, b in zip(nv, cv)]


def _topk_list(concepts, vec, etype, k, exclude=()):
    scored = []
    for c in concepts:
        if c.type != etype or c.uuid in exclude or not c.vec:
            continue
        scored.append((cosine(vec, c.vec), c))
    scored.sort(key=lambda x: -x[0])
    return [(s, c) for s, c in scored[:k] if s >= TH_BLOCK]


def _topk(cg: ConceptGraph, vec, etype, k, exclude=()):
    return _topk_list(cg.concepts.values(), vec, etype, k, exclude)


def _components(items, th):
    """Компоненты связности по cosine>=th внутри типа (union-find). Используется и для канопий (TH_BLOCK),
    и для пред-кластеризации представителей (T_MERGE). Элементы разных компонент заведомо <th похожи."""
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if items[i][0].type == items[j][0].type and cosine(items[i][2], items[j][2]) >= th:
                parent[find(i)] = find(j)
    groups: dict = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(items[i])
    return list(groups.values())


def _reachable(cg: ConceptGraph, a: str, b: str) -> bool:
    """достижим ли b из a по SUBTYPE_OF (a -> ... -> b); для защиты от циклов."""
    seen, stack = set(), [a]
    while stack:
        u = stack.pop()
        if u == b:
            return True
        for p in cg.parents(u):
            if p not in seen:
                seen.add(p)
                stack.append(p)
    return False


def _augment_ctx(c: Concept, new: str) -> None:
    """провизорный пул: копим сырые statement'ы упоминаний, пока концепт не дозрел (n<DEFINE_AT)."""
    if new and new not in c.context and len(c.context) < CONTEXT_CAP:
        c.context = (c.context + " | " + new).strip(" |")[:CONTEXT_CAP]


def _define_concept(deps, name: str, etype, ctx_text: str) -> str:
    """Короткое определение концепта (что значит) из ПУЛА statement'ов нескольких инстансов.
    Запускается при дозревании (n>=DEFINE_AT) — определение полнее, чем из одной статьи."""
    out = run_step(deps, "concept.define", schema=_DefineOut, term=name,
                   type=getattr(etype, "value", etype), context=ctx_text)
    return out.definition.strip() if out and out.definition else ctx_text[:CONTEXT_CAP]


def _merge_concept(cg: ConceptGraph, dup: Concept, keep: Concept) -> None:
    """LLM сказал, что dup и keep — один концепт: переносим instance/рёбра на keep, dup удаляем."""
    cg.instance = [(e, keep.uuid if cu == dup.uuid else cu) for (e, cu) in cg.instance]
    cg.subtype = {(keep.uuid if a == dup.uuid else a, keep.uuid if p == dup.uuid else p)
                  for (a, p) in cg.subtype} - {(keep.uuid, keep.uuid)}
    cg.concepts.pop(dup.uuid, None)


# ---------- проход A: линковка сущностей к концептам ----------
def _link_call(deps, e, ectx, cands):
    """один concept.link-вызов: вернуть выбранный концепт или None (косинус-блокинг -> LLM решает)."""
    if not cands:
        return None
    payload = [{"id": i, "name": cc.name, "aliases": list(cc.aliases), "context": cc.context}
               for i, (_, cc) in enumerate(cands)]
    try:
        out = run_step(deps, "concept.link", schema=_LinkOut, mention=e.canonical_name,
                       aliases=list(e.aliases), context=ectx, candidates=payload)
    except Exception:
        out = None   # сбой вызова -> «не совпало»; слой не падает
    if out and out.match_id is not None and 0 <= out.match_id < len(cands):
        return cands[out.match_id][1]
    return None


def _attach(deps, c: Concept, ectx: str) -> None:
    """прикрепить инстанс к существующему концепту: +1, копить провизорный пул, refine-define при дозревании."""
    c.n += 1
    if not c.defined:
        _augment_ctx(c, ectx)
        if c.n >= DEFINE_AT:
            try:
                c.context = _define_concept(deps, c.name, c.type, c.context)
                c.defined = True
            except Exception:
                pass


def link_entities(deps, cg: ConceptGraph, entities, ctx: dict, embed=None) -> list:
    """Двухфазно: (A) ПАРАЛЛЕЛЬНЫЙ матч против ЗАМОРОЖЕННОГО набора концептов; (B) КАНОПИ-ПАРАЛЛЕЛЬНОЕ
    создание новых концептов из несматченного (внутри канопии — последовательно, чтобы дубли друг друга
    слились). Возвращает список НОВЫХ концептов."""
    embed = embed or deps.embed
    names = [_name_text(e.canonical_name, e.aliases) for e in entities]
    ctxs = [ctx.get(e.uuid, "") for e in entities]
    nvecs = embed.encode(names)
    cvecs = embed.encode([c or n for c, n in zip(ctxs, names)])   # пустой контекст -> берём имя
    items = [(e, c, _blend(nv, cv)) for e, c, nv, cv in zip(entities, ctxs, nvecs, cvecs)]
    frozen = list(cg.concepts.values())   # существующие концепты (incremental); пусто на cold-start

    # ---- ФАЗА A (ПАРАЛЛЕЛЬНО): матч против замороженного набора (только чтение -> порядко-независимо) ----
    def _match(item):
        e, ectx, vec = item
        return (item, _link_call(deps, e, ectx, _topk_list(frozen, vec, e.type, LINK_K)))

    matched = pmap(_match, items, deps.cfg.workers) if frozen else [(it, None) for it in items]
    deferred = []
    for item, concept in matched:
        if concept is not None:
            _attach(deps, concept, item[1])
            cg.instance.append((item[0].uuid, concept.uuid))
        else:
            deferred.append(item)

    # ---- ФАЗА B (КАНОПИ-ПАРАЛЛЕЛЬНО): новые концепты из несматченного; канопии независимы ----
    def _process_canopy(cano):
        local = ConceptGraph()
        lfresh = []
        # ПРЕД-КЛАСТЕРИЗАЦИЯ: взаимно >=T_MERGE -> один концепт; представитель идёт в LLM, остальные наследуют
        for cluster in _components(cano, T_MERGE):
            re_, rectx, rvec = cluster[0]
            chosen = _link_call(deps, re_, rectx, _topk_list(local.concepts.values(), rvec, re_.type, LINK_K))
            if chosen is None:
                if not _is_conceptual(re_.canonical_name):
                    continue   # представитель (и весь near-identical кластер) — мусор, не концепт
                chosen = Concept(uuid=_new_uuid(), name=re_.canonical_name, type=re_.type,
                                 aliases=list(re_.aliases), vec=list(rvec), context=rectx, n=1)
                local.add_concept(chosen); lfresh.append(chosen)
            else:
                _attach(deps, chosen, rectx)
            local.instance.append((re_.uuid, chosen.uuid))
            for e2, ectx2, _ in cluster[1:]:   # наследники концепта представителя — БЕЗ LLM-вызова
                _attach(deps, chosen, ectx2)
                local.instance.append((e2.uuid, chosen.uuid))
        return local, lfresh

    fresh = []
    for local, lfresh in pmap(_process_canopy, _components(deferred, TH_BLOCK), deps.cfg.workers):
        cg.concepts.update(local.concepts)   # канопии disjoint (cross-канопи <TH_BLOCK) -> union безопасен
        cg.instance.extend(local.instance)
        fresh.extend(lfresh)
    return fresh


# ---------- проход B: иерархия — ТОЛЬКО для дозревших концептов (n>=DEFINE_AT), один раз ----------
def relink_hierarchy(deps, cg: ConceptGraph) -> None:
    # синглтоны/редкий хвост в таксономию не тащим (дорого и бессмысленно); строим её на хабах.
    to_place = [c for c in cg.concepts.values() if c.n >= DEFINE_AT and not c.hierarchy_done]
    if not to_place:
        return

    # ФАЗА 1 (ПАРАЛЛЕЛЬНО): вердикты — независимы, только ЧТЕНИЕ набора. Кандидаты — концепты ЛЮБОЙ зрелости
    # (дозревший хаб может бесплатно усыновить близкий синглтон как child/parent в своём же вызове).
    def _verdict(c):
        near = _topk(cg, c.vec, c.type, HIER_K, exclude={c.uuid})
        if not near:
            return (c, [], None)
        payload = [{"id": i, "name": n.name, "context": n.context} for i, (_, n) in enumerate(near)]
        try:
            out = run_step(deps, "concept.hierarchy", schema=_HierOut,
                           concept=c.name, concept_context=c.context, candidates=payload)
        except Exception:
            out = None
        return (c, near, out)

    results = pmap(_verdict, to_place, deps.cfg.workers)

    # ФАЗА 2 (ПОСЛЕДОВАТЕЛЬНО, без LLM): применяем рёбра с cycle-guard + транзитивной редукцией
    for c, near, out in results:
        c.hierarchy_done = True   # помечаем обработанным (повторно не считаем даже если рёбер не вышло)
        if c.uuid not in cg.concepts or not near or not out:
            continue
        rels = [it for it in out.relations if 0 <= it.id < len(near)]
        same = next((near[it.id][1] for it in rels if it.rel == "same"), None)
        if same is not None and same.uuid in cg.concepts:   # дубль концепта -> слить
            _merge_concept(cg, c, same)
            continue
        parents, children = [], []
        for it in rels:
            n = near[it.id][1]
            if n.uuid not in cg.concepts:        # кандидат мог быть слит как 'same' в другом вердикте
                continue
            if it.rel == "parent" and not _reachable(cg, n.uuid, c.uuid):   # c -> n; цикл если n достигает c
                cg.subtype.add((c.uuid, n.uuid)); parents.append(n)
            elif it.rel == "child" and not _reachable(cg, c.uuid, n.uuid):  # n -> c; цикл если c достигает n
                cg.subtype.add((n.uuid, c.uuid)); children.append(n)
        for ch in children:                      # вставка посередине: ch->c->p => убрать прямое ch->p
            for p in parents:
                cg.subtype.discard((ch.uuid, p.uuid))


def build_concept_layer(deps, cg: ConceptGraph, entities, ctx: dict, embed=None) -> list:
    """Полный шаг: линковка + иерархия (только для дозревших концептов) для новой пачки сущностей."""
    fresh = link_entities(deps, cg, entities, ctx, embed=embed)
    relink_hierarchy(deps, cg)
    return fresh


def build_and_persist_concepts(deps, cg: ConceptGraph | None = None) -> ConceptGraph:
    """Cross-paper шаг поверх Neo4j: грузим сущности+контекст из графа -> строим концепт-слой -> персистим.
    cg можно передать (инкремент против существующих концептов); по умолчанию пустой (полный проход)."""
    cg = cg or ConceptGraph()
    entities = deps.graph.all_entities()
    ctx = deps.graph.entity_contexts()
    build_concept_layer(deps, cg, entities, ctx)
    deps.graph.persist_concept_graph(list(cg.concepts.values()), cg.instance, cg.subtype)
    return cg
