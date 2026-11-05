from __future__ import annotations

from datetime import datetime, timezone
from .math_utils import Score, cosine_similarity, weighted_average

PARTICIPANT_OVERLAP_WEIGHT = 0.80
MAIN_ACTOR_WEIGHT = 0.20


def semantic_feature(a_emb: dict, b_emb: dict) -> Score:
    return cosine_similarity(a_emb.get('summary_embedding'), b_emb.get('summary_embedding'))


def action_feature(a_emb: dict, b_emb: dict) -> Score:
    return cosine_similarity(a_emb.get('title_embedding'), b_emb.get('title_embedding'))


def causal_feature(a_emb: dict, b_emb: dict) -> Score:
    scores = [
        cosine_similarity(a_emb.get('cause_embedding'), b_emb.get('result_embedding')),
        cosine_similarity(b_emb.get('cause_embedding'), a_emb.get('result_embedding')),
    ]
    valid = [score for score in scores if score is not None]
    return max(valid) if valid else None


def participant_feature(a_event: dict, b_event: dict) -> Score:
    a_ids = set(a_event.get('participant_character_ids') or [])
    b_ids = set(b_event.get('participant_character_ids') or [])
    union = a_ids | b_ids
    overlap = len(a_ids & b_ids) / len(union) if union else None
    a_main = a_event.get('main_actor_character_id')
    b_main = b_event.get('main_actor_character_id')
    main = (1.0 if a_main == b_main else 0.0) if a_main is not None and b_main is not None else None
    return weighted_average([(overlap, PARTICIPANT_OVERLAP_WEIGHT), (main, MAIN_ACTOR_WEIGHT)])


def _timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def time_feature(a_time: dict | None, b_time: dict | None) -> Score:
    if not a_time or not b_time:
        return 0.5
    a_date = _timestamp(a_time.get('story_time_iso') or a_time.get('story_datetime') or a_time.get('absolute_datetime'))
    b_date = _timestamp(b_time.get('story_time_iso') or b_time.get('story_datetime') or b_time.get('absolute_datetime'))
    if a_date is not None and b_date is not None:
        days = abs((a_date - b_date).total_seconds()) / 86400.0
        return 1.0 / (1.0 + days / 365.0)
    a_day = a_time.get('story_day_offset')
    b_day = b_time.get('story_day_offset')
    a_axis = a_time.get('story_timeline_id')
    b_axis = b_time.get('story_timeline_id')
    if a_axis is not None and a_axis == b_axis and isinstance(a_day, (int, float)) and not isinstance(a_day, bool) and isinstance(b_day, (int, float)) and not isinstance(b_day, bool):
        return 1.0 / (1.0 + abs(a_day - b_day) / 365.0)
    return 0.5


def _location_id(item):
    return item.get('place_id') or item.get('location_id') if item else None


def _parent_id(item):
    return item.get('parent_place_id') or item.get('parent_location_id')


def _ancestors(node_id, nodes):
    distance = 0
    seen = set()
    result = {}
    while node_id is not None and node_id not in seen:
        seen.add(node_id)
        result[node_id] = distance
        node = nodes.get(node_id)
        if node is None:
            break
        node_id = _parent_id(node)
        distance += 1
    return result


def location_feature(a_location: dict | None, b_location: dict | None, *, locations: dict | None = None, same_place_candidates=None) -> Score:
    if not a_location or not b_location:
        return 0.5
    a_id = _location_id(a_location)
    b_id = _location_id(b_location)
    nodes = dict(locations or {})
    if a_id is not None:
        nodes[a_id] = a_location
    if b_id is not None:
        nodes[b_id] = b_location
    base = 0.5
    if a_id is not None and b_id is not None:
        if a_id == b_id:
            base = 1.0
        else:
            a_ancestors = _ancestors(a_id, nodes)
            b_ancestors = _ancestors(b_id, nodes)
            common = a_ancestors.keys() & b_ancestors.keys()
            if common:
                distance = min(a_ancestors[node] + b_ancestors[node] for node in common)
                base = 1.0 / (1.0 + distance / 2.0)
            elif a_location.get('tree_complete') is True and b_location.get('tree_complete') is True and all(_parent_id(nodes[node]) in nodes or _parent_id(nodes[node]) is None for node in set(a_ancestors) | set(b_ancestors) if node in nodes):
                base = 0.25
    candidate_pairs = same_place_candidates or []
    for candidate in candidate_pairs:
        if isinstance(candidate, dict):
            left = candidate.get('place_id_a') or candidate.get('location_id_a')
            right = candidate.get('place_id_b') or candidate.get('location_id_b')
        elif isinstance(candidate, (list, tuple)) and len(candidate) == 2:
            left, right = candidate
        else:
            continue
        if {left, right} == {a_id, b_id} and a_id is not None and b_id is not None:
            return max(base, 0.75)
    return base
