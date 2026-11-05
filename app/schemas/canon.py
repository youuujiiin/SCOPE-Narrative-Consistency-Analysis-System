"""캐논 조회 응답 스키마 (계약서 4장).

탭(view)마다 형태가 다르다. 평면 리스트 탭은 items, 인물 탭은 nodes/edges.
라우터에서 exclude_none으로 직렬화해 탭별 형태를 맞춘다.
"""
from __future__ import annotations

from pydantic import BaseModel


class CanonOut(BaseModel):
    view: str
    items: list[dict] | None = None   # worldview/timeline/spaces/events/foreshadowing
    nodes: list[dict] | None = None   # characters
    edges: list[dict] | None = None   # characters
