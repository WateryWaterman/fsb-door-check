"""房间面积提取 — 动态匹配 IfcQuantityArea.Name。

对应 taskrequest/ifc_field_fill_rate.md §三 房间面积流水线。
实测命中: IFC2x3 Revit 用 "GSA BIM Area", IFC4 用 "NetFloorArea", 均 100%。
"""
from __future__ import annotations

from typing import Optional

from .ifc_loader import get_element_quantities

# 按优先级排序的面积 Quantity Name(IFC2x3 Revit 与 IFC4 命名差异)
AREA_QUANTITY_NAMES = ["NetFloorArea", "GSA BIM Area", "GrossFloorArea", "Area"]


def get_space_area(space) -> tuple[Optional[float], str]:
    """返回 (area_m2, source)。

    source ∈ {
      "IfcQuantityArea.NetFloorArea",
      "IfcQuantityArea.GSA BIM Area",
      "IfcQuantityArea.GrossFloorArea",
      "IfcQuantityArea.<其他名>",
      "unknown"
    }
    """
    quantities: list[tuple[str, float]] = []
    for pds in get_element_quantities(space):
        try:
            for q in pds.Quantities:
                if q.is_a("IfcQuantityArea"):
                    try:
                        val = q.AreaValue
                        if val is not None:
                            quantities.append((q.Name, float(val)))
                    except Exception:
                        continue
        except Exception:
            continue

    for preferred_name in AREA_QUANTITY_NAMES:
        for name, val in quantities:
            if name == preferred_name:
                return val, f"IfcQuantityArea.{name}"

    if quantities:
        name, val = quantities[0]
        return val, f"IfcQuantityArea.{name}"

    return None, "unknown"
