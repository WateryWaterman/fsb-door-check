"""路由 /override — 人工覆盖(防火门/用途/人数/阈值/楼层标记)。

对应 docs/SSD.md §4 阈值覆盖、§5 标记防火门、§6 用途/人数覆盖。
对应 docs/CONTRACT.md §4 OverrideRequest schema。
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

from ..core.presets import compute_capacity, get_default_factor_for_use_class
from ..core.rule_engine import check_door
from ..models.schemas import OverrideRequest
from ..session import Session, get_session

router = APIRouter(prefix="/override", tags=["override"])


class BatchCheckedRequest(BaseModel):
    global_ids: list[str]
    value: bool


@router.post("/{sid}")
def apply_override(sid: str, req: OverrideRequest):
    s = get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail={
            "error": "session_not_found", "detail": sid})

    affected: list[dict[str, Any]] = []

    if req.type == "fire_exit":
        affected = _override_fire_exit(s, req)
    elif req.type == "space_use":
        affected = _override_space_use(s, req)
    elif req.type == "occupancy":
        affected = _override_occupancy(s, req)
    elif req.type == "threshold":
        affected = _override_threshold(s, req)
    elif req.type in ("storey_sprinkler", "storey_entrance"):
        affected = _override_storey(s, req)
    elif req.type == "checked":
        affected = _override_checked(s, req)
    else:
        raise HTTPException(status_code=400, detail={
            "error": "invalid_override_type", "detail": req.type,
            "hint": "valid types: fire_exit | space_use | occupancy | threshold | storey_sprinkler | storey_entrance | checked"})

    s.overrides.append(req.model_dump())
    s.result["summary"] = _rebuild_summary(s.result.get("doors", []))
    return {"session_id": sid, "applied": req.model_dump(), "affected_results": affected}


@router.post("/{sid}/checked/batch")
def batch_checked(sid: str, req: BatchCheckedRequest):
    s = get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail={
            "error": "session_not_found", "detail": sid})
    count = 0
    for gid in req.global_ids:
        s.door_checked_overrides[gid] = bool(req.value)
        door = s.find_door(gid)
        if door:
            door["is_checked"] = bool(req.value)
            count += 1
    s.result["summary"] = _rebuild_summary(s.result.get("doors", []))
    return {"session_id": sid, "updated": count}


@router.delete("/{sid}/threshold/all")
def delete_all_threshold_overrides(sid: str):
    """DEPRECATED: 旧单条阈值覆盖清理入口, 等价于 reset_threshold_table。保留向后兼容。"""
    s = get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail={
            "error": "session_not_found", "detail": sid})
    s.reset_custom_threshold_table()
    affected = _recheck_all_doors(s)
    s.result["summary"] = _rebuild_summary(s.result.get("doors", []))
    return {"session_id": sid, "cleared_all": True, "summary": s.result["summary"], "affected_results": affected}


class ThresholdTableRequest(BaseModel):
    bands: list[dict[str, Any]]


@router.put("/{sid}/threshold/table")
def save_threshold_table(sid: str, req: ThresholdTableRequest):
    s = get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail={
            "error": "session_not_found", "detail": sid})
    err = _validate_threshold_bands(req.bands)
    if err:
        raise HTTPException(status_code=400, detail={
            "error": "invalid_threshold_table", "detail": err})
    s.set_custom_threshold_table(req.bands)
    affected = _recheck_all_doors(s)
    s.result["summary"] = _rebuild_summary(s.result.get("doors", []))
    return {
        "session_id": sid, "bands_saved": len(req.bands),
        "summary": s.result["summary"], "affected_results": affected,
        "custom_threshold_table": s.custom_threshold_table,
        "rechecked_count": len(affected),
    }


@router.delete("/{sid}/threshold/table")
def reset_threshold_table(sid: str):
    s = get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail={
            "error": "session_not_found", "detail": sid})
    s.reset_custom_threshold_table()
    affected = _recheck_all_doors(s)
    s.result["summary"] = _rebuild_summary(s.result.get("doors", []))
    return {
        "session_id": sid, "reset_to_defaults": True,
        "summary": s.result["summary"], "affected_results": affected,
        "custom_threshold_table": None,
        "rechecked_count": len(affected),
    }


def _validate_threshold_bands(bands: list[dict[str, Any]]) -> Optional[str]:
    if not bands:
        return "bands list cannot be empty"
    if not isinstance(bands, list):
        return "bands must be a list"
    sorted_bands = sorted(bands, key=lambda b: b.get("capacity_min", 0))
    for i, b in enumerate(sorted_bands):
        cmin = b.get("capacity_min")
        cmax = b.get("capacity_max")
        width = b.get("min_width_per_door_mm")
        if not isinstance(cmin, int) or cmin < 3:
            return f"band {i}: capacity_min must be an integer >= 3, got {cmin}"
        if cmax is not None and (not isinstance(cmax, int) or cmax < cmin):
            return f"band {i}: capacity_max must be null or integer >= capacity_min, got {cmax}"
        if width is not None and (not isinstance(width, (int, float)) or width <= 0):
            return f"band {i}: min_width_per_door_mm must be a positive number, got {width}"
        if i == len(sorted_bands) - 1:
            if cmax is not None:
                return f"last band {i}: capacity_max must be null (open upper bound)"
        else:
            if cmax is None:
                return f"band {i}: only the last band may have capacity_max=null"
            next_cmin = sorted_bands[i + 1].get("capacity_min", 0)
            if cmax + 1 != next_cmin:
                return f"gap or overlap between band {i} (max={cmax}) and band {i+1} (min={next_cmin})"
    return None


def _override_fire_exit(s: Session, req: OverrideRequest) -> list[dict[str, Any]]:
    s.door_fire_exit_overrides[req.global_id] = bool(req.value)
    door = s.find_door(req.global_id)
    if door:
        door["is_fire_exit"] = bool(req.value)
        door["fire_exit_source"] = "user_override" if bool(req.value) else "not_fire_exit"
        if door.get("check_result"):
            return [door["check_result"]]
    return []


def _override_space_use(s: Session, req: OverrideRequest) -> list[dict[str, Any]]:
    s.space_use_overrides[req.global_id] = str(req.value)
    space = s.find_space(req.global_id)
    if not space:
        return []
    factor_info = get_default_factor_for_use_class(str(req.value))
    space["use_class"] = str(req.value)
    space["use_class_source"] = "user_override"
    space["use_class_accommodation"] = factor_info.get("accommodation") if factor_info else None
    if factor_info:
        space["factor"] = factor_info["factor"]
        space["factor_type"] = factor_info["factor_type"]
        if factor_info["factor_type"] == "area_per_person_m2" and space.get("area_m2"):
            cap, _ = compute_capacity(space["area_m2"], factor_info["factor"], factor_info["factor_type"])
            space["occupant_capacity"] = cap
            space["capacity_source"] = "table_b1_factor"
    return _recheck_doors_of_space(s, req.global_id, space)


def _override_occupancy(s: Session, req: OverrideRequest) -> list[dict[str, Any]]:
    s.space_occupancy_overrides[req.global_id] = int(req.value)
    space = s.find_space(req.global_id)
    if not space:
        return []
    space["occupant_capacity"] = int(req.value)
    space["capacity_source"] = "user_input"
    return _recheck_doors_of_space(s, req.global_id, space)


def _override_threshold(s: Session, req: OverrideRequest) -> list[dict[str, Any]]:
    """单条阈值覆盖 — 合并入 custom_threshold_table 后整体重算。

    向后兼容: 旧前端 POST /override {type:"threshold"} 仍可用,
    内部转成 custom_threshold_table 中对应档位更新。
    """
    import copy
    to = req.value
    if not isinstance(to, dict) or "capacity_min" not in to or "min_width_per_door_mm" not in to:
        raise HTTPException(status_code=400, detail={
            "error": "invalid_threshold_override", "detail": "value must have capacity_min, capacity_max(optional), min_width_per_door_mm"})
    cmin = int(to["capacity_min"])
    cmax = to.get("capacity_max")
    new_w = float(to["min_width_per_door_mm"])
    # 深拷贝当前 table (避免污染 presets cache)
    cur_table = copy.deepcopy(s.get_threshold_table())
    updated = False
    for row in cur_table:
        row_cmin = row.get("capacity_min")
        row_cmax = row.get("capacity_max")
        if row_cmin == cmin and ((row_cmax is None and cmax is None) or row_cmax == cmax):
            row["min_width_per_door_mm"] = new_w
            updated = True
            break
    if not updated:
        raise HTTPException(status_code=400, detail={
            "error": "band_not_found", "detail": f"no band capacity_min={cmin} capacity_max={cmax} in current table"})
    s.set_custom_threshold_table(cur_table)
    return _recheck_all_doors(s)


def _override_storey(s: Session, req: OverrideRequest) -> list[dict[str, Any]]:
    if req.type == "storey_sprinkler":
        s.storey_sprinkler_overrides[req.global_id] = bool(req.value)
    else:
        s.storey_entrance_overrides[req.global_id] = bool(req.value)
    storey = s.find_storey(req.global_id)
    if storey:
        if req.type == "storey_sprinkler":
            storey["has_sprinkler"] = bool(req.value)
        else:
            storey["is_entrance_level"] = bool(req.value)
    return []


def _override_checked(s: Session, req: OverrideRequest) -> list[dict[str, Any]]:
    s.door_checked_overrides[req.global_id] = bool(req.value)
    door = s.find_door(req.global_id)
    if door:
        door["is_checked"] = bool(req.value)
    return []


def _recheck_all_doors(s: Session) -> list[dict[str, Any]]:
    affected: list[dict[str, Any]] = []
    custom_table = s.get_threshold_table()
    for d in s.result.get("doors", []):
        space_gid = d.get("space_global_id")
        space = s.find_space(space_gid) if space_gid else None
        if not space:
            space = {"capacity": None, "capacity_source": "unknown"}
        new_result = check_door(d, space, custom_threshold_table=custom_table)
        d["check_result"] = new_result
        affected.append(new_result)
    return affected


def _recheck_doors_of_space(s: Session, space_gid: str, space: dict) -> list[dict[str, Any]]:
    affected: list[dict[str, Any]] = []
    custom_table = s.get_threshold_table()
    for d in s.result.get("doors", []):
        if d.get("space_global_id") != space_gid:
            continue
        new_result = check_door(d, space, custom_threshold_table=custom_table)
        d["check_result"] = new_result
        affected.append(new_result)
    return affected


def _rebuild_summary(doors: list[dict[str, Any]]) -> dict[str, Any]:
    by_status = {"pass": 0, "fail": 0, "non_passage": 0}
    fire_exit_count = 0
    needs_review_count = 0
    fails: list[dict[str, Any]] = []
    for d in doors:
        cr = d.get("check_result") or {}
        status = cr.get("status", "non_passage")
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
        "total_doors": len(doors),
        "checked_doors": fire_exit_count,
        "by_status": by_status,
        "needs_review_count": needs_review_count,
        "top_fails": fails[:5],
    }
