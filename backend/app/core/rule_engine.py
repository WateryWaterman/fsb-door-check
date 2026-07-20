"""规则引擎 — Table B2 查询 + 四状态判定。

对应 docs/CONTRACT.md §3 CheckResult schema。
对应 taskrequest/occupant_capacity_research.md Table B2 + Clause B13.4/B7.1。
"""
from __future__ import annotations

from typing import Any, Optional

from .presets import get_absolute_minimum_door_width_mm, table_b2_lookup

RULE_SOURCE = "HK FSB 2011 (2024) Part B, Table B2 + Clause B7.1"


def check_door(
    door_info: dict[str, Any],
    space_info: dict[str, Any],
    preset_id: str = "hk_fsb_2011_b2_default",
    override_threshold_mm: Optional[float] = None,
    override_threshold_source: Optional[str] = None,
    custom_threshold_table: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """对单门执行检查, 返回 CheckResult(对齐 CONTRACT.md §3)。

    三状态: pass / fail / non_passage。
    - custom_threshold_table 非空时优先用自定义表查询 (含 capacity<=3 的边界档)
    - override_threshold_mm 非空时, 用用户单条覆盖阈值替代, has_threshold_override=True
    """
    capacity = space_info.get("capacity")
    measured = door_info.get("measured_width_mm")
    width_source = door_info.get("width_source", "unknown")
    capacity_source = space_info.get("capacity_source", "unknown")
    needs_review_default = width_source != "clear_width"
    overridden = override_threshold_mm is not None

    if capacity is None:
        return _result(
            door_info, preset_id, "non_passage", None, "unknown_capacity",
            measured, None, capacity, capacity_source, width_source,
            needs_human_review=True,
            reason="cannot derive occupant capacity",
            rule_clause="B7.1",
            human_review_notes=["capacity unknown, user input or use_class override required"],
            has_override=False,
        )

    if capacity == 0:
        return _result(
            door_info, preset_id, "non_passage", None, "excluded_space",
            measured, None, capacity, capacity_source, width_source,
            needs_human_review=False,
            reason="space excluded from capacity (toilet/corridor/stair/lift), not an egress door",
            rule_clause="N/A",
            human_review_notes=[],
            has_override=False,
        )

    if capacity <= 3:
        # 默认走 B13.4 绝对最小 750mm; 但若 custom_table 第一档显式覆盖 capacity<=3, 用 custom
        custom_row = None
        if custom_threshold_table:
            for r in custom_threshold_table:
                cmin = r.get("capacity_min", 0)
                cmax = r.get("capacity_max")
                if cmin <= 3 and (cmax is None or cmax >= capacity):
                    custom_row = r
                    break
        if custom_row and custom_row.get("min_width_per_door_mm") is not None:
            base_threshold = float(custom_row["min_width_per_door_mm"])
            base_source = f"Custom Table B2 row[{custom_row['capacity_min']}-{custom_row['capacity_max']}] (extends to capacity<=3)"
            rule_clause = "B7.1"
        else:
            base_threshold = float(get_absolute_minimum_door_width_mm())
            base_source = "Clause B13.4 (absolute minimum, capacity<=3)"
            rule_clause = "B13.4"
    else:
        row = table_b2_lookup(capacity, custom_table=custom_threshold_table)
        if row is None or row.get("min_width_per_door_mm") is None:
            return _result(
                door_info, preset_id, "non_passage", None,
                "BA case-by-case approval (capacity>3000)",
                measured, None, capacity, capacity_source, width_source,
                needs_human_review=True,
                reason=f"capacity={capacity}>3000, requires Building Authority case-by-case approval",
                rule_clause="B7.1",
                human_review_notes=["capacity>3000, BA approval required"],
                has_override=False,
            )
        base_threshold = float(row["min_width_per_door_mm"])
        base_source = f"Table B2 row[{row['capacity_min']}-{row['capacity_max']}]"
        rule_clause = "B7.1"

    if overridden:
        threshold = float(override_threshold_mm)
        threshold_source = override_threshold_source or "user_override"
    else:
        threshold = base_threshold
        threshold_source = base_source

    if measured is None:
        return _result(
            door_info, preset_id, "non_passage", threshold, threshold_source,
            measured, None, capacity, capacity_source, width_source,
            needs_human_review=True,
            reason=_reason(capacity, threshold, None, overridden),
            rule_clause=rule_clause,
            human_review_notes=["width unknown, verify in model"],
            has_override=overridden,
        )

    if measured >= threshold:
        return _result(
            door_info, preset_id, "pass", threshold, threshold_source,
            measured, None, capacity, capacity_source, width_source,
            needs_human_review=needs_review_default or overridden,
            reason=_reason(capacity, threshold, measured, overridden, passed=True),
            rule_clause=rule_clause,
            human_review_notes=_width_review_notes(width_source),
            has_override=overridden,
        )

    deficit = threshold - measured
    return _result(
        door_info, preset_id, "fail", threshold, threshold_source,
        measured, deficit, capacity, capacity_source, width_source,
        needs_human_review=True,
        reason=_reason(capacity, threshold, measured, overridden, passed=False, deficit=deficit),
        rule_clause=rule_clause,
        human_review_notes=_width_review_notes(width_source),
        has_override=overridden,
    )


def _reason(capacity, threshold, measured, overridden, passed=None, deficit=None) -> str:
    ov_tag = " [user override]" if overridden else ""
    if measured is None:
        return f"capacity={capacity}, requires {threshold}mm{ov_tag}, but width unknown"
    if passed:
        return f"capacity={capacity}, requires {threshold}mm{ov_tag}, measured {measured}mm -> pass"
    return f"capacity={capacity}, requires {threshold}mm{ov_tag}, measured {measured}mm, deficit {deficit}mm -> fail"


def _width_review_notes(width_source: str) -> list[str]:
    if width_source == "clear_width":
        return []
    return ["width is OverallWidth proxy (not clear width), verify field-measured clear width"]


def _result(door_info, preset_id, status, threshold_mm, threshold_source,
            measured_mm, deficit_mm, capacity, capacity_source, width_source,
            needs_human_review, reason, rule_clause, human_review_notes,
            has_override=False) -> dict[str, Any]:
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
        "has_threshold_override": has_override,
        "human_review_notes": human_review_notes,
    }
