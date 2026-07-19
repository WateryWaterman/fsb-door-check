"""规则引擎 — Table B2 查询 + 四状态判定。

对应 docs/CONTRACT.md §3 CheckResult schema。
对应 taskrequest/occupant_capacity_research.md Table B2 + Clause B13.4/B7.1。
"""
from __future__ import annotations

from typing import Any

from .presets import get_absolute_minimum_door_width_mm, table_b2_lookup

RULE_SOURCE = "HK FSB 2011 (2024) Part B, Table B2 + Clause B7.1"


def check_door(door_info: dict[str, Any], space_info: dict[str, Any],
               preset_id: str = "hk_fsb_2011_b2_default") -> dict[str, Any]:
    """对单门执行检查, 返回 CheckResult(对齐 CONTRACT.md §3)。

    door_info 必须含: global_id, measured_width_mm, width_source
    space_info 必须含: capacity, capacity_source
    """
    capacity = space_info.get("capacity")
    measured = door_info.get("measured_width_mm")
    width_source = door_info.get("width_source", "unknown")
    capacity_source = space_info.get("capacity_source", "unknown")
    needs_review_default = width_source != "clear_width"

    if capacity is None:
        return _result(
            door_info, preset_id, "unknown", None, "unknown_capacity",
            measured, None, capacity, capacity_source, width_source,
            needs_human_review=True,
            reason="cannot derive occupant capacity",
            rule_clause="B7.1",
            human_review_notes=["capacity unknown, user input or use_class override required"],
        )

    if capacity == 0:
        return _result(
            door_info, preset_id, "pass", None, "excluded_space",
            measured, None, capacity, capacity_source, width_source,
            needs_human_review=False,
            reason="space excluded from capacity (toilet/corridor/stair/lift), Table B2 not applicable",
            rule_clause="N/A",
            human_review_notes=[],
        )

    if capacity <= 3:
        abs_min = get_absolute_minimum_door_width_mm()  # 750
        threshold_source = "Clause B13.4 (absolute minimum, capacity<=3)"
        if measured is None:
            return _result(
                door_info, preset_id, "unknown", abs_min, threshold_source,
                measured, None, capacity, capacity_source, width_source,
                needs_human_review=True,
                reason=f"capacity={capacity}<=3, B13.4 requires {abs_min}mm, but width unknown",
                rule_clause="B13.4",
                human_review_notes=["width unknown, verify in model"],
            )
        if measured >= abs_min:
            return _result(
                door_info, preset_id, "pass", abs_min, threshold_source,
                measured, None, capacity, capacity_source, width_source,
                needs_human_review=needs_review_default,
                reason=f"capacity={capacity}<=3, B13.4 absolute minimum {abs_min}mm satisfied (measured {measured}mm)",
                rule_clause="B13.4",
                human_review_notes=_width_review_notes(width_source),
            )
        deficit = abs_min - measured
        return _result(
            door_info, preset_id, "fail", abs_min, threshold_source,
            measured, deficit, capacity, capacity_source, width_source,
            needs_human_review=True,
            reason=f"capacity={capacity}<=3, B13.4 requires {abs_min}mm, measured {measured}mm, deficit {deficit}mm",
            rule_clause="B13.4",
            human_review_notes=_width_review_notes(width_source),
        )

    row = table_b2_lookup(capacity)
    if row is None or row.get("min_width_per_door_mm") is None:
        return _result(
            door_info, preset_id, "unknown", None,
            "BA case-by-case approval (capacity>3000)",
            measured, None, capacity, capacity_source, width_source,
            needs_human_review=True,
            reason=f"capacity={capacity}>3000, requires Building Authority case-by-case approval",
            rule_clause="B7.1",
            human_review_notes=["capacity>3000, BA approval required"],
        )

    threshold = row["min_width_per_door_mm"]
    threshold_source = f"Table B2 row[{row['capacity_min']}-{row['capacity_max']}]"

    if measured is None:
        return _result(
            door_info, preset_id, "unknown", threshold, threshold_source,
            measured, None, capacity, capacity_source, width_source,
            needs_human_review=True,
            reason=f"capacity={capacity}, Table B2 requires {threshold}mm, but width unknown",
            rule_clause="B7.1",
            human_review_notes=["width unknown, verify in model"],
        )
    if measured >= threshold:
        return _result(
            door_info, preset_id, "pass", threshold, threshold_source,
            measured, None, capacity, capacity_source, width_source,
            needs_human_review=needs_review_default,
            reason=f"capacity={capacity}, Table B2 requires {threshold}mm, measured {measured}mm",
            rule_clause="B7.1",
            human_review_notes=_width_review_notes(width_source),
        )
    deficit = threshold - measured
    return _result(
        door_info, preset_id, "fail", threshold, threshold_source,
        measured, deficit, capacity, capacity_source, width_source,
        needs_human_review=True,
        reason=f"capacity={capacity}, Table B2 requires {threshold}mm, measured {measured}mm, deficit {deficit}mm",
        rule_clause="B7.1",
        human_review_notes=_width_review_notes(width_source),
    )


def _width_review_notes(width_source: str) -> list[str]:
    if width_source == "clear_width":
        return []
    return ["width is OverallWidth proxy (not clear width), verify field-measured clear width"]


def _result(door_info, preset_id, status, threshold_mm, threshold_source,
            measured_mm, deficit_mm, capacity, capacity_source, width_source,
            needs_human_review, reason, rule_clause, human_review_notes) -> dict[str, Any]:
    return {
        "door_global_id": door_info["global_id"],
        "preset_id": preset_id,
        "rule_source": RULE_SOURCE,
        "rule_clause": rule_clause,
        "status": status,
        "threshold_mm": threshold_mm,
        "threshold_source": threshold_source,
        "measured_mm": measured_mm,
        "deficit_mm": deficit_mm,
        "occupant_capacity": capacity,
        "capacity_source": capacity_source,
        "width_source": width_source,
        "needs_human_review": needs_human_review,
        "reason": reason,
        "overridden": False,
        "human_review_notes": human_review_notes,
    }
