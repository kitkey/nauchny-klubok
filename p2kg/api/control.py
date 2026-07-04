"""Control-plane: вложенные команды, пользователи, графы, гранты доступа.

Модель доступа. Команды образуют дерево (team.parent_id). Граф принадлежит команде. Доступ к графу:
члены команды-владельца И члены её родительских команд (орг выше видит нижестоящие), плюс явные гранты
(команде или пользователю). Внутри команды доступ у всех её членов. Аутентификации нет — «текущий юзер»
приходит заголовком (задел под RBAC).

MemControl — вся логика в памяти (тесты/локально). MongoControl — та же логика + запись в Mongo.
"""
from __future__ import annotations

import uuid


def _id() -> str:
    return uuid.uuid4().hex[:12]


class MemControl:
    def __init__(self) -> None:
        self.teams: dict = {}      # id -> {id, name, parent_id}
        self.users: dict = {}      # id -> {id, name}
        self.members: dict = {}    # user_id -> set(team_id)
        self.graphs: dict = {}     # id -> {id, name, owner_team}
        self.grants: dict = {}     # graph_id -> {"teams": set, "users": set}

    # --- точки записи (MongoControl их переопределяет для персистентности) ---
    def _put_team(self, t: dict) -> None:
        self.teams[t["id"]] = t

    def _put_user(self, u: dict) -> None:
        self.users[u["id"]] = u

    def _put_member(self, uid: str, tid: str) -> None:
        self.members.setdefault(uid, set()).add(tid)

    def _put_graph(self, g: dict) -> None:
        self.graphs[g["id"]] = g

    def _put_grant(self, gid: str, teams: set, users: set) -> None:
        self.grants[gid] = {"teams": set(teams), "users": set(users)}

    # --- команды / пользователи ---
    def create_team(self, name: str, parent_id: str | None = None) -> str:
        tid = _id()
        self._put_team({"id": tid, "name": name, "parent_id": parent_id})
        return tid

    def create_user(self, name: str, uid: str | None = None) -> str:
        uid = uid or _id()
        self._put_user({"id": uid, "name": name})
        return uid

    def add_member(self, uid: str, tid: str) -> None:
        self._put_member(uid, tid)

    def ensure_user(self, uid: str, name: str | None = None) -> None:
        if uid not in self.users:
            self.create_user(name or uid, uid=uid)

    # --- графы / гранты ---
    def create_graph(self, name: str, owner_team: str = "public") -> str:
        gid = _id()
        self._put_graph({"id": gid, "name": name, "owner_team": owner_team})
        return gid

    def grant(self, gid: str, *, team: str | None = None, user: str | None = None) -> None:
        cur = self.grants.get(gid, {"teams": set(), "users": set()})
        teams, users = set(cur["teams"]), set(cur["users"])
        if team:
            teams.add(team)
        if user:
            users.add(user)
        self._put_grant(gid, teams, users)

    # --- доступ ---
    def _ancestors(self, tid: str) -> set:
        out: set = set()
        cur = self.teams.get(tid, {}).get("parent_id")
        while cur and cur not in out:
            out.add(cur)
            cur = self.teams.get(cur, {}).get("parent_id")
        return out

    def user_teams(self, uid: str) -> set:
        return set(self.members.get(uid, set()))

    def can_access(self, uid: str, gid: str) -> bool:
        return gid in self.graphs          # разграничение доступа убрано (по ТЗ необязательно): графы общие

    def list_graphs(self, uid: str) -> list:
        return list(self.graphs.values())

    def teams_tree(self) -> list:
        return list(self.teams.values())


class MongoControl(MemControl):
    """Та же логика, но команды/юзеры/графы/гранты персистятся в Mongo (write-through, load-on-init)."""

    def __init__(self, uri: str, db: str = "p2kg") -> None:
        super().__init__()
        from pymongo import MongoClient
        self._db = MongoClient(uri, serverSelectionTimeoutMS=1500)[db]
        for t in self._db.ctl_teams.find():
            self.teams[t["id"]] = {"id": t["id"], "name": t["name"], "parent_id": t.get("parent_id")}
        for u in self._db.ctl_users.find():
            self.users[u["id"]] = {"id": u["id"], "name": u["name"]}
        for m in self._db.ctl_members.find():
            self.members.setdefault(m["user_id"], set()).add(m["team_id"])
        for g in self._db.ctl_graphs.find():
            self.graphs[g["id"]] = {"id": g["id"], "name": g["name"], "owner_team": g["owner_team"]}
        for gr in self._db.ctl_grants.find():
            self.grants[gr["graph_id"]] = {"teams": set(gr.get("teams", [])),
                                           "users": set(gr.get("users", []))}

    def _put_team(self, t: dict) -> None:
        super()._put_team(t)
        self._db.ctl_teams.replace_one({"id": t["id"]}, t, upsert=True)

    def _put_user(self, u: dict) -> None:
        super()._put_user(u)
        self._db.ctl_users.replace_one({"id": u["id"]}, u, upsert=True)

    def _put_member(self, uid: str, tid: str) -> None:
        super()._put_member(uid, tid)
        self._db.ctl_members.replace_one({"user_id": uid, "team_id": tid},
                                         {"user_id": uid, "team_id": tid}, upsert=True)

    def _put_graph(self, g: dict) -> None:
        super()._put_graph(g)
        self._db.ctl_graphs.replace_one({"id": g["id"]}, g, upsert=True)

    def _put_grant(self, gid: str, teams: set, users: set) -> None:
        super()._put_grant(gid, teams, users)
        self._db.ctl_grants.replace_one(
            {"graph_id": gid}, {"graph_id": gid, "teams": list(teams), "users": list(users)}, upsert=True)
