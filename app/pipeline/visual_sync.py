from __future__ import annotations

from copy import deepcopy


FIELDS = {
    "worldview": ("worldview_rules", "rule_id"),
    "characters": ("characters", "character_id"),
    "events": ("events", "event_id"),
    "timeline": ("times", "time_id"),
    "spaces": ("locations", "location_id"),
}


def sync_visual_category(visual: dict | None, category: str, items: list[dict]) -> dict | None:
    if not isinstance(visual, dict) or category not in FIELDS:
        return visual
    field, id_field = FIELDS[category]
    result = deepcopy(visual)
    previous = {entry.get(id_field): entry for entry in result.get(field, []) if isinstance(entry, dict)}
    updated = []
    for item in items:
        key = item.get("entity_key")
        if not isinstance(key, str) or not key:
            continue
        entry = deepcopy(previous.get(key, {id_field: key}))
        if category == "worldview":
            entry["content"] = item.get("item") or ""
            if item.get("detail") is not None:
                entry["description"] = item["detail"]
        elif category == "characters":
            entry["name"] = item.get("name") or ""
            attrs = item.get("attrs")
            if isinstance(attrs, dict) and attrs.get("description") is not None:
                entry["description"] = attrs["description"]
        elif category == "events":
            entry["title"] = item.get("label") or ""
            for source_key, target_key in (("order_index", "order"), ("summary", "summary"),
                                           ("cause", "cause"), ("result", "result"),
                                           ("participant_character_ids", "participant_character_ids"),
                                           ("main_actor_character_id", "main_actor_character_id"),
                                           ("time_id", "time_id"), ("location_id", "location_id"),
                                           ("source_quotes", "source_quotes")):
                if item.get(source_key) is not None:
                    entry[target_key] = item[source_key]
        elif category == "timeline" and item.get("time_value") is not None:
            entry["expression"] = item["time_value"]
        elif category == "spaces" and item.get("place") is not None:
            entry["name"] = item["place"]
        for field_name in ("note", "quote"):
            if item.get(field_name):
                entry["user_" + field_name] = item[field_name]
            else:
                entry.pop("user_" + field_name, None)
        updated.append(entry)
    result[field] = updated
    return result
