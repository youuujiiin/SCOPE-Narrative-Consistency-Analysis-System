"""2단계: epN 분할 → 타입별 ID 통합 → ep_global 갱신."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from ..common import StoryPaths, empty_ep, load_json, save_json, validate_ep
from .splitter import split_ep
from .character_manager import plan_character_ids, merge_characters
from .rule_manager import plan_rule_ids, merge_rules
from .event_manager import plan_event_ids, merge_events
from .time_manager import plan_time_ids, merge_times
from .location_manager import plan_location_ids, merge_locations
from .reference_mapper import replace_references


def process_ep(
    story_id: str,
    submission_number: int,
    *,
    ep: dict | None = None,
    data_root: str | Path | None = None,
    previous_id_maps: dict | None = None,
) -> dict:
    if submission_number < 1:
        raise ValueError("submission_number는 1 이상이어야 합니다.")

    paths = StoryPaths(story_id, Path(data_root)) if data_root else StoryPaths(story_id)
    current = deepcopy(ep) if ep is not None else load_json(paths.ep(submission_number))
    validate_ep(current)

    global_ep = load_json(paths.ep_global) if paths.ep_global.exists() else empty_ep()
    validate_ep(global_ep)

    previous_locations = [deepcopy(item) for item in global_ep["locations"] if submission_number in item.get("source_submissions", [item.get("source_submission")])]
    if previous_id_maps is not None:
        for field in ("events", "worldview_rules", "times"):
            global_ep[field] = [item for item in global_ep[field] if item.get("source_submission") != submission_number]
        retained_characters = []
        for character in global_ep["characters"]:
            sources = character.get("source_submissions", [])
            if submission_number not in sources:
                retained_characters.append(character)
                continue
            remaining = [number for number in sources if number != submission_number]
            if remaining:
                character["source_submissions"] = remaining
                retained_characters.append(character)
        global_ep["characters"] = retained_characters
        kept_locations = []
        for location in global_ep["locations"]:
            sources = location.get("source_submissions", [location.get("source_submission")])
            remaining = [number for number in sources if number is not None and number != submission_number]
            if remaining:
                location["source_submissions"] = remaining
                kept_locations.append(location)
        global_ep["locations"] = kept_locations

    character_map = plan_character_ids(current["characters"], global_ep["characters"])
    rule_map = plan_rule_ids(current["worldview_rules"], global_ep["worldview_rules"])
    event_map = plan_event_ids(current["events"], global_ep["events"])
    time_map = plan_time_ids(current["times"], global_ep["times"])
    location_map = plan_location_ids(current["locations"], global_ep["locations"], (previous_id_maps or {}).get("locations"), previous_locations)

    planned = {"characters": character_map, "worldview_rules": rule_map, "events": event_map, "times": time_map, "locations": location_map}
    if previous_id_maps is not None:
        id_fields = {"characters": "character_id", "worldview_rules": "rule_id", "events": "event_id", "times": "time_id", "locations": "location_id"}
        prefixes = {"characters": "CHAR", "worldview_rules": "RULE", "events": "EVENT", "times": "TIME", "locations": "LOCATION"}
        for field, mapping in planned.items():
            previous = previous_id_maps.get(field, {})
            reserved = {item[id_fields[field]] for item in global_ep[field]}
            reserved.update(previous.values())
            next_number = 1
            for value in reserved:
                prefix = prefixes[field] + "_"
                if value.startswith(prefix) and value[len(prefix):].isdigit():
                    next_number = max(next_number, int(value[len(prefix):]) + 1)
            if field == "locations":
                continue
            for local_id in list(mapping):
                if local_id in previous:
                    mapping[local_id] = previous[local_id]
                elif field != "characters" or mapping[local_id] not in reserved:
                    mapping[local_id] = f"{prefixes[field]}_{next_number:03d}"
                    next_number += 1
            if len(set(mapping.values())) != len(mapping):
                raise ValueError(f"Duplicate mapped IDs in {field}")
            collisions = set(mapping.values()) & {item[id_fields[field]] for item in global_ep[field]}
            if field == "characters":
                collisions = set()
            if collisions:
                raise ValueError(f"Global ID collision in {field}: {sorted(collisions)}")
    mappings = [character_map, rule_map, event_map, time_map, location_map]
    transformed = {
        field: replace_references(current[field], mappings)
        for field in current
        if field in {"worldview_rules", "characters", "events", "times", "locations"}
    }

                                           
    id_fields = {
        "worldview_rules": "rule_id",
        "characters": "character_id",
        "events": "event_id",
        "times": "time_id",
        "locations": "location_id",
    }
    for field, id_field in id_fields.items():
        for original, mapped in zip(current[field], transformed[field]):
            if original.get(id_field):
                mapped["source_local_id"] = original[id_field]

    global_ep["characters"] = merge_characters(
        transformed["characters"], global_ep["characters"], submission_number
    )
    global_ep["worldview_rules"] = merge_rules(
        transformed["worldview_rules"], global_ep["worldview_rules"], submission_number
    )
    global_ep["events"] = merge_events(
        transformed["events"], global_ep["events"], submission_number
    )
    global_ep["times"] = merge_times(
        transformed["times"], global_ep["times"], submission_number
    )
    global_ep["locations"] = merge_locations(
        transformed["locations"], global_ep["locations"], submission_number
    )

    split_ep(current, paths.ep_split_dir(submission_number))
    save_json(global_ep, paths.ep_global)

    return {
        "submission_number": submission_number,
        "ep_global_path": str(paths.ep_global),
        "id_maps": {
            "characters": character_map,
            "worldview_rules": rule_map,
            "events": event_map,
            "times": time_map,
            "locations": location_map,
        },
        "new_event_ids": list(event_map.values()),
        "counts": {field: len(current[field]) for field in current if isinstance(current[field], list)},
    }
