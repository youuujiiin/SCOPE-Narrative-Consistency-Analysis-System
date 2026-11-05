from __future__ import annotations
from copy import deepcopy
from .id_utils import next_id_number


def _key(item):
    name = item.get('name')
    return ' '.join(name.casefold().split()) if isinstance(name, str) and name.strip() else None


def plan_location_ids(new_items: list[dict], existing: list[dict], previous: dict | None = None, previous_items: list[dict] | None = None) -> dict[str, str]:
    by_id = {item['location_id']: item for item in existing}
    previous_by_id = {item['location_id']: item for item in previous_items or []}
    mapping = {}
    number = next_id_number(list(existing) + list(previous_items or []), 'location_id', 'LOCATION')
    used = set(by_id) | set(previous_by_id)
    pending = {item['location_id']: item for item in new_items}
    if len(pending) != len(new_items) or any(not identifier for identifier in pending):
        raise ValueError('Missing or duplicate local location ID')
    visiting = set()

    def assign(local):
        nonlocal number
        if local in mapping:
            return mapping[local]
        if local in visiting:
            raise ValueError('Cyclic location parent hierarchy')
        if local not in pending:
            if isinstance(local, str) and local.startswith('LOCATION_'):
                return local
            raise ValueError(f'Unknown parent location: {local}')
        visiting.add(local)
        item = pending[local]
        parent = item.get('parent_location_id')
        parent_id = assign(parent) if parent else None
        key = _key(item)
        chosen = None
        if previous and local in previous:
            prior_id = previous[local]
            prior = previous_by_id.get(prior_id) or by_id.get(prior_id)
            if prior and _key(prior) == key and prior.get('parent_location_id') == parent_id:
                chosen = prior_id
        if chosen is None and key:
            matches = [old for old in existing if _key(old) == key and old.get('parent_location_id') == parent_id]
            if parent_id is not None and len(matches) == 1:
                chosen = matches[0]['location_id']
            elif parent_id is None and len(matches) == 1 and item.get('identity_evidence') and matches[0].get('identity_evidence'):
                chosen = matches[0]['location_id']
        if chosen is None:
            while f'LOCATION_{number:03d}' in used:
                number += 1
            chosen = f'LOCATION_{number:03d}'
            number += 1
        mapping[local] = chosen
        used.add(chosen)
        visiting.remove(local)
        return chosen

    for identifier in pending:
        assign(identifier)
    if len(set(mapping.values())) != len(mapping):
        raise ValueError('Multiple local locations mapped to one global ID')
    return mapping


def merge_locations(transformed_items: list[dict], existing: list[dict], submission_number: int) -> list[dict]:
    result = deepcopy(existing)
    by_id = {item['location_id']: item for item in result}
    for item in transformed_items:
        copied = deepcopy(item)
        identifier = copied['location_id']
        if identifier in by_id:
            current = by_id[identifier]
            if current.get('parent_location_id') != copied.get('parent_location_id'):
                raise ValueError(f'Conflicting parent for location {identifier}')
            sources = current.setdefault('source_submissions', [])
            if submission_number not in sources:
                sources.append(submission_number)
        else:
            copied['source_submission'] = submission_number
            copied['source_submissions'] = [submission_number]
            result.append(copied)
            by_id[identifier] = copied
    return result
