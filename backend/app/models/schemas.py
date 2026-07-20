"""Pydantic schema — 严格对齐 docs/CONTRACT.md, 前后端共享字段定义。

前端实现时以本文件 + CONTRACT.md 为准, 禁止自行发明字段名。
Pydantic v2, 允许 extra 字段(向前兼容)但不依赖。
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============ 枚举(对齐 CONTRACT.md §5 §6) ============

CheckStatus = str  # "pass" | "fail" | "non_passage"
WidthSource = str  # "clear_width" | "overall_minus_lining" | "overall_estimate" | "geometry" | "unknown"
AreaSource = str  # "IfcQuantityArea.NetFloorArea" | ... | "unknown"
UseClassSource = str  # "Pset_SpaceOccupancyRequirements.OccupancyType" | "longname_keyword" | "excluded" | "ambiguous" | "unknown" | "user_override"
CapacitySource = str  # "OccupancyNumber" | "AreaPerOccupant" | "table_b1_factor" | "user_input" | "unknown" | "excluded"
FireExitSource = str  # "Pset_DoorCommon.FireExit" | "inferred_cross_space" | "inferred_name_keyword" | "inferred_to_stair" | "user_override" | "not_fire_exit"


# ============ 实体(CONTRACT.md §2) ============

class Storey(BaseModel):
    model_config = ConfigDict(extra="allow")
    global_id: str
    name: str
    long_name: Optional[str] = None
    elevation_m: Optional[float] = None
    storey_index: int = 0
    door_count: int = 0
    space_count: int = 0
    is_entrance_level: Optional[bool] = None
    has_sprinkler: Optional[bool] = None


class Space(BaseModel):
    model_config = ConfigDict(extra="allow")
    global_id: str
    name: str
    long_name: Optional[str] = None
    storey_global_id: Optional[str] = None
    area_m2: Optional[float] = None
    area_source: str = "unknown"
    use_class: Optional[str] = None
    use_class_source: str = "unknown"
    use_class_accommodation: Optional[str] = None
    use_class_confidence: str = "low"
    occupant_capacity: Optional[int] = None
    capacity_source: str = "unknown"
    factor: Optional[float] = None
    factor_type: str = "unknown"
    door_global_ids: list[str] = Field(default_factory=list)


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    door_global_id: str
    preset_id: str
    rule_source: str
    rule_clause: str
    status: str
    threshold_mm: Optional[float] = None
    threshold_source: str
    measured_mm: Optional[float] = None
    deficit_mm: Optional[float] = None
    occupant_capacity: Optional[int] = None
    capacity_source: str
    width_source: str
    needs_human_review: bool
    reason: str
    has_threshold_override: bool = False
    human_review_notes: list[str] = Field(default_factory=list)


class Door(BaseModel):
    model_config = ConfigDict(extra="allow")
    global_id: str
    name: Optional[str] = None
    long_name: Optional[str] = None
    overall_width_mm: Optional[float] = None
    overall_height_mm: Optional[float] = None
    measured_width_mm: Optional[float] = None
    width_source: str = "unknown"
    needs_human_review: bool = True
    storey_global_id: Optional[str] = None
    space_global_id: Optional[str] = None
    space_global_id_other: Optional[str] = None
    is_fire_exit: bool = False
    fire_exit_source: str = "not_fire_exit"
    fire_exit_reasons: list[str] = Field(default_factory=list)
    is_double_leaf: Optional[bool] = None
    is_checked: bool = False
    check_result: Optional[CheckResult] = None


# ============ 覆盖请求(CONTRACT.md §4) ============

class ThresholdOverride(BaseModel):
    capacity_min: int
    capacity_max: Optional[int] = None
    min_width_per_door_mm: float


class OverrideRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str  # "fire_exit" | "space_use" | "occupancy" | "threshold" | "storey_sprinkler" | "storey_entrance"
    global_id: str
    value: Any  # bool | int | str | ThresholdOverride
    note: Optional[str] = None


# ============ API 响应(CONTRACT.md §7) ============

class ModelCounts(BaseModel):
    spaces: int
    doors: int
    storeys: int
    door_types: int = 0


class Summary(BaseModel):
    total_doors: int
    checked_doors: int
    by_status: dict[str, int]
    needs_review_count: int
    top_fails: list[dict[str, Any]] = Field(default_factory=list)


class UploadResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    session_id: str
    ifc_schema: str
    counts: ModelCounts
    storeys: list[dict[str, Any]] = Field(default_factory=list)
    spaces: list[dict[str, Any]] = Field(default_factory=list)
    doors: list[dict[str, Any]] = Field(default_factory=list)
    summary: Summary
    warnings: list[str] = Field(default_factory=list)


class CheckResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    session_id: str
    checked_at: str
    results: list[CheckResult]
    summary: Summary


class DoorDetailResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    door: dict[str, Any]
    related_space: Optional[dict[str, Any]] = None
    storey: Optional[dict[str, Any]] = None


class OverrideResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    session_id: str
    applied: OverrideRequest
    affected_results: list[CheckResult] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: str
    detail: str
    hint: Optional[str] = None


class PresetsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    default: dict[str, Any]
    longname_map: dict[str, Any]
