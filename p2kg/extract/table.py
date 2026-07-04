"""S3: извлечение из ТАБЛИЧНОГО чанка — LLM трактует таблицу, веером отдаёт MaterialMeasurement-фреймы."""
from __future__ import annotations

from ..llm.steps import run_step
from ._common import LocalGraph, _FrameOut, build_from_frames


def _extract_table(deps, chunk, paper) -> LocalGraph:
    frames = run_step(deps, "extract.frame", schema=list[_FrameOut],
                      chunk_text=chunk.text, frames=["MaterialMeasurement"],
                      language_code=deps.cfg.output_language) or []
    return build_from_frames(frames, paper, chunk.span, source="table")
