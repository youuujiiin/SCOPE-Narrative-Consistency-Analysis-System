from __future__ import annotations

import json
import re
from pathlib import Path

from ..common import StoryPaths, load_json, save_json


def _normalized(text):
    return "".join(ch for ch in text if not ch.isspace() and not (not ch.isalnum() and ch != "_"))


def _matches(source, quote):
    if not isinstance(quote, str) or not quote.strip():
        return []
    exact = []
    start = 0
    while True:
        found = source.find(quote, start)
        if found < 0:
            break
        exact.append((found, found + len(quote)))
        start = found + 1
    if exact:
        return exact
    normalized_quote = _normalized(quote)
    if not normalized_quote:
        return []
    chars = [(index, ch) for index, ch in enumerate(source) if not ch.isspace() and (ch.isalnum() or ch == "_")]
    compact = "".join(ch for _, ch in chars)
    result = []
    start = 0
    while True:
        found = compact.find(normalized_quote, start)
        if found < 0:
            break
        result.append((chars[found][0], chars[found + len(normalized_quote) - 1][0] + 1))
        start = found + 1
    return result


def _quotes(event):
    candidates = event.get("source_quotes")
    if not isinstance(candidates, list):
        candidates = [event.get("source_text") or event.get("source_quote")]
    return [item for item in candidates if isinstance(item, str) and item.strip()][:3]


def extract_event_sources(story_id, number, *, data_root=None, event_id_map=None):
    paths = StoryPaths(story_id, Path(data_root)) if data_root else StoryPaths(story_id)
    source = paths.submission(number).read_text(encoding="utf-8") if paths.submission(number).exists() else ""
    ep = load_json(paths.ep(number))
    directory = paths.ep_split_dir(number) / "event_sources"
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {"submission_number": number, "events": {}}
    expected = set()
    for event in ep["events"]:
        event_id = (event_id_map or {}).get(event["event_id"], event["event_id"])
        if not re.fullmatch(r"[A-Za-z0-9_-]+", event_id):
            raise ValueError("Invalid event ID")
        segments = []
        for quote in _quotes(event):
            matches = _matches(source, quote)
            if len(matches) != 1:
                continue
            start, end = matches[0]
            if any(not (end <= seg["start"] or start >= seg["end"]) for seg in segments):
                continue
            segments.append({"start": start, "end": end, "text": source[start:end]})
        segments.sort(key=lambda item: item["start"])
        status = "verified" if segments else "unverified"
        filename = f"{event_id}.txt"
        if segments:
            (directory / filename).write_text("\n\n".join(segment["text"] for segment in segments), encoding="utf-8")
            expected.add(filename)
        manifest["events"][event_id] = {"source_status": status, "segments": segments, "file": filename if segments else None}
    for old in directory.glob("*.txt"):
        if old.name not in expected:
            old.unlink()
    save_json(manifest, directory / "manifest.json")
    return manifest


def load_event_sources(paths, number):
    manifest = paths.ep_split_dir(number) / "event_sources" / "manifest.json"
    return load_json(manifest).get("events", {}) if manifest.exists() else {}
