"""Трассировка прогона: тайминги стадий + все LLM-запросы/ответы.

Бэкенды:
- NullTracer  — no-op (дефолт в Deps, ноль оверхеда в тестах).
- JsonlTracer — строка JSON на событие в logs/<run_id>.jsonl (грепать/диффать без БД).
- MongoTracer — коллекции `runs` (таймлайн) и `llm_calls` (каждый вызов).
- MultiTracer — фан-аут в несколько бэкендов с общим run_id.

Tracer держит run_id и «текущую статью», поэтому run_step не нужно знать paper_ref.
Вся «переписка» статьи = выборка llm_calls по (run_id, paper_ref) сортированная по seq.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ser(resp):
    if resp is None or isinstance(resp, (str, int, float, bool)):
        return resp
    if isinstance(resp, list):
        return [_ser(x) for x in resp]
    if hasattr(resp, "model_dump"):
        try:
            return resp.model_dump(mode="json")
        except Exception:
            return str(resp)
    return str(resp)


class NullTracer:
    run_id = ""

    def start_paper(self, paper_ref: str) -> None: ...
    def end_paper(self, paper_ref: str, **summary) -> None: ...
    def log_stage(self, paper_ref: str, name: str, duration_s: float, error: str | None = None) -> None: ...
    def llm_call(self, **kw) -> None: ...

    @contextmanager
    def stage(self, paper_ref: str, name: str):
        yield


class _BaseTracer:
    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self._cur: str | None = None
        self._seq = 0
        self._t0: dict[str, float] = {}
        self._acc: dict[str, dict] = {}   # paper_ref -> агрегаты cost/токенов
        self._lock = threading.Lock()     # llm_call зовётся из пула потоков

    def _emit(self, coll: str, doc: dict) -> None:
        raise NotImplementedError

    def start_paper(self, paper_ref: str) -> None:
        self._cur = paper_ref
        self._seq = 0
        self._t0[paper_ref] = time.perf_counter()
        self._acc[paper_ref] = {"cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "llm_calls": 0}
        self._emit("runs", {"event": "paper_start", "run_id": self.run_id,
                            "paper_ref": paper_ref, "ts": _now()})

    def end_paper(self, paper_ref: str, **summary) -> None:
        dur = time.perf_counter() - self._t0.get(paper_ref, time.perf_counter())
        acc = self._acc.get(paper_ref, {})
        self._emit("runs", {"event": "paper_end", "run_id": self.run_id, "paper_ref": paper_ref,
                            "ts": _now(), "duration_s": round(dur, 3),
                            "cost": round(acc.get("cost", 0.0), 6),
                            "prompt_tokens": acc.get("prompt_tokens", 0),
                            "completion_tokens": acc.get("completion_tokens", 0),
                            "llm_calls": acc.get("llm_calls", 0), **summary})

    def log_stage(self, paper_ref: str, name: str, duration_s: float, error: str | None = None) -> None:
        self._emit("runs", {"event": "stage", "run_id": self.run_id, "paper_ref": paper_ref,
                            "stage": name, "duration_s": round(duration_s, 3),
                            "error": error, "ts": _now()})

    @contextmanager
    def stage(self, paper_ref: str, name: str):
        t = time.perf_counter()
        err = None
        try:
            yield
        except Exception as e:
            err = repr(e)
            raise
        finally:
            self.log_stage(paper_ref, name, time.perf_counter() - t, err)

    def llm_call(self, *, step: str, model: str, system: str, user: str,
                 response, latency: float, ok: bool = True, error: str | None = None,
                 usage: dict | None = None) -> None:
        with self._lock:                       # вызывается конкурентно из пула
            self._seq += 1
            doc = {"run_id": self.run_id, "paper_ref": self._cur, "seq": self._seq,
                   "step": step, "model": model, "system": system, "user": user,
                   "response": _ser(response), "latency_s": round(latency, 3),
                   "ok": ok, "error": error, "ts": _now()}
            if usage:
                doc["prompt_tokens"] = usage.get("prompt_tokens")
                doc["completion_tokens"] = usage.get("completion_tokens")
                doc["total_tokens"] = usage.get("total_tokens")
                doc["cost"] = usage.get("cost")
                doc["provider"] = usage.get("provider")
                a = self._acc.get(self._cur)
                if a is not None:
                    a["llm_calls"] += 1
                    a["prompt_tokens"] += usage.get("prompt_tokens") or 0
                    a["completion_tokens"] += usage.get("completion_tokens") or 0
                    a["cost"] += usage.get("cost") or 0.0
            self._emit("llm_calls", doc)


class JsonlTracer(_BaseTracer):
    def __init__(self, path: str, run_id: str | None = None) -> None:
        super().__init__(run_id)
        import os
        self._path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def _emit(self, coll: str, doc: dict) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"_coll": coll, **doc}, ensure_ascii=False) + "\n")


class MongoTracer(_BaseTracer):
    def __init__(self, uri: str, db: str = "p2kg", run_id: str | None = None) -> None:
        super().__init__(run_id)
        from pymongo import MongoClient
        self._db = MongoClient(uri)[db]

    def _emit(self, coll: str, doc: dict) -> None:
        self._db[coll].insert_one(dict(doc))   # копия: insert_one добавит _id


class MultiTracer:
    """Фан-аут в несколько бэкендов; run_id берём у первого (передавай им общий run_id)."""

    def __init__(self, *tracers) -> None:
        self._ts = [t for t in tracers if t is not None]
        self.run_id = self._ts[0].run_id if self._ts else ""

    def start_paper(self, p: str) -> None:
        for t in self._ts:
            t.start_paper(p)

    def end_paper(self, p: str, **k) -> None:
        for t in self._ts:
            t.end_paper(p, **k)

    def log_stage(self, p: str, n: str, d: float, error: str | None = None) -> None:
        for t in self._ts:
            t.log_stage(p, n, d, error)

    def llm_call(self, **kw) -> None:
        for t in self._ts:
            t.llm_call(**kw)

    @contextmanager
    def stage(self, p: str, n: str):
        t0 = time.perf_counter()
        err = None
        try:
            yield
        except Exception as e:
            err = repr(e)
            raise
        finally:
            for t in self._ts:
                t.log_stage(p, n, time.perf_counter() - t0, err)
