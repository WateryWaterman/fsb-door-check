"""路由 /export — 导出检查结果(BCF/HTML/JSON)。

JSON 格式已实现: 完整结构化数据 + 字段说明字典, 供 CI/CD / LLM / dashboard 用。
BCF/HTML 仍在设计阶段, 返回 501 + EXPORT_DESIGN.md 链接。

对应 docs/EXPORT_DESIGN.md。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ..core.presets import load_presets
from ..session import get_session

router = APIRouter(tags=["export"])


@router.post("/export/{sid}")
def export_session(
    sid: str,
    fmt: str = Query(..., alias="format", description="bcf | html | json"),
):
    s = get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail={
            "error": "session_not_found", "detail": sid})
    fmt_lower = fmt.lower()
    if fmt_lower == "json":
        return _export_json(s)
    if fmt_lower in {"bcf", "html"}:
        raise HTTPException(status_code=501, detail={
            "error": "export_not_implemented",
            "detail": f"{fmt_lower} export is designed but not implemented in MVP",
            "hint": "see docs/EXPORT_DESIGN.md for the full design (BCF > HTML > JSON)",
            "design_doc": "docs/EXPORT_DESIGN.md",
            "planned_formats": {
                "bcf": "BIM Collaboration Format — Revit/Navisworks/Solibri native",
                "html": "self-contained single HTML report, email-friendly",
            },
            "session_id": sid,
            "requested_format": fmt_lower,
        })
    raise HTTPException(status_code=400, detail={
        "error": "invalid_format",
        "detail": f"unsupported format: {fmt_lower}",
        "hint": "choose one of: bcf, html, json",
    })


def _export_json(s) -> JSONResponse:
    """完整 JSON 导出 — 自包含, 含字段说明字典。"""
    presets = load_presets()
    r = s.result
    doors = r.get("doors", [])
    spaces = r.get("spaces", [])
    storeys = r.get("storeys", [])

    space_map: dict[str, dict] = {sp.get("global_id"): sp for sp in spaces}
    storey_map: dict[str, dict] = {st.get("global_id"): st for st in storeys}

    def _enrich_door(d: dict) -> dict[str, Any]:
        sp = space_map.get(d.get("space_global_id"))
        st = storey_map.get(d.get("storey_global_id"))
        out = dict(d)
        if sp:
            out["related_space"] = {
                "global_id": sp.get("global_id"),
                "name": sp.get("name"),
                "long_name": sp.get("long_name"),
                "area_m2": sp.get("area_m2"),
                "area_source": sp.get("area_source"),
                "use_class": sp.get("use_class"),
                "use_class_source": sp.get("use_class_source"),
                "use_class_accommodation": sp.get("use_class_accommodation"),
                "use_class_note": sp.get("use_class_note"),
                "capacity": sp.get("capacity"),
                "capacity_source": sp.get("capacity_source"),
                "factor": sp.get("factor"),
                "factor_type": sp.get("factor_type"),
            }
        else:
            out["related_space"] = None
        if st:
            out["storey_name"] = st.get("name")
        return out

    enriched_doors = [_enrich_door(d) for d in doors]

    data: dict[str, Any] = {
        "export_meta": {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "tool": "FSB Door Check MVP",
            "format_version": "1.0",
            "note": "Self-contained JSON export. See field_dictionary below for field meanings.",
        },
        "session": {
            "session_id": s.id,
            "filename": s.filename,
            "ifc_schema": s.schema,
            "counts": {
                "spaces": len(spaces),
                "doors": len(doors),
                "storeys": len(storeys),
            },
        },
        "regulation": {
            "preset_id": presets["preset_id"],
            "preset_version": presets.get("preset_version"),
            "jurisdiction": presets.get("jurisdiction"),
            "code": presets.get("code"),
            "code_short": presets.get("code_short"),
            "scope": presets.get("scope"),
            "rule_source": presets.get("rule_source"),
            "rule_link": presets.get("rule_link"),
            "table_b2_thresholds": presets.get("table_b2_thresholds"),
            "absolute_minimums": presets.get("absolute_minimums"),
            "custom_threshold_table": s.custom_threshold_table,
            "use_classes": presets.get("use_classes"),
        },
        "summary": r.get("summary"),
        "storeys": storeys,
        "spaces": spaces,
        "doors": enriched_doors,
        "overrides": s.overrides,
        "field_dictionary": _field_dictionary(),
    }

    return JSONResponse(
        content=data,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="fsb_export_{s.filename}.json"',
        },
    )


def _field_dictionary() -> dict[str, str]:
    """字段说明字典 — 每个 JSON 字段的含义、来源、可能取值。"""
    return {
        # export_meta
        "export_meta.exported_at": "导出时间 (UTC ISO 8601)",
        "export_meta.tool": "导出工具名称",
        "export_meta.format_version": "JSON 格式版本 (当前 1.0)",

        # session
        "session.session_id": "后端会话 ID (重启后失效, 仅用于调试)",
        "session.filename": "上传的 IFC 文件名",
        "session.ifc_schema": "IFC 规范版本 (IFC2X3_TC1 / IFC4 / IFC4X3_ADD2 等)",
        "session.counts": "模型元素计数 (spaces / doors / storeys)",

        # regulation
        "regulation.preset_id": "法规预设 ID (hk_fsb_2011_b2_default)",
        "regulation.rule_source": "适用法规全称",
        "regulation.rule_link": "法规 PDF 链接 (BD 官网)",
        "regulation.table_b2_thresholds": "Table B2 完整 14 档阈值表 (capacity_min/max, min_doors, min_width_per_door_mm)",
        "regulation.absolute_minimums": "Clause B13.4 绝对下限 (750mm 单门 / 600mm 双扇单叶) + B30.3 避难层 (850mm)",
        "regulation.custom_threshold_table": "用户自定义阈值表 (null=用默认; 非空=用户改过的 Table B2)",
        "regulation.use_classes": "Table B1 Use Class 16 类描述 (1b~8)",

        # summary
        "summary.total_doors": "门总数",
        "summary.by_status": "按状态统计: pass(达标) / fail(不达标) / non_passage(不适用/无法判定)",
        "summary.needs_review_count": "需人工复核门数 (width_source 非 clear_width 或双扇门)",
        "summary.top_fails": "失败门 Top 5 (按 deficit_mm 降序)",

        # door fields
        "doors[].global_id": "IFC GlobalId — 22 字符 base64 唯一标识",
        "doors[].name": "IfcDoor.Name — 门名称 (Revit 族类型:尺寸)",
        "doors[].overall_width_mm": "IfcDoor.OverallWidth — 门总宽 (mm), 含门框",
        "doors[].overall_height_mm": "IfcDoor.OverallHeight — 门总高 (mm)",
        "doors[].measured_width_mm": "用于合规检查的门宽 (mm), 当前=OverallWidth (代理值)",
        "doors[].width_source": "门宽数据来源: overall_estimate(OverallWidth 代理) | clear_width(实测) | unknown",
        "doors[].needs_human_review": "是否需人工复核 (width_source≠clear_width 或双扇门 → true)",
        "doors[].is_fire_exit": "是否为疏散门 (推断: 跨空间/名字关键词/用户标记)",
        "doors[].fire_exit_source": "疏散门判定来源: inferred_cross_space | inferred_name_keyword | inferred_to_stair | user_override | not_fire_exit",
        "doors[].fire_exit_reasons": "疏散门推断理由列表 (如 'crosses two spaces via IfcRelSpaceBoundary')",
        "doors[].is_double_leaf": "是否为双扇门 (IfcDoor.OperationType 前缀 DOUBLE_DOOR)",
        "doors[].double_leaf_source": "双扇判定来源: operation_type_occurrence | operation_type_type | unknown",
        "doors[].is_checked": "人工已复核标记 (用户手动勾选, 不影响合规计算)",
        "doors[].space_global_id": "主关联空间 GlobalId (IfcRelSpaceBoundary)",
        "doors[].space_global_id_other": "次关联空间 GlobalId (门跨两个空间时)",
        "doors[].storey_global_id": "所在楼层 GlobalId",
        "doors[].storey_name": "所在楼层名称",

        # check_result
        "doors[].check_result.status": "合规状态: pass(达标) | fail(不达标) | non_passage(不适用/无法判定)",
        "doors[].check_result.rule_clause": "适用条款: B7.1(Table B2, capacity>3) | B13.4(绝对下限, capacity≤3 或双扇) | N/A(排除空间)",
        "doors[].check_result.threshold_mm": "门宽阈值 (mm), 来自 Table B2 或 Clause B13.4",
        "doors[].check_result.threshold_source": "阈值来源: Table B2 row[x-y] | Clause B13.4 | user_override | excluded_space",
        "doors[].check_result.measured_mm": "实测门宽 (mm), 当前=OverallWidth",
        "doors[].check_result.deficit_mm": "缺口 (mm) = threshold - measured, 正值=不够宽 (FAIL)",
        "doors[].check_result.occupant_capacity": "关联空间人数容量",
        "doors[].check_result.capacity_source": "容量来源: table_b1_factor | user_input | excluded | unknown",
        "doors[].check_result.needs_human_review": "需人工复核 (同 doors[].needs_human_review, 但 override 后可能变化)",
        "doors[].check_result.reason": "判定理由 (自然语言, 如 'capacity=10, requires 850mm, measured 900mm -> pass')",
        "doors[].check_result.has_threshold_override": "是否因用户覆盖阈值而重算",
        "doors[].check_result.human_review_notes": "人工复核提示列表 (如双扇门估算提示、width_source 代理提示)",

        # related_space
        "doors[].related_space": "门关联的 IfcSpace 信息 (null=无关联空间)",
        "doors[].related_space.long_name": "IfcSpace.LongName — 空间名称 (如 'CORRIDOR', 'OFFICE 101')",
        "doors[].related_space.area_m2": "空间面积 (m²), 优先 NetFloorArea / GSA BIM Area",
        "doors[].related_space.use_class": "Table B1 Use Class (1b~8), null=未匹配/排除",
        "doors[].related_space.use_class_source": "UseClass 来源: longname_keyword | user_override | excluded | unknown",
        "doors[].related_space.use_class_note": "UseClass 备注 (如 'excluded space, not counted toward capacity')",
        "doors[].related_space.capacity": "空间人数容量 (0=排除空间, null=未知, >0=有效)",
        "doors[].related_space.capacity_source": "容量来源: table_b1_factor | user_input | excluded | unknown",
        "doors[].related_space.factor": "Table B1 占用因子 (m²/人, 或 bedspaces/seats)",
        "doors[].related_space.factor_type": "因子类型: area_per_person_m2 | bedspaces | seats | case_by_case",

        # overrides
        "overrides": "用户覆盖操作历史列表 (按时间顺序)",
        "overrides[].type": "覆盖类型: fire_exit | space_use | occupancy | threshold | storey_sprinkler | storey_entrance | checked",
        "overrides[].global_id": "覆盖目标的 GlobalId (门/空间/楼层)",
        "overrides[].value": "覆盖值 (bool/int/str/object)",
    }
