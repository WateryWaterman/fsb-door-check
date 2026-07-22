"""路由 /export — 导出检查结果(BCF/HTML/JSON) + 邮件报告。

JSON 格式已实现: 完整结构化数据 + 字段说明字典, 供 CI/CD / LLM / dashboard 用。
BCF/HTML 仍在设计阶段, 返回 501 + EXPORT_DESIGN.md 链接。
POST /export/{sid}/email_report: DeepSeek 生成 Markdown 质检报告 → Resend 发邮件。

对应 docs/EXPORT_DESIGN.md。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..core.presets import load_presets
from ..session import get_session

logger = logging.getLogger("fsb.export")

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
    data = _build_export_data(s)
    return JSONResponse(
        content=data,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="fsb_export_{s.filename}.json"',
        },
    )


def _build_export_data(s) -> dict[str, Any]:
    """构建完整导出数据 dict — 被 _export_json 和 email_report 复用。"""
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

    return {
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


# ============ Email Report ============

class EmailReportOptions(BaseModel):
    focus_fail_only: bool = False
    storey_filter: Optional[str] = None


class EmailReportRequest(BaseModel):
    email: str
    options: EmailReportOptions = Field(default_factory=EmailReportOptions)


@router.post("/export/{sid}/email_report")
def email_report(sid: str, body: EmailReportRequest):
    s = get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail={"error": "session_not_found", "detail": sid})

    summary = s.result.get("summary") or {}
    if summary.get("total_doors", 0) == 0:
        raise HTTPException(status_code=400, detail={
            "error": "no_results",
            "detail": "模型尚未完成检查，请先 Run Check",
        })

    export_data = _build_export_data(s)
    report_input = _build_report_input(export_data, body.options)

    markdown, llm_used = _generate_markdown(report_input)
    if markdown is None:
        raise HTTPException(status_code=502, detail={
            "error": "report_generation_failed",
            "detail": "DeepSeek 不可用且降级逻辑也未生成报告",
        })

    resend_result = _send_email_resend(body.email, sid, s.filename, markdown)
    if not resend_result["ok"]:
        return JSONResponse(status_code=502, content={
            "status": "send_failed",
            "email": body.email,
            "session_id": sid,
            "llm_used": llm_used,
            "markdown": markdown,
            "error": resend_result["error"],
            "detail": resend_result["detail"],
        })

    return {
        "status": "sent",
        "email": body.email,
        "session_id": sid,
        "llm_used": llm_used,
        "message_id": resend_result.get("message_id"),
    }


def _build_report_input(export_data: dict, options: EmailReportOptions) -> dict:
    """从完整 export data 压缩成 LLM 友好的 report_input。"""
    session = export_data.get("session", {})
    regulation = export_data.get("regulation", {})
    summary = export_data.get("summary") or {}
    doors = export_data.get("doors", [])
    overrides = export_data.get("overrides", [])

    doors_filtered = doors
    if options.storey_filter:
        doors_filtered = [d for d in doors if d.get("storey_name") == options.storey_filter]

    by_status = summary.get("by_status", {})

    storey_fail: dict[str, int] = {}
    for d in doors_filtered:
        cr = d.get("check_result") or {}
        if cr.get("status") == "fail":
            sn = d.get("storey_name") or "Unknown"
            storey_fail[sn] = storey_fail.get(sn, 0) + 1

    override_counts: dict[str, int] = {}
    use_class_overrides: list[str] = []
    for ov in overrides:
        t = ov.get("type", "unknown")
        override_counts[t] = override_counts.get(t, 0) + 1
        if t == "space_use":
            v = ov.get("value")
            if isinstance(v, str):
                use_class_overrides.append(v)

    fail_doors = [d for d in doors_filtered if (d.get("check_result") or {}).get("status") == "fail"]
    fail_doors_sorted = sorted(fail_doors, key=lambda d: (d.get("check_result") or {}).get("deficit_mm") or 0, reverse=True)
    fail_samples = []
    for d in fail_doors_sorted[:5]:
        cr = d.get("check_result") or {}
        sp = d.get("related_space") or {}
        fail_samples.append({
            "door_id": d.get("global_id", "")[:12],
            "name": d.get("name"),
            "storey": d.get("storey_name"),
            "use_class": sp.get("use_class"),
            "capacity": cr.get("occupant_capacity"),
            "measured_mm": cr.get("measured_mm"),
            "threshold_mm": cr.get("threshold_mm"),
            "deficit_mm": cr.get("deficit_mm"),
            "is_custom_threshold": cr.get("has_threshold_override", False),
            "reason": cr.get("reason"),
        })

    review_doors = [d for d in doors_filtered if (d.get("check_result") or {}).get("needs_human_review")]
    review_samples = []
    for d in review_doors[:3]:
        cr = d.get("check_result") or {}
        review_samples.append({
            "door_id": d.get("global_id", "")[:12],
            "width_source": d.get("width_source"),
            "fire_exit_source": d.get("fire_exit_source"),
            "is_double_leaf": d.get("is_double_leaf"),
            "notes": cr.get("human_review_notes", []),
        })

    return {
        "model_info": {
            "filename": session.get("filename"),
            "ifc_schema": session.get("ifc_schema"),
            "counts": session.get("counts", {}),
        },
        "check_stats": {
            "pass": by_status.get("pass", 0),
            "fail": by_status.get("fail", 0),
            "non_passage": by_status.get("non_passage", 0),
            "needs_review": summary.get("needs_review_count", 0),
            "total_doors": summary.get("total_doors", 0),
        },
        "threshold_state": {
            "has_custom": regulation.get("custom_threshold_table") is not None,
            "custom_bands": regulation.get("custom_threshold_table"),
            "default_bands": regulation.get("table_b2_thresholds"),
        },
        "user_overrides": {
            "counts": override_counts,
            "use_class_types": use_class_overrides,
        },
        "storey_stats": storey_fail,
        "door_samples": {
            "fail_representatives": fail_samples,
            "needs_review_representatives": review_samples,
        },
        "options": {
            "focus_fail_only": options.focus_fail_only,
            "storey_filter": options.storey_filter,
        },
    }


# ============ DeepSeek 调用 ============

_DEEPSEEK_SYSTEM_PROMPT = """你是一位建筑消防合规审查助手。根据输入的 JSON 数据，生成一份 Markdown 格式的门净宽质检报告。

