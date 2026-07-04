"""FastAPI: команды/графы/доступ (control-plane) + загрузка документов + ретрив.

Запуск:  uvicorn p2kg.api.app:app --reload
Текущий пользователь берётся из заголовка X-User (аутентификации пока нет — задел под RBAC).
Ингест PDF идёт фоновой задачей; статус — /api/graphs/{gid}/status.
"""
from __future__ import annotations

import pathlib
import shutil
import traceback

from fastapi import BackgroundTasks, Body, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..config import Config
from . import service
from .control import MemControl, MongoControl

_STATIC = pathlib.Path(__file__).resolve().parent / "static"
_UPLOADS = pathlib.Path("data/uploads")

app = FastAPI(title="Научный клубок")

# Граф-эксплорер (фронт команды) как отдельная полноэкранная страница; чат внутри идёт в наш /ask
if (_STATIC / "explore").is_dir():
    app.mount("/explore", StaticFiles(directory=str(_STATIC / "explore"), html=True), name="explore")


def _control():
    try:
        return MongoControl(Config.from_env().mongo_uri)
    except Exception:
        return MemControl()          # фолбэк без Mongo (control-plane в памяти)


ctl = _control()
JOBS: dict = {}                      # graph_id -> list[job]


def _seed() -> None:
    if not ctl.teams:                # чтобы UI работал сразу
        t = ctl.create_team("Демо-НИИ")
        ctl.ensure_user("demo", "demo")
        ctl.add_member("demo", t)


_seed()


def _user(x_user: str | None) -> str:
    u = (x_user or "demo").strip() or "demo"
    ctl.ensure_user(u, u)
    return u


def _require(gid: str, user: str) -> None:
    if not ctl.can_access(user, gid):
        raise HTTPException(403, "нет доступа к этому графу")


@app.get("/")
def index():
    return FileResponse(str(_STATIC / "index.html"))


# ---------------- команды ----------------
@app.get("/api/teams")
def list_teams(x_user: str | None = Header(None)):
    u = _user(x_user)
    return {"teams": ctl.teams_tree(), "my_teams": sorted(ctl.user_teams(u))}


@app.post("/api/teams")
def create_team(body: dict = Body(...), x_user: str | None = Header(None)):
    u = _user(x_user)
    tid = ctl.create_team(body["name"], parent_id=body.get("parent_id") or None)
    ctl.add_member(u, tid)           # создатель — член команды
    return {"id": tid}


@app.post("/api/teams/{tid}/members")
def add_member(tid: str, body: dict = Body(...)):
    ctl.ensure_user(body["user_id"], body.get("name"))
    ctl.add_member(body["user_id"], tid)
    return {"ok": True}


# ---------------- графы ----------------
@app.get("/api/graphs")
def list_graphs(x_user: str | None = Header(None)):
    return {"graphs": ctl.list_graphs(_user(x_user))}


@app.post("/api/graphs")
def create_graph(body: dict = Body(...), x_user: str | None = Header(None)):
    _user(x_user)
    return {"id": ctl.create_graph(body["name"])}   # графы общие, без владельца


@app.post("/api/graphs/{gid}/grant")
def grant(gid: str, body: dict = Body(...), x_user: str | None = Header(None)):
    _require(gid, _user(x_user))
    ctl.grant(gid, team=body.get("team") or None, user=body.get("user") or None)
    return {"ok": True}


@app.post("/api/graphs/{gid}/docs")
def upload_doc(gid: str, bg: BackgroundTasks, file: UploadFile = File(...),
               x_user: str | None = Header(None)):
    _require(gid, _user(x_user))
    dest_dir = _UPLOADS / gid
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    job = {"file": file.filename, "state": "queued"}
    JOBS.setdefault(gid, []).append(job)
    bg.add_task(_run_ingest, gid, str(dest), file.filename, job)
    return {"queued": file.filename}


def _run_ingest(gid: str, path: str, name: str, job: dict) -> None:
    job["state"] = "processing"
    try:
        if not name.lower().endswith(".pdf"):
            job.update(state="unsupported", error="сегодня поддержан только PDF")
            return
        job.update(service.ingest_pdf(gid, path, paper_ref=name), state="done")
    except Exception as e:
        job.update(state="error", error=repr(e))
        traceback.print_exc()


@app.get("/api/graphs/{gid}/status")
def status(gid: str, x_user: str | None = Header(None)):
    _require(gid, _user(x_user))
    return {"jobs": JOBS.get(gid, [])}


@app.post("/api/graphs/{gid}/ask")
def ask(gid: str, body: dict = Body(...), x_user: str | None = Header(None)):
    _require(gid, _user(x_user))
    q = (body.get("question") or "").strip()
    if not q:
        raise HTTPException(400, "пустой вопрос")
    try:
        return service.ask(gid, q, k=int(body.get("k", 16)))
    except Exception as e:
        raise HTTPException(500, f"ошибка ретрива: {e!r}")


@app.get("/api/graphs/{gid}/stats")
def graph_stats(gid: str, x_user: str | None = Header(None)):
    _require(gid, _user(x_user))
    return service.graph_stats(gid)


@app.get("/api/graphs/{gid}/docs/{paper_ref:path}")
def get_doc(gid: str, paper_ref: str, x_user: str | None = Header(None)):
    _require(gid, _user(x_user))
    d = service.get_doc(gid, paper_ref)
    if not d:
        raise HTTPException(404, "документ не найден")
    return d
