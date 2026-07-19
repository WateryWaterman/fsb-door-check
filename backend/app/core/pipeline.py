"""端到端流水线 — 串联所有解析步骤, 输出完整 session 结果。

对应 docs/CONTRACT.md §7.1 POST /model/upload 响应 + §7.2 POST /check 响应。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .door_space_link import get_door_primary_space
from .door_width import get_door_width
from .fire_exit_infer import infer_fire_exit
from .ifc_loader import (
    get_doors, get_door_types, get_schema, get_spaces, get_storey_of_element,
    get_storeys, load_ifc,
)
from .occupant_capacity import compute_space_capacity
from .rule_engine import check_door


def analyze_ifc(path: str | Path, preset_id: str = "hk_fsb_2011_b2_default") -> dict[str, Any]:
    """完整流水线: 加载 → 解析空间 → 解析门 → 检查 → 返回结构化结果。

    返回对齐 CONTRACT.md §7.1 + §7.2(合并 upload 与 check 为一步, MVP 简化)。
    """
    f = load_ifc(path)
    schema = get_schema(f)
    storeys = get_storeys(f)
    spaces = get_spaces(f)
    doors = get_doors(f)
    door_types = get_door_types(f)

    space_infos: dict[str, dict[str, Any]] = {}
    for sp in spaces:
        info = compute_space_capacity(sp)
        info["global_id"] = sp.GlobalId
        info["name"] = sp.Name
        info["long_name"] = sp.LongName
        info["storey_global_id"] = get_storey_of_element(sp)
        space_infos[sp.GlobalId] = info

    storey_infos: list[dict[str, Any]] = []
    for st in storeys:
        storey_infos.append({
            "global_id": st.GlobalId,
            "name": st.Name,
            "long_name": st.LongName,
            "elevation_m": st.Elevation,
            "storey_index": 0,
        })
    storey_infos.sort(key=lambda s: s.get("elevation_m") or 0)
    for i, s in enumerate(storey_infos):
        s["storey_index"] = i

    door_results: list[dict[str, Any]] = []
    width_unit_warnings: list[str] = []
    for d in doors:
        w_mm, w_src, needs_review = get_door_width(d)
        if w_mm is not None and w_src == "overall_estimate" and w_mm > 5000:
            width_unit_warnings.append(
                f"door {d.GlobalId} width={w_mm}mm seems too large, check IFC unit assignment"
            )

        space_ids_primary, space_ids_other = get_door_primary_space(d)
        all_space_ids = [s for s in [space_ids_primary, space_ids_other] if s]
        is_fe, fe_src, fe_reasons = infer_fire_exit(d, all_space_ids, space_infos)

        space_info = space_infos.get(space_ids_primary, {
            "capacity": None,
            "capacity_source": "unknown",
        })

        door_info: dict[str, Any] = {
            "global_id": d.GlobalId,
            "name": d.Name,
            "long_name": getattr(d, "LongName", None),
            "overall_width_mm": w_mm,
            "overall_height_mm": _safe_float(getattr(d, "OverallHeight", None)),
            "measured_width_mm": w_mm,
            "width_source": w_src,
            "needs_human_review": needs_review,
            "is_fire_exit": is_fe,
            "fire_exit_source": fe_src,
            "fire_exit_reasons": fe_reasons,
            "space_global_id": space_ids_primary,
            "space_global_id_other": space_ids_other,
            "storey_global_id": get_storey_of_element(d),
        }
        result = check_door(door_info, space_info, preset_id)
        door_results.append({**door_info, "check_result": result})

    summary = _build_summary(door_results)

    return {
        "schema": schema,
        "counts": {
            "spaces": len(spaces),
            "doors": len(doors),
            "storeys": len(storeys),
            "door_types": len(door_types),
        },
        "storeys": storey_infos,
        "spaces": list(space_infos.values()),
        "doors": door_results,
        "summary": summary,
        "warnings": width_unit_warnings,
    }


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
        if x > 10:
            return x
        return x * 1000.0
    except (TypeError, ValueError):
        return None


def _build_summary(door_results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(door_results)
    by_status = {"pass": 0, "fail": 0, "unknown": 0, "overridden": 0}
    fire_exit_count = 0
    needs_review_count = 0
    fails: list[dict[str, Any]] = []
    for d in door_results:
        cr = d.get("check_result") or {}
        status = cr.get("status", "unknown")
        if status in by_status:
            by_status[status] += 1
        if d.get("is_fire_exit"):
            fire_exit_count += 1
        if cr.get("needs_human_review"):
            needs_review_count += 1
        if status == "fail":
            fails.append(cr)
    fails.sort(key=lambda c: c.get("deficit_mm") or 0, reverse=True)
    return {
        "total_doors": total,
        "checked_doors": fire_exit_count,
        "by_status": by_status,
        "needs_review_count": needs_review_count,
        "top_fails": fails[:5],
    }
