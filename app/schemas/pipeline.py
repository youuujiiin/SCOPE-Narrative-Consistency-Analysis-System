"""파이프라인 연결 점검 응답."""
from __future__ import annotations

from pydantic import BaseModel, Field


class PipelineHealthOut(BaseModel):
    """GET /pipeline/health. 연결 실패도 200 + ok=false 로 내려준다(원인은 message)."""

    ok: bool
    mode: str  # fake | remote | local
    message: str = ""
    info: dict = Field(default_factory=dict)
