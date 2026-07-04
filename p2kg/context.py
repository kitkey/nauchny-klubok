"""Контекст прогона: Deps (immutable зависимости) + ArticleState (состояние по статье).

Этапы — чистые функции (Deps, ArticleState) -> ArticleState. Паттерн PydanticAI/OpenAI-Agents
без фреймворка: immutable-депсы аргументом, типизированное состояние прогона.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from pydantic import BaseModel, Field

from .config import Config
from .schema import Chunk, Edge, Entity, Fact, Paper, Unit
from .trace import NullTracer

# Протоколы зависимостей — конкретные реализации в M3 (llm/embed/prompts) и M5 (сторы).


class LLMClient(Protocol):
    ...


class Embedder(Protocol):
    ...


class PromptManager(Protocol):
    ...


class GraphStore(Protocol):
    ...


class DocStore(Protocol):
    ...


@dataclass(frozen=True)
class Deps:
    llm: LLMClient
    embed: Embedder
    prompts: PromptManager
    cfg: Config
    graph: GraphStore
    docs: DocStore
    tracer: object = field(default_factory=NullTracer)   # см. p2kg/trace.py


class ArticleState(BaseModel):
    paper_ref: str
    paper: Paper | None = None
    chunks: list[Chunk] = Field(default_factory=list)
    units: list[Unit] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    stage_status: dict[str, str] = Field(default_factory=dict)


Stage = Callable[[Deps, "ArticleState"], "ArticleState"]


def run_pipeline(deps: Deps, paper_ref: str, stages: list[Stage]) -> ArticleState:
    st = ArticleState(paper_ref=paper_ref)
    for stage in stages:
        st = stage(deps, st)
    return st
