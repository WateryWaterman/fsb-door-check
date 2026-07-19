"""房间用途识别 — LongName 关键词 → Table A1 映射。

对应 taskrequest/ifc_field_fill_rate.md §三 房间用途流水线。
实测: Pset_SpaceOccupancyRequirements 0% 填充, LongName 100% 填充。
"""
from __future__ import annotations

from typing import Any

from .ifc_loader import get_psets, get_pset_prop
from .presets import match_longname_to_use_class


def get_space_use(space) -> dict[str, Any]:
    """返回 use_class 信息 dict(对齐 CONTRACT.md §6.3 UseClassSource)。

    优先级:
    1. Pset_SpaceOccupancyRequirements.OccupancyType (实测 0%, 留兼容)
    2. IfcSpace.LongName 关键词映射 (MVP 主路径)
    3. unknown

    返回字段: use_class, accommodation, factor, factor_type, confidence, source, note
    source ∈ {
      "Pset_SpaceOccupancyRequirements.OccupancyType",
      "longname_keyword",
      "excluded",
      "ambiguous",
      "unknown"
    }
    """
    psets = get_psets(space)
    occ_type = get_pset_prop(psets, "Pset_SpaceOccupancyRequirements", "OccupancyType")
    if occ_type:
        match = match_longname_to_use_class(str(occ_type))
        if match["use_class"]:
            match["source"] = "Pset_SpaceOccupancyRequirements.OccupancyType"
            return match

    longname = space.LongName
    return match_longname_to_use_class(longname)
