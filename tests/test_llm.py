import importlib

from p2kg.config import Config
from p2kg.context import Deps
from p2kg.llm.prompts import PromptManager
from p2kg.llm.steps import STEP_CONFIG, run_step


class FakeLLM:
    def __init__(self, ret):
        self.ret = ret
        self.calls = []

    def complete(self, prompt, *, model, schema=None, **kw):
        self.calls.append({"prompt": prompt, "model": model, "schema": schema})
        return self.ret


def _deps(ret):
    return Deps(llm=FakeLLM(ret), embed=None, prompts=PromptManager(),
                cfg=Config(), graph=None, docs=None)


def test_prompt_render_roles_tag():
    system, user = PromptManager().render_pair(
        "roles/tag", chunk_text="Hello materials world",
        roles=["method", "result"], hint="method")
    assert "Hello materials world" in user and "method" in system


def test_run_step_renders_and_calls_llm():
    deps = _deps(["RESULT"])
    out = run_step(deps, "roles.tag", schema=None, chunk_text="X", roles=["method"])
    assert out == ["RESULT"]
    assert deps.llm.calls[0]["model"] == "deepseek/deepseek-v4-flash"
    assert "X" in deps.llm.calls[0]["prompt"]


def test_config_overrides_model():
    deps = Deps(llm=FakeLLM("ok"), embed=None, prompts=PromptManager(),
                cfg=Config(models={"roles.tag": "google/gemma-2-9b-it"}),
                graph=None, docs=None)
    run_step(deps, "roles.tag", chunk_text="X", roles=["method"])
    assert deps.llm.calls[0]["model"] == "google/gemma-2-9b-it"


def test_step_config_has_core_steps():
    for name in ("roles.tag", "extract.frame", "link.dedup", "verify.check"):
        assert name in STEP_CONFIG


def test_client_module_importable():
    m = importlib.import_module("p2kg.llm.client")
    assert hasattr(m, "LLMClient")


def test_provider_pin_in_extra_body():
    from p2kg.llm.client import LLMClient
    c = LLMClient("k", provider_order=["Wafer"])
    eb = c._extra_body()
    assert eb["usage"]["include"] is True
    assert eb["provider"]["order"] == ["Wafer"] and eb["provider"]["allow_fallbacks"] is True
    assert "provider" not in LLMClient("k")._extra_body()
