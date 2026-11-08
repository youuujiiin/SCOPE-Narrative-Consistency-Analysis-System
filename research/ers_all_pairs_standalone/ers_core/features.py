

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
