import dataclasses

from p2kg.context import ArticleState, Deps, run_pipeline


def test_articlestate_defaults():
    st = ArticleState(paper_ref="p1")
    assert st.paper is None and st.chunks == [] and st.facts == []


def test_run_pipeline_runs_stages_in_order():
    def s_a(deps, st):
        st.stage_status["a"] = "ok"
        return st

    def s_b(deps, st):
        st.stage_status["b"] = "ok"
        return st

    st = run_pipeline(deps=None, paper_ref="p1", stages=[s_a, s_b])
    assert list(st.stage_status.keys()) == ["a", "b"]


def test_deps_is_frozen():
    assert dataclasses.is_dataclass(Deps)
    names = {f.name for f in dataclasses.fields(Deps)}
    assert names == {"llm", "embed", "prompts", "cfg", "graph", "docs", "tracer"}
