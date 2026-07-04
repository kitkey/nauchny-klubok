"""GraphStore: интерфейс + InMemoryGraph (тесты) + Neo4jGraph (прод, граф + vector-index).

В пайплайне S4 уже дедуплицирует и перевешивает рёбра на канонические uuid, поэтому persist
делает простой upsert (MERGE) по uuid/key — идемпотентно.
"""
from __future__ import annotations

from typing import Protocol

from ..schema import Edge, Entity, EntityType, Fact


class GraphStore(Protocol):
    def upsert_entities(self, ents: list[Entity]) -> None: ...
    def upsert_facts(self, facts: list[Fact]) -> None: ...
    def upsert_edges(self, edges: list[Edge]) -> None: ...
    def find_entity_by_key(self, key: str) -> Entity | None: ...
    def vector_search(self, emb: list[float], top_k: int,
                      type: EntityType | None = None) -> list[Entity]: ...
    def paper_subgraph(self, paper_ref: str) -> dict: ...


class InMemoryGraph:
    """Граф в памяти — для тестов и быстрых прогонов."""

    def __init__(self) -> None:
        self.entities: dict[str, Entity] = {}     # uuid -> Entity
        self.facts: dict[str, Fact] = {}          # uuid -> Fact
        self.edges: list[Edge] = []
        self._by_key: dict[str, str] = {}         # key -> uuid

    def upsert_entities(self, ents: list[Entity]) -> None:
        for e in ents:
            if e.key in self._by_key:
                ex = self.entities[self._by_key[e.key]]
                merged = set(ex.aliases) | set(e.aliases) | {e.canonical_name}
                ex.aliases = sorted(merged - {ex.canonical_name})
                ex.provenance = ex.provenance + e.provenance
            else:
                self.entities[e.uuid] = e
                self._by_key[e.key] = e.uuid

    def upsert_facts(self, facts: list[Fact]) -> None:
        for f in facts:
            self.facts[f.uuid] = f

    def upsert_edges(self, edges: list[Edge]) -> None:
        self.edges.extend(edges)

    def find_entity_by_key(self, key: str) -> Entity | None:
        uid = self._by_key.get(key)
        return self.entities.get(uid) if uid else None

    def vector_search(self, emb, top_k, type=None):
        return []   # in-memory: без векторного индекса

    def all_entities(self):
        return list(self.entities.values())

    def all_facts(self):
        return list(self.facts.values())

    def all_edges(self):
        return list(self.edges)

    def delete_paper(self, paper_ref: str) -> None:
        """Убрать все узлы документа (супрессессия старой версии перед заливкой новой)."""
        fids = {u for u, f in self.facts.items() if getattr(f, "paper_ref", None) == paper_ref}
        touched = {e.dst for e in self.edges if e.src in fids} | {e.src for e in self.edges if e.dst in fids}
        for u in fids:
            self.facts.pop(u, None)
        self.edges = [e for e in self.edges if e.src not in fids and e.dst not in fids]
        for u in [x for x in touched if x in self.entities]:
            ent = self.entities.pop(u, None)
            if ent:
                self._by_key.pop(ent.key, None)

    def stats(self) -> dict:
        from collections import Counter
        ebt = Counter(getattr(e.type, "value", e.type) for e in self.entities.values())
        fbf = Counter(getattr(f.frame_type, "value", f.frame_type) for f in self.facts.values())
        fbs = Counter(f.paper_ref for f in self.facts.values())
        contested = sum(1 for f in self.facts.values() if str(getattr(f, "status", "")).endswith("contested"))
        return {"entities_by_type": dict(ebt), "facts_by_frame": dict(fbf),
                "facts_by_source": [{"source": s, "facts": c} for s, c in fbs.most_common(25)],
                "contested": contested, "top_entities": [],
                "total_entities": len(self.entities), "total_facts": len(self.facts), "n_sources": len(fbs)}

    def paper_subgraph(self, paper_ref: str) -> dict:
        return {
            "entities": list(self.entities.values()),
            "facts": [f for f in self.facts.values() if f.paper_ref == paper_ref],
            "edges": list(self.edges),
        }


