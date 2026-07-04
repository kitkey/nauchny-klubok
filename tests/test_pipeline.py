from pathlib import Path
from typing import get_origin

from p2kg.config import Config
from p2kg.context import Deps
from p2kg.embedder import HashEmbedder
from p2kg.llm.prompts import PromptManager
from p2kg.pipeline import process_source
from p2kg.stores.docstore import InMemoryDocStore
from p2kg.stores.graphstore import InMemoryGraph

FIX = Path(__file__).parent / "fixtures" / "sample.pdf"


class FakeLLM:
    """Возвращает по схеме: list-схема -> [], BaseModel -> дефолтный экземпляр, None -> ''."""

    def complete(self, prompt, *, model, schema=None, **kw):
        if schema is None:
            return ""
        if get_origin(schema) is list:
            return []
        try:
            return schema()
        except Exception:
            return None


def _deps():
    return Deps(llm=FakeLLM(), embed=HashEmbedder(), prompts=PromptManager(), cfg=Config(),
                graph=InMemoryGraph(), docs=InMemoryDocStore())


def test_pipeline_end_to_end_on_pdf():
    deps = _deps()
    st = process_source(deps, str(FIX))
    for stage in ("s0_ingest", "s1_chunk", "s2_roles", "s3_extract", "s4_link", "s5_verify", "persist"):
        assert st.stage_status.get(stage) == "ok", f"stage {stage} not ok"
    assert st.paper is not None and len(st.chunks) > 0
    # артефакт записан в DocStore
    assert deps.docs.get_paper(st.paper_ref) is not None


def test_pipeline_paper_ref_override():
    deps = _deps()
    st = process_source(deps, str(FIX), paper_ref="arxiv:2502.06472v1")
    assert st.paper_ref == "arxiv:2502.06472v1"
