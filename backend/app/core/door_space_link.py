"""门↔房间关联。

对应 taskrequest/ifc_field_fill_rate.md §三 门↔房间流水线。
主路径: IfcRelSpaceBoundary (IFC2x3 大样本 100%)
兜底1: IfcRelContainedInSpatialStructure → IfcSpace (实测 0%)
兜底2: 几何 point-in-polygon (SampleHouse IFC4 退化路径, MVP 暂不实现)
"""
from __future__ import annotations

from typing import Optional


def get_door_spaces(door) -> list[str]:
    """返回门关联的所有空间 GlobalId 列表(通常 1 个, 跨两空间时 2 个)。

    通过 IfcRelSpaceBoundary 找:
    - IFC4 inverse: door.ProvidesBoundaries
    - IFC2x3 inverse: door.ProvidesBoundaries 或 door.BoundedBy
    """
    space_ids: list[str] = []
    boundaries: list = []

    for attr in ("ProvidesBoundaries", "BoundedBy"):
        try:
            b = getattr(door, attr, None)
            if b:
                boundaries = list(b)
                break
        except Exception:
            continue

    for bnd in boundaries:
        try:
            space = bnd.RelatingSpace
            if space is not None:
                gid = space.GlobalId
                if gid and gid not in space_ids:
                    space_ids.append(gid)
        except Exception:
            continue

    if space_ids:
        return space_ids

    try:
        for rel in door.ContainedInStructure:
            struct = rel.RelatingStructure
            if struct.is_a("IfcSpace"):
                gid = struct.GlobalId
                if gid and gid not in space_ids:
                    space_ids.append(gid)
    except Exception:
        pass

    return space_ids


def get_door_primary_space(door) -> tuple[Optional[str], Optional[str]]:
    """返回 (primary_space_global_id, other_space_global_id)。

    跨两空间时 primary=第一个, other=第二个(疏散门候选)。
    """
    ids = get_door_spaces(door)
    if not ids:
        return None, None
    if len(ids) == 1:
        return ids[0], None
    return ids[0], ids[1]
