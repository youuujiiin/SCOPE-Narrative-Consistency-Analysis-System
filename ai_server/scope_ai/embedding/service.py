"""3단계: 신규 submission의 사건만 증분 임베딩하여 누적 저장."""

from __future__ import annotations

from pathlib import Path

from ..common import StoryPaths, load_json, save_json
from .base import BaseEmbedder
from .event_embedder import EMBEDDING_FIELDS, embed_events


def embed_submission_events(
    story_id: str,
    submission_number: int,
    *,
    data_root: str | Path | None = None,
    embedder: BaseEmbedder | None = None,
    previous_events: list[dict] | None = None,
) -> dict:
    paths = StoryPaths(story_id, Path(data_root)) if data_root else StoryPaths(story_id)
    global_ep = load_json(paths.ep_global)
    new_events = [
        event for event in global_ep["events"]
        if event.get("source_submission") == submission_number
    ]

    if embedder is None:
                                                   
        from .bge_m3 import BGEM3Embedder
        model: BaseEmbedder = BGEM3Embedder()
    else:
        model = embedder

    if paths.event_embeddings.exists():
        store = load_json(paths.event_embeddings)
    else:
        store = {
            "model": getattr(model, "model_name", model.__class__.__name__),
            "embedding_fields": list(EMBEDDING_FIELDS),
            "events": [],
        }
    model_name = getattr(model, "model_name", model.__class__.__name__)
    if store.get("model") != model_name:
        raise ValueError("Embedding model changed; rebuild all story embeddings before proceeding")
    by_id = {item["event_id"]: item for item in store.get("events", [])}
    old_by_id = {item["event_id"]: item for item in previous_events or []}
    current_ids = {event["event_id"] for event in new_events}
    for event_id, old_event in old_by_id.items():
        if event_id not in current_ids:
            by_id.pop(event_id, None)
    updated_fields = {}
    for event in new_events:
        event_id = event["event_id"]
        old = old_by_id.get(event_id)
        cached = by_id.get(event_id)
        entry = dict(cached) if cached is not None else {"event_id": event_id}
        entry["source_submission"] = submission_number
        changed = []
        for field in EMBEDDING_FIELDS:
            key = f"{field}_embedding"
            value = event.get(field)
            if cached is not None and old is not None and old.get(field) == value and key in cached:
                continue
            if not isinstance(value, str) or not value.strip():
                entry[key] = None
            else:
                entry[key] = model.embed_batch([value.strip()])[0]
            changed.append(field)
        by_id[event_id] = entry
        if changed:
            updated_fields[event_id] = changed
    store["events"] = list(by_id.values())
    save_json(store, paths.event_embeddings)

    return {
        "submission_number": submission_number,
        "embedded_event_ids": list(updated_fields),
        "updated_fields": updated_fields,
        "embedding_path": str(paths.event_embeddings),
    }
