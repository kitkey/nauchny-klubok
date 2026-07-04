"""S4: дедуп сущностей (key-merge + БАТЧ near-dup эмбеддинг/LLM) и фактов (повтор/конфликт)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..concurrency import pmap
from ..embedder import cosine
from ..llm.steps import run_step
from ..provenance import context_snippet
from ..schema import EdgeType, Edge, FactStatus, Quantity


class _PairVerdict(BaseModel):
    id: int
    same: bool = False
    rationale: str = ""


def _ent_ctx(raw: str, ent) -> str:
    return context_snippet(raw, ent.provenance[0]) if ent.provenance else ""


def _dedup_entities(deps, st) -> None:
    raw = st.paper.raw_text if getattr(st, "paper", None) else ""
    # 1) key-merge (детерминированно)
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

    # 2) near-dup внутри типа: эмбеддинг отбирает пары-кандидаты -> ОДИН батч-вызов LLM
    merged_keys: set[str] = set()
    if deps.embed is not None:
        by_type: dict = {}
        for e in ents:
            by_type.setdefault(e.type, []).append(e)
        pairs: list[tuple] = []
        for group in by_type.values():
            if len(group) < 2:
                continue
            try:
                vecs = deps.embed.encode([e.canonical_name for e in group])
            except Exception:
                continue   # эмбеддер сбоил на группе -> пропускаем near-dup (key-merge уже применён, док не падает)
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    if cosine(vecs[i], vecs[j]) >= 0.93:
                        pairs.append((group[i], group[j]))
        if pairs:
            items = [{"id": k, "a": a.canonical_name, "a_ctx": _ent_ctx(raw, a),
                      "b": b.canonical_name, "b_ctx": _ent_ctx(raw, b)}
                     for k, (a, b) in enumerate(pairs)]
            out = run_step(deps, "link.dedup", schema=list[_PairVerdict], pairs=items) or []
            same_ids = {v.id for v in out if getattr(v, "same", False)}
            for k, (a, b) in enumerate(pairs):
                if k not in same_ids or a.key in merged_keys or b.key in merged_keys:
                    continue
                a.aliases = sorted((set(a.aliases) | set(b.aliases) | {b.canonical_name}) - {a.canonical_name})
                a.provenance = a.provenance + b.provenance
                for kk, val in list(remap.items()):
                    if val == b.uuid:
                        remap[kk] = a.uuid
                remap[b.uuid] = a.uuid
                merged_keys.add(b.key)
        ents = [e for e in ents if e.key not in merged_keys]

    # 3) перевесить рёбра на канонические uuid
    for ed in st.edges:
        ed.src = remap.get(ed.src, ed.src)
        ed.dst = remap.get(ed.dst, ed.dst)
    st.entities = ents


class _FactDedupOut(BaseModel):
    duplicates: list[list[int]] = Field(default_factory=list)      # группы id «это один и тот же факт»
    contradictions: list[list[int]] = Field(default_factory=list)  # группы id «конфликт значений»


def _qsig(q: Quantity | None):
    return None if q is None else (q.value, q.unit, q.operator)


def _qstr(q: Quantity | None) -> str:
    if q is None:
        return ""
    if q.raw:
        return q.raw
    if q.value is not None:
        return f"{q.operator or ''}{q.value} {q.unit or ''}".strip()
    return ""


def _dedup_facts(deps, st) -> None:
    ent_of: dict[str, set] = {}
    for ed in st.edges:
        if ed.type in (EdgeType.SUPPORTED_BY, EdgeType.CONTRADICTED_BY,
                       EdgeType.SUBTYPE_OF, EdgeType.PART_OF):
            continue   # дискурсные и Entity->Entity рёбра не участвуют в сигнатуре факта
        ent_of.setdefault(ed.src, set()).add(ed.dst)
    name_of = {e.uuid: e.canonical_name for e in st.entities}

    # группируем факты по сигнатуре = (тип факта + набор сущностей)
    by_sig: dict = {}
    for f in st.facts:
        ents = frozenset(ent_of.get(f.uuid, ()))
        if not ents:
            continue   # факты без сущностей не дедупим
        by_sig.setdefault((f.frame_type, ents), []).append(f)

    drop: set[str] = set()
    contradictions: list[tuple[str, str]] = []
    llm_groups: list[tuple] = []   # (представители, участники) для LLM-суждения
    for sig, facts in by_sig.items():
        # 1) ДЕТЕРМИНИРОВАННО: точные дубли (та же сигнатура И то же значение) -> в один
        rep: dict = {}
        reps: list = []
        for f in facts:
            k = _qsig(f.quantity)
            if k in rep:
                drop.add(f.uuid)
            else:
                rep[k] = f
                reps.append(f)
        # 2) осталось >1 различных -> отдаём LLM (почти-дубли / реальный конфликт / законно разные)
        if len(reps) >= 2:
            participants = sorted(name_of.get(u, u) for u in sig[1])
            llm_groups.append((reps, participants))

    def _judge(arg):
        reps, participants = arg
        facts_payload = [{"id": i, "statement": f.statement or "", "value": _qstr(f.quantity)}
                         for i, f in enumerate(reps)]
        return run_step(deps, "link.dedup_facts", schema=_FactDedupOut,
                        participants=participants, facts=facts_payload)

    outs = pmap(_judge, llm_groups, deps.cfg.workers) if llm_groups else []

    for (reps, _), out in zip(llm_groups, outs):
        if out is None:   # LLM не ответил -> безопасный фолбэк: пометить группу как конфликт
            for f in reps:
                f.status = FactStatus.CONTESTED
            for f in reps[1:]:
                contradictions.append((reps[0].uuid, f.uuid))
            continue
        gone: set[int] = set()
        for dup in (out.duplicates or []):           # почти-дубли -> схлопнуть в первый
            ids = [i for i in dup if 0 <= i < len(reps)]
            for i in ids[1:]:
                drop.add(reps[i].uuid)
                gone.add(i)
        for con in (out.contradictions or []):       # реальный конфликт -> CONTESTED + CONTRADICTED_BY
            ids = [i for i in con if 0 <= i < len(reps) and i not in gone]
            for i in ids:
                reps[i].status = FactStatus.CONTESTED
            for i in ids[1:]:
                contradictions.append((reps[ids[0]].uuid, reps[i].uuid))

    if drop:
        st.facts = [f for f in st.facts if f.uuid not in drop]
        st.edges = [e for e in st.edges if e.src not in drop and e.dst not in drop]
    for a, b in contradictions:
        prov = next((f.provenance for f in st.facts if f.uuid == a), None)
        if prov is not None:
            st.edges.append(Edge(src=a, dst=b, type=EdgeType.CONTRADICTED_BY, provenance=prov))