报告必须严格包含以下 6 个段落，每段用 ## 标题：
1. 抬头 — 模型文件名、IFC 版本、门/空间/楼层总数、检查时间
2. 总体概况 — pass/fail/non_passage 分布、需复核门数、通过率
3. 规则与原因 — 本次检查依据的法规（HK FSB 2011 Table B2 + Clause B13.4）、各状态的主要原因
4. 重点问题与典型门 — 列出 fail 代表性门（门ID/楼层/用途/人数/实测宽/阈值/缺口）、需人工复核的典型问题（宽度代理值/疏散门推断/双扇门估算）
5. 用户修改影响 — 用户做了哪些覆盖（空间用途/人数/阈值表/防火门/勾选）、是否使用了自定义阈值
6. 建议 — 针对当前 fail 门和复核需求的下一步行动建议

要求：
- 全中文输出（门ID、数值、字段名保持原文）
- 总长度 800-1200 字
- 纯 Markdown，不要包裹在代码块里
- 数据驱动，不要空话套话
- 如果 fail=0，在第 4 段说明"本次检查全部达标"并仍列出需复核项
"""


def _generate_markdown(report_input: dict) -> tuple[Optional[str], bool]:
    """调用 DeepSeek 生成 Markdown, 最多重试 2 次。失败走降级。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY not set, using fallback markdown")
        return _fallback_markdown(report_input), False

    api_base = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model = os.environ.get("DEEPSEEK_MODEL_NAME", "deepseek-chat")
    url = f"{api_base.rstrip('/')}/chat/completions"

    user_content = json.dumps(report_input, ensure_ascii=False, indent=2)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _DEEPSEEK_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.3,
        "max_tokens": 2048,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for attempt in range(3):
        try:
            with httpx.Client(timeout=30.0) as client:
                r = client.post(url, json=payload, headers=headers)
            if r.status_code == 429:
                logger.warning("DeepSeek 429 rate limit, attempt %d", attempt + 1)
                if attempt < 2:
                    continue
                break
            if r.status_code >= 500:
                logger.warning("DeepSeek server error %d, attempt %d", r.status_code, attempt + 1)
                if attempt < 2:
                    continue
                break
            r.raise_for_status()
            data = r.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content.strip():
                return content.strip(), True
            logger.warning("DeepSeek returned empty content, attempt %d", attempt + 1)
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            logger.warning("DeepSeek network error: %s, attempt %d", e, attempt + 1)
            if attempt < 2:
                continue
        except Exception as e:
            logger.warning("DeepSeek unexpected error: %s, attempt %d", e, attempt + 1)
            if attempt < 2:
                continue
            break

    logger.warning("DeepSeek failed after retries, using fallback markdown")
    return _fallback_markdown(report_input), False


