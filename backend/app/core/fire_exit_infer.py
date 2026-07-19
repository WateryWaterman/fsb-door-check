"""疏散门推断。

对应 taskrequest/ifc_field_fill_rate.md §三 疏散门识别流水线。
实测: Pset_DoorCommon.FireExit 0% 填充, 改用推断。
"""
from __future__ import annotations

from typing import Any, Optional

from .ifc_loader import get_psets, get_pset_prop

FIRE_EXIT_NAME_KEYWORDS = ("exit", "entry", "corridor", "stair", "escape", "egress")
STAIR_SPACE_KEYWORDS = ("stair", "staircase", "stairwell", "landing")


def infer_fire_exit(door, space_ids: list[str],
                    space_infos: Optional[dict] = None) -> tuple[bool, str, list[str]]:
    """返回 (is_fire_exit, source, reasons[])。

    source ∈ {
      "Pset_DoorCommon.FireExit",
      "inferred_cross_space",
      "inferred_name_keyword",
      "inferred_to_stair",
      "not_fire_exit"
    }
    """
    reasons: list[str] = []

    psets = get_psets(door)
    fire_exit = get_pset_prop(psets, "Pset_DoorCommon", "FireExit")
    if fire_exit is True:
        return True, "Pset_DoorCommon.FireExit", ["Pset_DoorCommon.FireExit=True"]

    if len(space_ids) >= 2:
        reasons.append(f"crosses two spaces via IfcRelSpaceBoundary: {space_ids}")
        return True, "inferred_cross_space", reasons

    name = (door.Name or "").lower()
    longname = (getattr(door, "LongName", None) or "").lower()
    text = f"{name} {longname}"
    for kw in FIRE_EXIT_NAME_KEYWORDS:
        if kw in text:
            reasons.append(f"name/longname contains '{kw}'")
            return True, "inferred_name_keyword", reasons

    if space_infos and space_ids:
        for sid in space_ids:
            info = space_infos.get(sid)
            if not info:
                continue
            sp_longname = (info.get("long_name") or "").lower()
            for kw in STAIR_SPACE_KEYWORDS:
                if kw in sp_longname:
                    reasons.append(f"connects to stair space '{sp_longname}' (global_id={sid})")
                    return True, "inferred_to_stair", reasons

    return False, "not_fire_exit", []
