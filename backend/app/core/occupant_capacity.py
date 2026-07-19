"""Occupant Capacity 推算。

对应 taskrequest/ifc_field_deep_lookup.md §三 Occupant Capacity 流水线。
公式: capacity = usable_floor_area / occupancy_factor(向上取整)。
"""
from __future__ import annotations

import math
from typing import Any

from .ifc_loader import get_psets, get_pset_prop
from .presets import compute_capacity
from .space_area import get_space_area
from .space_use import get_space_use


def compute_space_capacity(space) -> dict[str, Any]:
    """返回 capacity 信息 dict(对齐 CONTRACT.md §6.4 CapacitySource)。

    优先级:
    1. Pset_SpaceOccupancyRequirements.OccupancyNumber (实测 0%, 留兼容)
    2. Pset_SpaceOccupancyRequirements.AreaPerOccupant 反算 (实测 0%)
    3. LongName → Table B1 factor → area/factor (MVP 主路径)
    4. unknown

    排除空间(toilet/corridor/stair/lift) capacity=0, source="excluded"。
    """
    area_m2, area_source = get_space_area(space)
    use_info = get_space_use(space)

    result: dict[str, Any] = {
        "capacity": None,
        "capacity_source": "unknown",
        "area_m2": area_m2,
        "area_source": area_source,
        "use_class": use_info["use_class"],
        "use_class_source": use_info["source"],
        "use_class_accommodation": use_info["accommodation"],
        "use_class_confidence": use_info["confidence"],
        "factor": use_info["factor"],
        "factor_type": use_info["factor_type"],
        "use_class_note": use_info.get("note"),
    }

    if use_info["source"] == "excluded":
        result["capacity"] = 0
        result["capacity_source"] = "excluded"
        return result

    psets = get_psets(space)
    occ_num = get_pset_prop(psets, "Pset_SpaceOccupancyRequirements", "OccupancyNumber")
    if occ_num is not None and isinstance(occ_num, (int, float)) and occ_num >= 0:
        result["capacity"] = int(occ_num)
        result["capacity_source"] = "OccupancyNumber"
        return result

    apo = get_pset_prop(psets, "Pset_SpaceOccupancyRequirements", "AreaPerOccupant")
    if apo is not None and isinstance(apo, (int, float)) and apo > 0 and area_m2:
        result["capacity"] = math.ceil(area_m2 / apo)
        result["capacity_source"] = "AreaPerOccupant"
        return result

    if use_info["factor"] is not None and use_info["factor_type"] == "area_per_person_m2" and area_m2:
        cap, _ = compute_capacity(area_m2, use_info["factor"], use_info["factor_type"])
        if cap is not None:
            result["capacity"] = cap
            result["capacity_source"] = "table_b1_factor"
            return result

    return result
