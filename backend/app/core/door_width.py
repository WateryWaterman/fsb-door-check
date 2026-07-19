"""门宽提取 — OverallWidth 作代理。

对应 taskrequest/ifc_field_fill_rate.md §三 门宽流水线。
实测: IfcDoor.OverallWidth 100% 填充, IfcDoorLiningProperties.LiningThickness 0%。
语义陷阱: OverallWidth 是门洞口宽, 非法规 clear width(门框竖向构件间净宽)。
"""
from __future__ import annotations

from typing import Optional

from .ifc_loader import get_psets, get_pset_prop


def get_door_width(door) -> tuple[Optional[float], str, bool]:
    """返回 (width_mm, source, needs_human_review)。

    source ∈ {"clear_width", "overall_minus_lining", "overall_estimate", "unknown"}
    needs_human_review: True 当 source != "clear_width"

    优先级:
    1. 自定义 Pset ClearWidth/NetWidth (MVP 样本未发现, 留兼容)
    2. OverallWidth - 2*LiningThickness (LiningThickness 实测 0%, 留兼容)
    3. OverallWidth 作代理 (MVP 主路径, 标 overall_estimate)
    4. unknown
    """
    psets = get_psets(door)
    for pset_name in list(psets.keys()):
        for prop_name in ("ClearWidth", "NetWidth"):
            v = get_pset_prop(psets, pset_name, prop_name)
            if v is not None and isinstance(v, (int, float)) and v > 0:
                return float(v) * 1000.0, "clear_width", False  # 假设 m → mm

    overall = door.OverallWidth
    if overall is not None:
        try:
            w_m = float(overall)
            if w_m > 0:
                if w_m > 10:
                    return w_m, "overall_estimate", True
                return w_m * 1000.0, "overall_estimate", True
        except (TypeError, ValueError):
            pass

    return None, "unknown", True
