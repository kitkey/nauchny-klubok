import importlib

from p2kg.provenance import text_hash
from p2kg.schema import Chunk, Paper, Span
from p2kg.stores.docstore import InMemoryDocStore, SqliteDocStore


def _paper():
    raw = "Some materials science text."
    return Paper(paper_ref="arxiv:1v1", raw_text=raw, text_hash=text_hash(raw), title="T")


def _chunks():
    return [Chunk(chunk_id="chunk-0", paper_ref="arxiv:1v1", index=0,
                  span=Span(start=0, end=4), text="Some")]


def _roundtrip(store):
    store.save_paper(_paper())
    store.save_chunks("arxiv:1v1", _chunks())
    p = store.get_paper("arxiv:1v1")
    assert p is not None and p.title == "T"
    ch = store.get_chunks("arxiv:1v1")
    assert len(ch) == 1 and ch[0].chunk_id == "chunk-0"
    assert store.list_papers() == ["arxiv:1v1"]


def test_inmemory_roundtrip():
    _roundtrip(InMemoryDocStore())


def test_sqlite_roundtrip():
    _roundtrip(SqliteDocStore(":memory:"))


def test_mongo_module_importable():
    m = importlib.import_module("p2kg.stores.docstore")
    assert hasattr(m, "MongoDocStore")
