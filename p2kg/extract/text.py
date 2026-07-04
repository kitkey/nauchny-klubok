"""S3: извлечение n-арных фреймов из ТЕКСТОВОГО чанка (v1 — один extract.frame-вызов)."""
from __future__ import annotations

from ..llm.steps import run_step
from ..schema import FrameType
from ._common import LocalGraph, _FrameOut, build_from_frames

_FRAMES = [
    FrameType.MATERIAL_MEASUREMENT.value,
    FrameType.SYNTHESIS_PROCEDURE.value,
    FrameType.CLAIM_FACT.value,
    FrameType.HYPOTHESIS_FACT.value,
]


def _extract_text(deps, chunk, units, paper) -> LocalGraph:
    frames = run_step(deps, "extract.frame", schema=list[_FrameOut],
                      chunk_text=chunk.text, frames=_FRAMES,
                      language_code=deps.cfg.output_language) or []
    return build_from_frames(frames, paper, chunk.span)
