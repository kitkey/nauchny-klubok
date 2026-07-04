"""persist — st -> Neo4j (граф) + DocStore (артефакты). Идемпотентно (upsert по uuid/key)."""
from __future__ import annotations

from .context import ArticleState, Deps


def _index_embeddings(deps: Deps, st: ArticleState) -> None:
    """Считаем эмбеддинги сущностей (имя+алиасы) и фактов (statement) ОДИН раз при ингесте и кладём
    в Neo4j vector-index. Запрос потом эмбедит только вопрос, а не весь граф."""
    embed = getattr(deps, "embed", None)
    graph = deps.graph
    if embed is None or not hasattr(graph, "set_embeddings"):
        return
    try:
        ent_txt = [(e.canonical_name + " " + " ".join(e.aliases or [])).strip() for e in st.entities]
        fact_txt = [f.statement or "" for f in st.facts]
        evecs = embed.encode(ent_txt) if ent_txt else []
        fvecs = embed.encode(fact_txt) if fact_txt else []
        dim = len(evecs[0]) if evecs else (len(fvecs[0]) if fvecs else 0)
        if not dim:
            return
        graph.ensure_vector_indexes(dim)
        graph.set_embeddings("Entity", [(e.uuid, v) for e, v in zip(st.entities, evecs)])
        graph.set_embeddings("Fact", [(f.uuid, v) for f, v in zip(st.facts, fvecs)])
    except Exception:
        pass   # индексация эмбеддингов не должна ронять ингест


def persist(deps: Deps, st: ArticleState) -> ArticleState:
    if deps.graph is not None:
        deps.graph.upsert_entities(st.entities)
        deps.graph.upsert_facts(st.facts)
        deps.graph.upsert_edges(st.edges)
        _index_embeddings(deps, st)
    if deps.docs is not None and st.paper is not None:
        deps.docs.save_paper(st.paper)
        deps.docs.save_chunks(st.paper_ref, st.chunks)
        deps.docs.save_units(st.paper_ref, st.units)
    st.stage_status["persist"] = "ok"
    return st
