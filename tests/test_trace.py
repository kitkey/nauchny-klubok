import json

from p2kg.config import Config
from p2kg.context import Deps
from p2kg.llm.prompts import PromptManager
from p2kg.llm.steps import run_step
from p2kg.trace import JsonlTracer, NullTracer


def _read(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def test_jsonl_tracer_records_run_and_calls(tmp_path):
    p = str(tmp_path / "r.jsonl")
    tr = JsonlTracer(p, run_id="testrun")
    tr.start_paper("paperA")
    with tr.stage("paperA", "s2_roles"):
        pass
    tr.llm_call(step="roles.tag", model="m", system="sys", user="usr",
                response=["x"], latency=0.1,
                usage={"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60, "cost": 0.0002})
    tr.end_paper("paperA", facts=3)

    lines = _read(p)
    colls = {l["_coll"] for l in lines}
    assert {"runs", "llm_calls"} <= colls
    call = next(l for l in lines if l["_coll"] == "llm_calls")
    assert call["step"] == "roles.tag" and call["run_id"] == "testrun"
    assert call["paper_ref"] == "paperA" and call["seq"] == 1 and call["ok"] is True
    assert call["prompt_tokens"] == 50 and call["cost"] == 0.0002
    end = next(l for l in lines if l.get("event") == "paper_end")
    assert end["facts"] == 3 and "duration_s" in end
    assert end["cost"] == 0.0002 and end["prompt_tokens"] == 50 and end["llm_calls"] == 1
    stage = next(l for l in lines if l.get("event") == "stage")
    assert stage["stage"] == "s2_roles" and "duration_s" in stage


def test_run_step_logs_to_tracer(tmp_path):
    class FakeLLM:
        last_usage = {"prompt_tokens": 120, "completion_tokens": 25, "total_tokens": 145, "cost": 0.0003}

        def complete(self, user, *, system=None, model, schema=None, **kw):
            return "ok"

    p = str(tmp_path / "calls.jsonl")
    tr = JsonlTracer(p, run_id="r1")
    deps = Deps(llm=FakeLLM(), embed=None, prompts=PromptManager(), cfg=Config(),
                graph=None, docs=None, tracer=tr)
    tr.start_paper("pp")
    run_step(deps, "roles.tag", schema=None, chunk_text="HELLOWORLD",
             roles=["method"], hint="method")
    call = next(l for l in _read(p) if l["_coll"] == "llm_calls")
    assert call["step"] == "roles.tag" and "HELLOWORLD" in call["user"]
    assert call["model"] == "deepseek/deepseek-v4-flash" and call["ok"] is True
    assert call["prompt_tokens"] == 120 and call["cost"] == 0.0003


def test_default_deps_tracer_is_null():
    deps = Deps(llm=None, embed=None, prompts=None, cfg=Config(), graph=None, docs=None)
    assert isinstance(deps.tracer, NullTracer)
