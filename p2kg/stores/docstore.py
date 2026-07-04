"""DocStore: артефакты (Paper/Chunk/Unit). InMemory (тесты) / Sqlite (локально) / Mongo (прод)."""
from __future__ import annotations

import json
from typing import Protocol

from ..schema import Chunk, Paper, Unit


class DocStore(Protocol):
    def save_paper(self, paper: Paper) -> None: ...
    def get_paper(self, paper_ref: str) -> Paper | None: ...
    def save_chunks(self, paper_ref: str, chunks: list[Chunk]) -> None: ...
    def get_chunks(self, paper_ref: str) -> list[Chunk]: ...
    def save_units(self, paper_ref: str, units: list[Unit]) -> None: ...
    def get_units(self, paper_ref: str) -> list[Unit]: ...
    def list_papers(self) -> list[str]: ...


class InMemoryDocStore:
    def __init__(self) -> None:
        self._papers: dict[str, Paper] = {}
        self._chunks: dict[str, list[Chunk]] = {}
        self._units: dict[str, list[Unit]] = {}

    def save_paper(self, paper: Paper) -> None:
        self._papers[paper.paper_ref] = paper

    def get_paper(self, paper_ref: str) -> Paper | None:
        return self._papers.get(paper_ref)

    def save_chunks(self, paper_ref: str, chunks: list[Chunk]) -> None:
        self._chunks[paper_ref] = list(chunks)

    def get_chunks(self, paper_ref: str) -> list[Chunk]:
        return self._chunks.get(paper_ref, [])

    def save_units(self, paper_ref: str, units: list[Unit]) -> None:
        self._units[paper_ref] = list(units)

    def get_units(self, paper_ref: str) -> list[Unit]:
        return self._units.get(paper_ref, [])

    def list_papers(self) -> list[str]:
        return list(self._papers)


class SqliteDocStore:
    def __init__(self, path: str = ":memory:") -> None:
        import sqlite3
        self._c = sqlite3.connect(path)
        for t in ("papers", "chunks", "units"):
            self._c.execute(f"CREATE TABLE IF NOT EXISTS {t}(paper_ref TEXT PRIMARY KEY, json TEXT)")
        self._c.commit()

    def _put(self, table: str, paper_ref: str, payload: str) -> None:
        self._c.execute(f"INSERT OR REPLACE INTO {table} VALUES(?,?)", (paper_ref, payload))
        self._c.commit()

    def _get(self, table: str, paper_ref: str) -> str | None:
        row = self._c.execute(f"SELECT json FROM {table} WHERE paper_ref=?", (paper_ref,)).fetchone()
        return row[0] if row else None

    def save_paper(self, paper: Paper) -> None:
        self._put("papers", paper.paper_ref, paper.model_dump_json())

    def get_paper(self, paper_ref: str) -> Paper | None:
        raw = self._get("papers", paper_ref)
        return Paper.model_validate_json(raw) if raw else None

    def save_chunks(self, paper_ref: str, chunks: list[Chunk]) -> None:
        self._put("chunks", paper_ref, json.dumps([c.model_dump() for c in chunks]))

    def get_chunks(self, paper_ref: str) -> list[Chunk]:
        raw = self._get("chunks", paper_ref)
        return [Chunk.model_validate(d) for d in json.loads(raw)] if raw else []

    def save_units(self, paper_ref: str, units: list[Unit]) -> None:
        self._put("units", paper_ref, json.dumps([u.model_dump() for u in units]))

    def get_units(self, paper_ref: str) -> list[Unit]:
        raw = self._get("units", paper_ref)
        return [Unit.model_validate(d) for d in json.loads(raw)] if raw else []

    def list_papers(self) -> list[str]:
        return [r[0] for r in self._c.execute("SELECT paper_ref FROM papers")]


class MongoDocStore:
    def __init__(self, uri: str, db: str = "p2kg") -> None:
        from pymongo import MongoClient
        self._db = MongoClient(uri)[db]

    def save_paper(self, paper: Paper) -> None:
        self._db.papers.replace_one({"_id": paper.paper_ref},
                                    {"_id": paper.paper_ref, **paper.model_dump()}, upsert=True)

    def get_paper(self, paper_ref: str) -> Paper | None:
        d = self._db.papers.find_one({"_id": paper_ref})
        if not d:
            return None
        d.pop("_id", None)
        return Paper.model_validate(d)

    def save_chunks(self, paper_ref: str, chunks: list[Chunk]) -> None:
        self._db.chunks.replace_one({"_id": paper_ref},
                                    {"_id": paper_ref, "items": [c.model_dump() for c in chunks]}, upsert=True)

    def get_chunks(self, paper_ref: str) -> list[Chunk]:
        d = self._db.chunks.find_one({"_id": paper_ref})
        return [Chunk.model_validate(x) for x in d["items"]] if d else []

    def save_units(self, paper_ref: str, units: list[Unit]) -> None:
        self._db.units.replace_one({"_id": paper_ref},
                                   {"_id": paper_ref, "items": [u.model_dump() for u in units]}, upsert=True)

    def get_units(self, paper_ref: str) -> list[Unit]:
        d = self._db.units.find_one({"_id": paper_ref})
        return [Unit.model_validate(x) for x in d["items"]] if d else []

    def list_papers(self) -> list[str]:
        return [d["_id"] for d in self._db.papers.find({}, {"_id": 1})]