def _fallback_markdown(ri: dict) -> str:
    """纯逻辑拼接降级 Markdown — 仅总体概况 + 简短建议。"""
    mi = ri.get("model_info", {})
    cs = ri.get("check_stats", {})
    ts = ri.get("threshold_state", {})
    uo = ri.get("user_overrides", {})
    ss = ri.get("storey_stats", {})
    ds = ri.get("door_samples", {})
    total = cs.get("total_doors", 0)
    pass_n = cs.get("pass", 0)
    fail_n = cs.get("fail", 0)
    non_p = cs.get("non_passage", 0)
    review_n = cs.get("needs_review", 0)
    rate = f"{pass_n / total * 100:.1f}%" if total > 0 else "N/A"

    lines = [
        f"## 抬头",
        f"模型: {mi.get('filename', 'unknown')} | IFC 版本: {mi.get('ifc_schema', 'unknown')} | "
        f"门: {total} | 空间: {mi.get('counts', {}).get('spaces', '?')} | 楼层: {mi.get('counts', {}).get('storeys', '?')}",
        f"",
        f"## 总体概况",
        f"PASS: {pass_n} | FAIL: {fail_n} | NON-PASSAGE: {non_p} | 需复核: {review_n} | 通过率: {rate}",
        f"",
        f"## 规则与原因",
        f"依据: HK FSB 2011 (2024) Part B, Table B2 + Clause B13.4。",
        f"FAIL 主要原因: 门实测宽度低于 Table B2 对应容量档位的阈值要求。",
        f"NON-PASSAGE 原因: 空间被排除(厕所/走廊等)、容量未知、或宽度数据缺失。",
        f"",
        f"## 重点问题与典型门",
    ]
    fails = ds.get("fail_representatives", [])
    if fails:
        for f in fails[:5]:
            lines.append(
                f"- 门 {f.get('door_id')}: {f.get('name', '')} | 楼层 {f.get('storey', '?')} | "
                f"用途 {f.get('use_class', '?')} | 人数 {f.get('capacity', '?')} | "
                f"实测 {f.get('measured_mm', '?')}mm / 阈值 {f.get('threshold_mm', '?')}mm | "
                f"缺口 {f.get('deficit_mm', '?')}mm"
            )
    else:
        lines.append("本次检查无 FAIL 门。")

    reviews = ds.get("needs_review_representatives", [])
    if reviews:
        lines.append("")
        lines.append("需人工复核典型:")
        for rv in reviews[:3]:
            notes = "; ".join(rv.get("notes", [])) or "无"
            lines.append(
                f"- 门 {rv.get('door_id')}: width_source={rv.get('width_source', '?')}, "
                f"fire_exit_source={rv.get('fire_exit_source', '?')}, "
                f"is_double_leaf={rv.get('is_double_leaf', '?')} | {notes}"
            )

    lines.extend([
        f"",
        f"## 用户修改影响",
    ])
    counts = uo.get("counts", {})
    if counts:
        parts = [f"{k}: {v}" for k, v in counts.items()]
        lines.append(f"覆盖操作: {', '.join(parts)}")
        uc_types = uo.get("use_class_types", [])
        if uc_types:
            lines.append(f"UseClass 覆盖类型: {', '.join(uc_types)}")
    else:
        lines.append("本次检查未进行用户覆盖操作。")
    if ts.get("has_custom"):
        lines.append("使用了自定义阈值表。")
    else:
        lines.append("使用默认 Table B2 阈值表。")

    lines.extend([
        f"",
        f"## 建议",
    ])
    if fail_n > 0:
        lines.append(f"1. 优先处理 {fail_n} 扇 FAIL 门, 尤其是缺口最大的门。")
    else:
        lines.append("1. 本次检查全部达标, 但仍需关注需复核项。")
    if review_n > 0:
        lines.append(f"2. {review_n} 扇门需人工复核, 主要因为门宽为代理值(OverallWidth)而非实测净宽。")
    if ss:
        worst_storey = max(ss, key=ss.get)
        lines.append(f"3. 楼层 {worst_storey} FAIL 门最多({ss[worst_storey]} 扇), 建议优先排查。")
    lines.append("4. 建议现场实测 FAIL 门的实际净宽, 以代理值仅为初步筛查。")

    return "\n".join(lines)


# ============ Resend 发邮件 ============

def _send_email_resend(to_email: str, sid: str, filename: str, markdown: str) -> dict:
    """调 Resend API 发邮件, 返回 {ok, message_id?, error?, detail?}。"""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        return {"ok": False, "error": "resend_not_configured", "detail": "RESEND_API_KEY 环境变量未设置"}

    from_email = os.environ.get("REPORT_FROM_EMAIL")
    if not from_email:
        return {"ok": False, "error": "resend_not_configured", "detail": "REPORT_FROM_EMAIL 环境变量未设置"}

    prefix = os.environ.get("REPORT_EMAIL_SUBJECT_PREFIX", "[FSB Door Check]")
    subject = f"{prefix} {filename} - {sid[:8]}"
    html_body = f"<pre style=\"font-family: monospace; font-size: 13px; white-space: pre-wrap;\">{markdown}</pre>"

    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "text": markdown,
        "html": html_body,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post("https://api.resend.com/emails", json=payload, headers=headers)
        if r.status_code >= 400:
            detail = r.text[:200]
            logger.error("Resend error %d: %s", r.status_code, detail)
            return {"ok": False, "error": f"resend_http_{r.status_code}", "detail": detail}
        data = r.json()
        return {"ok": True, "message_id": data.get("id")}
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        logger.error("Resend network error: %s", e)
        return {"ok": False, "error": "resend_network_error", "detail": str(e)}
    except Exception as e:
        logger.error("Resend unexpected error: %s", e)
        return {"ok": False, "error": "resend_unexpected", "detail": str(e)}
