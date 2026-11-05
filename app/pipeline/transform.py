"""LLM 시각화 JSON(prompt_result_1 포맷) → CanonDelta 변환.

LLM 파이프라인은 회차 분석 결과를 시각화 친화적인 rich JSON
(worldview_rules / characters / events / times / locations, 각 항목에
source_text·certainty 포함)으로 내려준다. 몸통(캐논 병합·모순 대조)은
CanonDelta 스키마를 쓰므로 여기서 단방향 변환한다.

원본 JSON은 정보가 더 많으므로(traits, source_text, certainty…)
변환과 별개로 analysis_results.raw_output에 통째로 보존되고,
GET /projects/{id}/chapters/{no}/visual 로 프론트 시각화에 내려간다.

entity_key는 LLM이 준 안정적 ID(rule_id/character_id/...)를 그대로 써서
같은 회차를 재분석해도 캐논 병합이 멱등이 되게 한다.
"""
from __future__ import annotations

import hashlib

from app.pipeline.interface import (
    CanonDelta,
    CharacterDelta,
    EventDelta,
    RelationDelta,
    SpaceDelta,
    TimelineDelta,
    WorldviewDelta,
)

# rich JSON을 식별하는 최상위 키 (하나라도 있으면 시각화 포맷으로 간주)
_VISUAL_KEYS = ("worldview_rules", "characters", "events", "times", "locations")


def looks_like_visual_json(data: dict) -> bool:
    """페이로드가 prompt_result_1 포맷(rich JSON)인지 판별한다."""
    return isinstance(data, dict) and any(k in data for k in _VISUAL_KEYS)


def _key(prefix: str, given: str | None, fallback_text: str) -> str:
    """LLM이 준 ID를 우선 쓰고, 없으면 내용 해시로 안정적 키를 만든다."""
    if given:
        return given
    digest = hashlib.sha1(fallback_text.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def visual_to_canon_delta(visual: dict) -> CanonDelta:
    """rich JSON → CanonDelta. 몸통이 아는 필드만 추리고 나머지는 attrs에 담는다."""
    worldview = [
        WorldviewDelta(
            entity_key=_key("rule", r.get("rule_id"), r.get("content", "")),
            item=r.get("content", ""),
            detail=r.get("description"),
        )
        for r in visual.get("worldview_rules", [])
        if r.get("content")
    ]

    characters: list[CharacterDelta] = []
    relations: list[RelationDelta] = []
    for c in visual.get("characters", []):
        if not c.get("name"):
            continue
        char_key = _key("char", c.get("character_id"), c["name"])
        attrs: dict = {}
        if c.get("description"):
            attrs["description"] = c["description"]
        if c.get("aliases"):
            attrs["aliases"] = c["aliases"]
        if isinstance(c.get("traits"), list):
            attrs["traits"] = [t.get("trait") for t in c["traits"] if isinstance(t, dict) and t.get("trait")]
        characters.append(
            CharacterDelta(entity_key=char_key, name=c["name"], attrs=attrs or None)
        )
        for rel in (c.get("relationships") or []):
            if not isinstance(rel, dict):
                continue
            target = rel.get("target_character_id")
            if not target:
                continue
            relations.append(
                RelationDelta(
                    entity_key=f"{char_key}->{target}",
                    from_char=char_key,
                    to_char=target,
                    relation=rel.get("relationship_type") or rel.get("description"),
                )
            )

    events = [
        EventDelta(
            entity_key=_key("event", e.get("event_id"), e.get("title", "")),
            label=e.get("title", ""),
            order_index=e.get("order", i + 1),
            summary=e.get("summary"),
            cause=e.get("cause"),
            result=e.get("result"),
            participant_character_ids=e.get("participant_character_ids"),
            main_actor_character_id=e.get("main_actor_character_id"),
            time_id=e.get("time_id"),
            location_id=e.get("location_id"),
            source_quotes=e.get("source_quotes"),
        )
        for i, e in enumerate(visual.get("events", []))
        if e.get("title")
    ]

    timeline = [
        TimelineDelta(
            entity_key=_key("time", t.get("time_id"), t.get("expression", "")),
            time_value=t.get("expression"),
            order_index=i + 1,
        )
        for i, t in enumerate(visual.get("times", []))
        if t.get("expression")
    ]

    spaces = [
        SpaceDelta(
            entity_key=_key("loc", s.get("location_id"), s.get("name", "")),
            place=s.get("name"),
            attrs={"description": s["description"]} if s.get("description") else None,
        )
        for s in visual.get("locations", [])
        if s.get("name")
    ]

    return CanonDelta(
        worldview=worldview,
        characters=characters,
        relations=relations,
        events=events,
        timeline=timeline,
        spaces=spaces,
    )
