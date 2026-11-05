"""Worldview rule ID 및 누적 병합."""

from __future__ import annotations

from copy import deepcopy

from .id_utils import sequential_id_map


def plan_rule_ids(new_items: list[dict], existing: list[dict]) -> dict[str, str]:
                                                  
    return sequential_id_map(
        new_items,
        existing,
        id_field="rule_id",
        prefix="RULE",
    )


def merge_rules(transformed_items: list[dict], existing: list[dict], submission_number: int) -> list[dict]:
    result = deepcopy(existing)
    for item in transformed_items:
        copied = deepcopy(item)
        copied["source_submission"] = submission_number
        result.append(copied)
    return result
