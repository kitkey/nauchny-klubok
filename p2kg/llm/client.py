"""LLMClient — обёртка OpenRouter (OpenAI-совместимый) + instructor для structured output.

Mode.MD_JSON — устойчивее на deepseek/gemma (нативный JSON-schema у них неровный).
Реальные вызовы требуют OPENROUTER_API_KEY; в юнит-тестах используется фейковый клиент
(любой объект с .complete(prompt, *, model, schema)).
"""
from __future__ import annotations

import os
import threading
from typing import Any, Callable, get_args, get_origin

from pydantic import create_model

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
# жёсткий wall-clock на ОДИН вызов. SDK/httpx-таймаут (60с) НЕ срабатывает на коннектах с keep-alive:
# такие вызовы висели по часу, выдав 0 токенов. 240с покрывает легитимную генерацию 8k-выхода (~200с)
# и нормальные resolve (≤194с), но рубит мёртвые коннекты.
CALL_TIMEOUT_S = 240.0


class LLMClient:
    def __init__(self, api_key: str, base_url: str = OPENROUTER_BASE,
                 provider_order: list[str] | None = None, max_concurrency: int = 8,
                 call_timeout: float = CALL_TIMEOUT_S, openrouter: bool = True) -> None:
        import instructor
        from openai import OpenAI

        self._openrouter = openrouter   # False -> Yandex/другой OpenAI-совместимый: без OpenRouter-extra_body
        self._raw = OpenAI(api_key=api_key, base_url=base_url, timeout=240.0, max_retries=1)
        self._ix = instructor.from_openai(self._raw, mode=instructor.Mode.MD_JSON)
        self._usage_tl = threading.local()   # токены+cost последнего вызова (per-thread, для конкурентности)
        self._provider = provider_order or []   # порядок провайдеров OpenRouter (строгий приоритет + фолбэк)
        self._call_timeout = call_timeout
        # глобальный кап одновременных запросов: статьи×pmap иначе забивают провайдера -> троттлинг/таймауты
        self._sem = threading.BoundedSemaphore(max_concurrency)

    @classmethod
    def from_env(cls, provider_order: list[str] | None = None) -> "LLMClient":
        return cls(api_key=os.environ["OPENROUTER_API_KEY"], provider_order=provider_order)

    def _run_bounded(self, fn: Callable):
        """Выполнить fn() в daemon-потоке с жёстким лимитом self._call_timeout.
        Зачем: SDK/httpx read-таймаут не срабатывает, если провайдер шлёт keep-alive байты, ничего не
        генерируя — вызов висит часами. Поток — daemon, поэтому повисший коннект не держит выход процесса."""
        box: dict = {}

        def _worker():
            try:
                box["r"] = fn()
            except BaseException as e:   # noqa: BLE001 — пробрасываем наружу как есть
                box["e"] = e

        th = threading.Thread(target=_worker, daemon=True)
        th.start()
        th.join(self._call_timeout)
        if th.is_alive():   # не уложились -> бросаем коннект (daemon-поток умрёт вместе с процессом)
            raise TimeoutError(f"LLM-вызов завис >{self._call_timeout:.0f}s — бросаем (вероятно мёртвый коннект)")
        if "e" in box:
            raise box["e"]
        return box.get("r")

    def _extra_body(self) -> dict:
        if not self._openrouter:
            return {"reasoning_effort": "none"}   # Yandex: гасим reasoning DeepSeek (иначе CoT -> таймаут)
        eb: dict = {"usage": {"include": True},   # вернуть cost + кэш-инфо
                    # ВЫКЛ reasoning: deepseek-v4-flash лил ~90% выхода в CoT (roles.tag: 14035 ток, из них
                    # ~12.7k reasoning, instructor его выкидывает) -> платили и ждали (291с) зря. Задачи
                    # структурные, цепочка размышлений не нужна. Замер: completion 788->80, latency в разы ниже.
                    "reasoning": {"enabled": False}}
        if self._provider:   # order=строгий приоритет: 1-й провайдер берёт всё, остальные — фолбэк
            eb["provider"] = {"order": list(self._provider), "allow_fallbacks": True}
        return eb

    @staticmethod
    def _usage_dict(completion) -> dict | None:
        u = getattr(completion, "usage", None)
        if u is None:
            return None
        return {
            "prompt_tokens": getattr(u, "prompt_tokens", None),
            "completion_tokens": getattr(u, "completion_tokens", None),
            "total_tokens": getattr(u, "total_tokens", None),
            "cost": getattr(u, "cost", None),   # OpenRouter $ (если usage.include)
            "provider": getattr(completion, "provider", None),   # какой провайдер OpenRouter обслужил
        }

    def _set_usage(self, u: dict | None) -> None:
        self._usage_tl.value = u

    def pop_usage(self) -> dict | None:
        return getattr(self._usage_tl, "value", None)

    def _usage_of(self, res, comp) -> dict | None:
        """usage из completion, а если там нет — из res._raw_response (фикс для одиночных схем, напр. stitch)."""
        return self._usage_dict(comp) or self._usage_dict(getattr(res, "_raw_response", None))

    def _structured(self, *, model, messages, response_model, temperature, max_tokens):
        """(result, raw_completion) — raw нужен для usage/cost.

        max_retries=0 -> instructor делает РОВНО один запрос и НЕ дозапрашивает с подмешиванием своего
        прошлого (огромного) вывода обратно в промпт. Раньше при max_retries=1 один reask на провалившийся
        45k-выход раздувал вход следующего запроса до 54k токенов. Один ЧИСТЫЙ ретрай (теми же исходными
        messages, без аккумуляции) на транзиентный сбой парсинга делаем сами ниже."""
        eb = self._extra_body()

        def _once():
            try:
                return self._ix.chat.completions.create_with_completion(
                    model=model, messages=messages, response_model=response_model,
                    temperature=temperature, max_tokens=max_tokens, extra_body=eb, max_retries=0)
            except (AttributeError, TypeError):
                res = self._ix.chat.completions.create(
                    model=model, messages=messages, response_model=response_model,
                    temperature=temperature, max_tokens=max_tokens, extra_body=eb, max_retries=0)
                return res, getattr(res, "_raw_response", None)

        with self._sem:   # глобальный кап одновременных запросов на весь процесс
            try:
                return self._run_bounded(_once)
            except TimeoutError:
                raise   # таймаут НЕ ретраим (удвоило бы ожидание) — pmap проглотит -> None, шаг деградирует мягко
            except Exception:
                return self._run_bounded(_once)   # чистый ретрай: ТЕ ЖЕ messages, без подмешивания прошлого вывода

    def complete(self, user: str, *, system: str | None = None, model: str,
                 schema: Any | None = None, temperature: float = 0.0,
                 max_tokens: int | None = None) -> Any:
        messages = ([{"role": "system", "content": system}] if system else []) \
            + [{"role": "user", "content": user}]
        eb = self._extra_body()   # usage.include + (опц.) пин провайдера
        if schema is None:
            with self._sem:
                r = self._run_bounded(lambda: self._raw.chat.completions.create(
                    model=model, messages=messages, temperature=temperature,
                    max_tokens=max_tokens, extra_body=eb,
                ))
            self._set_usage(self._usage_dict(r))
            return r.choices[0].message.content
        if get_origin(schema) is list:   # instructor не ест list[...] напрямую — оборачиваем
            item = get_args(schema)[0]
            wrapper = create_model("_ItemsWrapper", items=(list[item], ...))
            res, comp = self._structured(model=model, messages=messages, response_model=wrapper,
                                         temperature=temperature, max_tokens=max_tokens)
            self._set_usage(self._usage_of(res, comp))
            return list(res.items)
        res, comp = self._structured(model=model, messages=messages, response_model=schema,
                                     temperature=temperature, max_tokens=max_tokens)
        self._set_usage(self._usage_of(res, comp))   # БЫЛ БАГ: писалось в self.last_usage, а run_step читает pop_usage()
        return res
