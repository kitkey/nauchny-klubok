"""Сервис: строит Deps под конкретный graph_id (Neo4j namespace + Mongo), ингест и ретрив.

Тяжёлые клиенты (Neo4j-драйвер, Mongo, LLM, эмбеддер) создаются лениво и кэшируются по graph_id.
"""
from __future__ import annotations

import os

from ..config import Config
from ..context import Deps
from ..embedder import HashEmbedder
from ..llm.client import LLMClient
from ..llm.prompts import PromptManager
from ..pipeline import process_source
from ..stores.docstore import MongoDocStore
from ..stores.graphstore import Neo4jGraph
from .. import retrieve as _retrieve

_DEPS: dict[str, Deps] = {}          # graph_id -> Deps (кэш)
_SHARED: dict = {}                    # общие клиенты (llm, embed, prompts, docs, cfg)


def _auth() -> tuple[str, str]:
    return (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", "password"))


def _embedder():
    try:
        from ..embedder import OpenRouterEmbedder
        if os.environ.get("OPENROUTER_API_KEY"):
            return OpenRouterEmbedder()
    except Exception:
        pass
    return HashEmbedder()          # оффлайн-фолбэк (несемантический) — линковка идёт по кодам/подстроке


def _shared() -> dict:
    if not _SHARED:
        cfg = Config.from_env()
        _SHARED.update(cfg=cfg, prompts=PromptManager(), embed=_embedder(),
                       llm=LLMClient.from_env(), docs=MongoDocStore(cfg.mongo_uri))
    return _SHARED


def build_deps(graph_id: str) -> Deps:
    if graph_id not in _DEPS:
        sh = _shared()
        graph = Neo4jGraph(sh["cfg"].neo4j_uri, auth=_auth(), graph_id=graph_id)
        _DEPS[graph_id] = Deps(llm=sh["llm"], embed=sh["embed"], prompts=sh["prompts"],
                               cfg=sh["cfg"], graph=graph, docs=sh["docs"])
    return _DEPS[graph_id]


def ingest_pdf(graph_id: str, path: str, paper_ref: str | None = None, supersede: bool = True) -> dict:
    """Полный прогон одного PDF: S0..persist -> узлы попадают в namespace graph_id.

    supersede=True: перед заливкой удаляем старую версию этого документа (по paper_ref) -> обновление
    без дублей, новая версия статьи вытесняет старую."""
    deps = build_deps(graph_id)
    if supersede and paper_ref and hasattr(deps.graph, "delete_paper"):
        deps.graph.delete_paper(paper_ref)
    st = process_source(deps, path, paper_ref=paper_ref)
    return {"paper_ref": st.paper_ref, "entities": len(st.entities), "facts": len(st.facts),
            "edges": len(st.edges), "status": dict(st.stage_status)}


def ask(graph_id: str, question: str, k: int = 16) -> dict:
    return _retrieve.answer(build_deps(graph_id), question, k=k)


def get_doc(graph_id: str, paper_ref: str) -> dict | None:
    p = build_deps(graph_id).docs.get_paper(paper_ref)
    if not p:
        return None
    return {"paper_ref": p.paper_ref, "title": p.title, "year": p.year,
            "n_chars": len(p.raw_text), "raw_text": p.raw_text}


def graph_stats(graph_id: str) -> dict:
    g = build_deps(graph_id).graph
    return g.stats() if hasattr(g, "stats") else {}


def discover(graph_id: str, topic: str, n: int = 6) -> dict:
    """Поиск внешних публикаций по теме, которых НЕТ в нашем корпусе.
    LLM формирует англоязычный научный запрос -> Crossref (реальные публикации, без ключа) ->
    дедуп против названий нашего корпуса. Наружу уходит только строка-запрос, не данные корпуса."""
    import httpx
    from ..llm.steps import DEFAULT_MODEL
    deps = build_deps(graph_id)
    q = topic
    try:
        q = (deps.llm.complete(
            "Преобразуй тему в короткий английский научный поисковый запрос (3–6 слов) для базы публикаций. "
            "Верни ТОЛЬКО запрос, без кавычек.\nТема: " + topic, model=DEFAULT_MODEL) or topic).strip().strip('"')[:120]
    except Exception:
        q = topic
    try:
        r = httpx.get("https://api.crossref.org/works",
                      params={"query": q, "rows": n * 2,
                              "select": "title,author,issued,container-title,DOI,URL"},
                      headers={"User-Agent": "nauchny-klubok/1.0 (mailto:demo@example.com)"}, timeout=20.0)
        items = r.json().get("message", {}).get("items", [])
    except Exception as e:
        return {"topic": topic, "query": q, "results": [], "error": repr(e)[:160]}
    try:
        existing = [x.lower() for x in deps.docs.list_papers()]
    except Exception:
        existing = []
    out = []
    for it in items:
        title = (it.get("title") or [""])[0]
        if not title:
            continue
        tl = title.lower()
        if any(tl[:28] in e or e[:28] in tl for e in existing):   # грубый дедуп против корпуса
            continue
        authors = ", ".join(x for x in
                            [((a.get("given", "") + " " + a.get("family", "")).strip()) for a in (it.get("author") or [])[:3]] if x)
        year = None
        try:
            year = it["issued"]["date-parts"][0][0]
        except Exception:
            pass
        out.append({"title": title, "authors": authors, "year": year,
                    "venue": (it.get("container-title") or [""])[0], "doi": it.get("DOI"), "url": it.get("URL")})
        if len(out) >= n:
            break
    return {"topic": topic, "query": q, "results": out}