class Neo4jGraph:
    """Прод: Neo4j (граф + нативный vector-index). neo4j-драйвер импортируется лениво."""

    def __init__(self, uri: str, auth: tuple[str, str] | None = None,
                 graph_id: str | None = None) -> None:
        from neo4j import GraphDatabase
        self._driver = GraphDatabase.driver(uri, auth=auth)
        self._gid = graph_id          # namespace: изоляция графов в одной БД (тег graph_id на узлах/рёбрах)

    def close(self) -> None:
        self._driver.close()

    def upsert_entities(self, ents: list[Entity]) -> None:
        with self._driver.session() as s:
            for e in ents:
                s.run(
                    "MERGE (n:Entity {uuid:$uuid}) "
                    "SET n.key=$key, n.type=$type, n.canonical_name=$name, n.aliases=$aliases, n.graph_id=$gid",
                    uuid=e.uuid, key=e.key, type=e.type.value,
                    name=e.canonical_name, aliases=e.aliases, gid=self._gid,
                )

    def upsert_facts(self, facts: list[Fact]) -> None:
        with self._driver.session() as s:
            for f in facts:
                q = f.quantity
                s.run(
                    "MERGE (n:Fact {uuid:$uuid}) "
                    "SET n.frame_type=$ft, n.paper_ref=$pr, n.source=$src, n.statement=$st, n.status=$status, "
                    "n.confidence=$c, n.clarity=$cl, n.relevance=$r, n.rationale=$rat, n.negated=$neg, "
                    "n.q_value=$qv, n.q_unit=$qu, n.q_operator=$qop, n.q_uncertainty=$qunc, "
                    "n.q_lower=$qlo, n.q_upper=$qhi, n.q_raw=$qraw, n.graph_id=$gid, n.year=$year",
                    uuid=f.uuid, ft=f.frame_type.value, pr=f.paper_ref, src=f.source, st=f.statement,
                    status=f.status.value, c=f.confidence, cl=f.clarity, r=f.relevance,
                    rat=f.rationale, neg=f.negated,
                    qv=(q.value if q else None), qu=(q.unit if q else None),
                    qop=(q.operator if q else None), qunc=(q.uncertainty if q else None),
                    qlo=(q.lower if q else None), qhi=(q.upper if q else None),
                    qraw=(q.raw if q else None), gid=self._gid, year=getattr(f, "year", None),
                )

    def upsert_edges(self, edges: list[Edge]) -> None:
        with self._driver.session() as s:
            for e in edges:
                # Neo4j-связь хранит только плоские скаляры -> фильтруем props
                props = {k: v for k, v in (e.props or {}).items()
                         if isinstance(v, (str, int, float, bool))}
                s.run(
                    "MATCH (a {uuid:$src}), (b {uuid:$dst}) "
                    "MERGE (a)-[r:REL {type:$type, rel:$rel}]->(b) "
                    "SET r += $props, r.graph_id=$gid",
                    src=e.src, dst=e.dst, type=e.type.value, rel=(e.rel or ""), props=props, gid=self._gid,
                )

    def find_entity_by_key(self, key: str) -> Entity | None:
        with self._driver.session() as s:
            rec = s.run(
                "MATCH (n:Entity {key:$key}) "
                "RETURN n.uuid AS uuid, n.type AS type, n.canonical_name AS name LIMIT 1",
                key=key,
            ).single()
        if not rec:
            return None
        return Entity(uuid=rec["uuid"], key=key, type=EntityType(rec["type"]),
                      canonical_name=rec["name"])

    def vector_search(self, emb, top_k, type=None):
        return []   # требует созданного native vector index; деталь прод-настройки

    def paper_subgraph(self, paper_ref: str) -> dict:
        with self._driver.session() as s:
            facts = [dict(r) for r in s.run(
                "MATCH (n:Fact {paper_ref:$pr}) RETURN n.uuid AS uuid, n.frame_type AS frame_type",
                pr=paper_ref)]
        return {"facts": facts}

    # ---------- концепт-слой (cross-paper) ----------
    def all_entities(self):
        """Все сущности графа как лёгкие объекты (uuid/canonical_name/type/aliases) для концепт-линковки."""
        from types import SimpleNamespace
        where = "WHERE e.graph_id=$gid " if self._gid else ""
        with self._driver.session() as s:
            rows = list(s.run("MATCH (e:Entity) " + where + "RETURN e.uuid AS uuid, e.canonical_name AS name, "
                              "e.type AS type, e.aliases AS aliases", gid=self._gid))
        out = []
        for r in rows:
            try:
                t = EntityType(r["type"])
            except ValueError:
                continue
            out.append(SimpleNamespace(uuid=r["uuid"], canonical_name=r["name"] or "",
                                       type=t, aliases=list(r["aliases"] or [])))
        return out

    def entity_contexts(self, k: int = 3, cap: int = 140) -> dict:
        """Для каждой сущности — до k statement'ов её фактов (контекст для линковки/определения)."""
        with self._driver.session() as s:
            rows = list(s.run("MATCH (f:Fact)-[:REL]->(e:Entity) WHERE f.statement IS NOT NULL "
                              "RETURN e.uuid AS uuid, collect(f.statement) AS stmts"))
        return {r["uuid"]: "; ".join(x[:cap] for x in [s for s in r["stmts"] if s][:k]) for r in rows}

    def all_facts(self):
        from types import SimpleNamespace
        where = "WHERE f.graph_id=$gid " if self._gid else ""
        with self._driver.session() as s:
            rows = list(s.run("MATCH (f:Fact) " + where + "RETURN f.uuid AS uuid, f.statement AS statement, "
                              "f.frame_type AS frame_type, f.paper_ref AS paper_ref, f.status AS status, "
                              "f.year AS year, f.q_value AS qv, f.q_unit AS qu, f.q_operator AS qop, f.q_raw AS qraw",
                              gid=self._gid))
        out = []
        for r in rows:
            q = None
            if r["qv"] is not None or r["qraw"]:
                q = SimpleNamespace(value=r["qv"], unit=r["qu"], operator=r["qop"], raw=r["qraw"])
            out.append(SimpleNamespace(uuid=r["uuid"], statement=r["statement"] or "",
                                       frame_type=r["frame_type"], paper_ref=r["paper_ref"],
                                       status=r["status"], year=r["year"], quantity=q))
        return out

    def all_edges(self):
        from types import SimpleNamespace
        where = "WHERE r.graph_id=$gid " if self._gid else ""
        with self._driver.session() as s:
            rows = list(s.run("MATCH (a)-[r:REL]->(b) " + where + "RETURN a.uuid AS src, b.uuid AS dst, r.type AS type",
                              gid=self._gid))
        return [SimpleNamespace(src=r["src"], dst=r["dst"], type=r["type"]) for r in rows]

    # ---------- векторный индекс (эмбеддинги считаются при ингесте, а не на каждый запрос) ----------
    def ensure_vector_indexes(self, dim: int) -> None:
        with self._driver.session() as s:
            for label in ("Entity", "Fact"):
                s.run(f"CREATE VECTOR INDEX {label.lower()}_vec IF NOT EXISTS "
                      f"FOR (n:{label}) ON (n.embedding) "
                      "OPTIONS {indexConfig: {`vector.dimensions`: $dim, "
                      "`vector.similarity_function`: 'cosine'}}", dim=dim)

    def set_embeddings(self, label: str, id_vecs) -> None:
        rows = [{"uuid": u, "emb": list(v)} for u, v in id_vecs]
        if not rows:
            return
        with self._driver.session() as s:
            s.run(f"UNWIND $rows AS row MATCH (n:{label} {{uuid:row.uuid}}) SET n.embedding=row.emb",
                  rows=rows)

    def await_indexes(self, timeout: int = 60) -> None:
        with self._driver.session() as s:
            s.run("CALL db.awaitIndexes($t)", t=timeout)

    def _vsearch(self, label: str, emb, k: int) -> list:
        fetch = k * (12 if self._gid else 1)   # over-fetch, потом фильтр по graph_id
        with self._driver.session() as s:
            return [dict(r) for r in s.run(
                "CALL db.index.vector.queryNodes($idx,$fetch,$emb) YIELD node, score "
                "WHERE ($gid IS NULL OR node.graph_id=$gid) "
                "RETURN node.uuid AS uuid, node.canonical_name AS name, node.type AS type, "
                "node.statement AS statement, node.paper_ref AS paper_ref, node.status AS status, "
                "node.year AS year, node.q_raw AS qraw, node.q_value AS qv, node.q_unit AS qu, "
                "node.q_operator AS qop, score ORDER BY score DESC LIMIT $k",
                idx=f"{label.lower()}_vec", fetch=fetch, emb=list(emb), gid=self._gid, k=k)]

    def search_facts(self, emb, k: int) -> list:
        return self._vsearch("Fact", emb, k)

    def search_entities(self, emb, k: int) -> list:
        return self._vsearch("Entity", emb, k)

    def facts_with_participants(self, fact_uuids) -> dict:
        """Для набора фактов — их участники-сущности (bounded Cypher, без загрузки всего графа)."""
        from types import SimpleNamespace
        if not fact_uuids:
            return {}
        pe = ["HAS_MATERIAL", "HAS_PROPERTY", "USES_TECHNIQUE", "UNDER_CONDITION", "VIA_PROCESS",
              "PRODUCES", "USES_EQUIPMENT", "LOCATED_IN", "CONDUCTED_BY", "MENTIONS"]
        with self._driver.session() as s:
            rows = list(s.run(
                "MATCH (f:Fact) WHERE f.uuid IN $ids "
                "OPTIONAL MATCH (f)-[r:REL]->(e:Entity) WHERE r.type IN $pe "
                "RETURN f.uuid AS uuid, f.statement AS statement, f.paper_ref AS paper_ref, "
                "f.status AS status, f.year AS year, f.q_raw AS qraw, f.q_value AS qv, "
                "f.q_unit AS qu, f.q_operator AS qop, "
                "collect({name:e.canonical_name, type:e.type}) AS parts",
                ids=list(fact_uuids), pe=pe))
        out: dict = {}
        for r in rows:
            q = None
            if r["qraw"] or r["qv"] is not None:
                q = SimpleNamespace(raw=r["qraw"], value=r["qv"], unit=r["qu"], operator=r["qop"])
            parts: dict = {}
            for p in r["parts"]:
                if p and p.get("name"):
                    parts.setdefault(p["type"], []).append(p["name"])
            out[r["uuid"]] = SimpleNamespace(uuid=r["uuid"], statement=r["statement"] or "",
                                             paper_ref=r["paper_ref"], status=r["status"],
                                             year=r["year"], quantity=q, participants=parts)
        return out

    def facts_needing_verification(self, uuids) -> list:
        """Из набора uuid — факты, которые ещё НЕ проверялись (status='unverified' и без флага v_checked).
        Для ленивой верификации в момент ответа."""
        if not uuids:
            return []
        with self._driver.session() as s:
            rows = s.run(
                "MATCH (f:Fact) WHERE f.uuid IN $u "
                + ("AND f.graph_id=$gid " if self._gid else "")
                + "AND f.status='unverified' AND coalesce(f.v_checked,false)=false "
                "RETURN f.uuid AS uuid, f.statement AS statement, f.paper_ref AS paper_ref, f.q_raw AS qraw",
                u=list(uuids), gid=self._gid)
            return [dict(r) for r in rows]

    def set_fact_verification(self, rows) -> None:
        """Записать результат ленивой верификации: status + флаг v_checked (повторно не гоняем) + скор/обоснование."""
        if not rows:
            return
        with self._driver.session() as s:
            s.run(
                "UNWIND $rows AS r MATCH (f:Fact {uuid:r.uuid}) "
                + ("WHERE f.graph_id=$gid " if self._gid else "")
                + "SET f.status=r.status, f.v_checked=true, f.v_conf=r.conf, f.v_rationale=r.rationale",
                rows=list(rows), gid=self._gid)

    def delete_paper(self, paper_ref: str) -> None:
        """Удалить факты документа и их сущности (супрессессия старой версии). uuid уникальны на док,
        поэтому сущности факта принадлежат только ему -> DETACH DELETE безопасен."""
        with self._driver.session() as s:
            s.run("MATCH (f:Fact {paper_ref:$ref}) WHERE ($gid IS NULL OR f.graph_id=$gid) "
                  "OPTIONAL MATCH (f)-[:REL]->(e:Entity) DETACH DELETE f, e",
                  ref=paper_ref, gid=self._gid)

    def stats(self) -> dict:
        we = "WHERE e.graph_id=$gid " if self._gid else ""
        wf = "WHERE f.graph_id=$gid " if self._gid else ""
        wfc = "WHERE f.graph_id=$gid AND f.status='contested'" if self._gid else "WHERE f.status='contested'"
        with self._driver.session() as s:
            ebt = {r["t"]: r["c"] for r in s.run("MATCH (e:Entity) " + we + "RETURN e.type AS t, count(*) AS c", gid=self._gid)}
            fbf = {r["t"]: r["c"] for r in s.run("MATCH (f:Fact) " + wf + "RETURN f.frame_type AS t, count(*) AS c", gid=self._gid)}
            fbs = [{"source": r["s"], "facts": r["c"]} for r in s.run("MATCH (f:Fact) " + wf + "RETURN f.paper_ref AS s, count(*) AS c ORDER BY c DESC LIMIT 25", gid=self._gid)]
            crow = s.run("MATCH (f:Fact) " + wfc + " RETURN count(*) AS c", gid=self._gid).single()
            tope = [{"name": r["n"], "type": r["t"], "facts": r["c"]} for r in s.run(
                "MATCH (f:Fact)-[:REL]->(e:Entity) " + wf + "RETURN e.canonical_name AS n, e.type AS t, count(*) AS c ORDER BY c DESC LIMIT 15", gid=self._gid)]
            nsrc = s.run("MATCH (f:Fact) " + wf + "RETURN count(DISTINCT f.paper_ref) AS c", gid=self._gid).single()
        return {"entities_by_type": {k: v for k, v in ebt.items() if k}, "facts_by_frame": {k: v for k, v in fbf.items() if k},
                "facts_by_source": fbs, "contested": (crow["c"] if crow else 0), "top_entities": tope,
                "total_entities": sum(ebt.values()), "total_facts": sum(fbf.values()),
                "n_sources": (nsrc["c"] if nsrc else len(fbs))}   # DISTINCT, а не длина топ-25

    def ppr(self, anchor_uuids, k: int = 25) -> list:
        """Personalized PageRank (Neo4j GDS) от якорных сущностей по всему графу.
        Проекция: Entity+Fact+Concept + рёбра REL + мост по одинаковому key (кросс-док).
        Возвращает [{uuid, statement, paper_ref, score}] — факты по структурной близости к якорям.
        Требует плагин graph-data-science; при отсутствии/ошибке кидает исключение (ретривер деградирует)."""
        anchors = list(anchor_uuids)
        if not anchors:
            return []
        name = "ppr_" + (self._gid or "all")[:10]
        gf = "n.graph_id=$gid AND " if self._gid else ""
        mf = "m.graph_id=$gid AND " if self._gid else ""
        af = "a.graph_id=$gid AND " if self._gid else ""
        with self._driver.session() as s:
            s.run("CALL gds.graph.drop($n, false) YIELD graphName RETURN graphName", n=name).consume()
            aids = [r["id"] for r in s.run(
                "MATCH (e:Entity) WHERE e.uuid IN $u " + ("AND e.graph_id=$gid " if self._gid else "")
                + "RETURN id(e) AS id", u=anchors, gid=self._gid)]
            if not aids:
                return []
            s.run(
                "CALL { "
                "  MATCH (n) WHERE " + gf + "(n:Entity OR n:Fact OR n:Concept) "
                "  OPTIONAL MATCH (n)-[:REL]-(m) WHERE " + mf + "(m:Entity OR m:Fact OR m:Concept) "
                "  RETURN n AS s, m AS t "
                "  UNION "
                "  MATCH (a:Entity) WHERE " + af + "a.key IS NOT NULL "
                "  WITH a.key AS kk, collect(a) AS es WHERE size(es)>1 "
                "  UNWIND range(0,size(es)-2) AS i RETURN es[i] AS s, es[i+1] AS t "
                "} WITH gds.graph.project($n, s, t) AS gg RETURN gg.nodeCount", n=name, gid=self._gid).consume()
            rows = [dict(r) for r in s.run(
                "CALL gds.pageRank.stream($n, {sourceNodes:$a, maxIterations:20, dampingFactor:0.85}) "
                "YIELD nodeId, score WITH gds.util.asNode(nodeId) AS node, score WHERE node:Fact AND score>0 "
                "RETURN node.uuid AS uuid, node.statement AS statement, node.paper_ref AS paper_ref, score "
                "ORDER BY score DESC LIMIT $k", n=name, a=aids, k=k)]
            s.run("CALL gds.graph.drop($n, false) YIELD graphName RETURN graphName", n=name).consume()
        return rows

    def persist_concept_graph(self, concepts, instances, subtypes) -> None:
        """Concept-узлы + рёбра Entity-INSTANCE_OF->Concept и Concept-SUBTYPE_OF->Concept."""
        with self._driver.session() as s:
            for c in concepts:
                s.run("MERGE (n:Concept {uuid:$u}) SET n.name=$n, n.type=$t, n.definition=$d, "
                      "n.n_instances=$ni, n.defined=$df, n.hierarchy_done=$hd",
                      u=c.uuid, n=c.name, t=c.type.value, d=c.context, ni=c.n,
                      df=c.defined, hd=c.hierarchy_done)
            for (e_uuid, c_uuid) in instances:
                s.run("MATCH (e:Entity {uuid:$e}), (c:Concept {uuid:$c}) "
                      "MERGE (e)-[:REL {type:'INSTANCE_OF', rel:''}]->(c)", e=e_uuid, c=c_uuid)
            for (child, parent) in subtypes:
                s.run("MATCH (a:Concept {uuid:$a}), (b:Concept {uuid:$b}) "
                      "MERGE (a)-[:REL {type:'SUBTYPE_OF', rel:''}]->(b)", a=child, b=parent)
