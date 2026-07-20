"""路由 /presets — 默认预设查询。

对应 docs/SSD.md §1 前端首屏展示默认 preset + longname map。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.presets import load_longname_map, load_presets
from ..session import get_session

router = APIRouter(prefix="/presets", tags=["presets"])


@router.get("")
def get_presets():
    return {"default": load_presets(), "longname_map": load_longname_map()}


@router.get("/{sid}")
def get_session_presets(sid: str):
    s = get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail={
            "error": "session_not_found", "detail": sid})
    base = load_presets()
    if s.custom_threshold_table is not None:
        base = dict(base)
        base = {**base, "table_b2_thresholds": list(s.custom_threshold_table)}
    base["active_overrides"] = s.overrides
    return base
