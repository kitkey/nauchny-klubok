"""Шаги LLM: единая точка «логический шаг -> модель + промпт», + generic run_step.

Схему вывода передаёт вызывающий этап (во избежание циклических импортов): run_step(..., schema=...).
Модель: STEP_CONFIG[name].model (по умолчанию deepseek), переопределяется Config.models[name].
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ..context import Deps

DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
DEFAULT_MAX_TOKENS = 8000   # кап выхода: ловит «разнос» генерации (resolve выдавал 45k-мусор → 30 мин на вызов)


@dataclass(frozen=True)
class Step:
    prompt: str
    model: str = DEFAULT_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS


STEP_CONFIG: dict[str, Step] = {
    "roles.tag": Step(prompt="roles/tag"),
    "roles.section": Step(prompt="roles/section"),
    "extract.frame": Step(prompt="extract/frame", max_tokens=16000),   # запас под плотные чанки, чтоб не обрезать вывод (IncompleteOutput)
    "extract.define": Step(prompt="extract/define"),
    "extract.binary": Step(prompt="extract/binary"),
    "extract.assemble": Step(prompt="extract/assemble"),
    "link.dedup": Step(prompt="link/dedup"),
    "link.dedup_facts": Step(prompt="link/dedup_facts"),
    "link.resolve": Step(prompt="link/resolve"),
    "link.canon_rel": Step(prompt="link/canon_rel"),
    "link.stitch": Step(prompt="link/stitch"),
    "concept.define": Step(prompt="concept/define"),
    "concept.link": Step(prompt="concept/link"),
    "concept.hierarchy": Step(prompt="concept/hierarchy"),
    "verify.check": Step(prompt="verify/check"),
    "retrieve.extract": Step(prompt="retrieve/extract"),
    "retrieve.decompose": Step(prompt="retrieve/decompose"),
    "retrieve.answer": Step(prompt="retrieve/answer", max_tokens=2000),
}


def run_step(deps: Deps, name: str, schema: Any | None = None, **variables) -> Any:
    step = STEP_CONFIG[name]
    model = deps.cfg.models.get(name, step.model)
    system, user = deps.prompts.render_pair(step.prompt, **variables)
    tracer = getattr(deps, "tracer", None)
    t = time.perf_counter()
    try:
        resp = deps.llm.complete(user, system=system, model=model, schema=schema,
                                 max_tokens=step.max_tokens)
    except Exception as e:
        if tracer is not None:
            tracer.llm_call(step=name, model=model, system=system, user=user, response=None,
                            latency=time.perf_counter() - t, ok=False, error=repr(e))
        raise
    if tracer is not None:
        usage = deps.llm.pop_usage() if hasattr(deps.llm, "pop_usage") else getattr(deps.llm, "last_usage", None)
        tracer.llm_call(step=name, model=model, system=system, user=user, response=resp,
                        latency=time.perf_counter() - t, usage=usage)
    return resp
