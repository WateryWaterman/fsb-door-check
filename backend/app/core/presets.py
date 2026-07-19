"""法规预设层 — 加载 regulation_presets.json + longname_to_a1.json,提供查询接口。

对应 docs/CONTRACT.md §6 来源标签枚举。
对应 taskrequest/ifc_field_fill_rate.md §三 修正后的流水线。
对应 taskrequest/occupant_capacity_research.md Table B1 / B2 / Clause B13.4 / B30.3。
"""
import json
import re
from pathlib import Path
from typing import Any, Optional

PRESETS_DIR = Path(__file__).parent.parent.parent / "presets"
REGULATION_PRESETS_PATH = PRESETS_DIR / "regulation_presets.json"
LONGNAME_MAP_PATH = PRESETS_DIR / "longname_to_a1.json"

_cache: dict[str, Any] = {}


def _keyword_match(text: str, keyword: str) -> bool:
    """单词边界匹配, 避免短词误匹配(如 'lab' 误匹配 'available')。

    字母前后用非字母作边界(. / - 空格 等都算边界)。
    关键词首尾空格被 trim(原 'bar ' 带尾空格是为了子串匹配, 现已不需要)。
    """
    kw = keyword.lower().strip()
    if not kw:
        return False
    pattern = r'(?<![a-z])' + re.escape(kw) + r'(?![a-z])'
    return bool(re.search(pattern, text))


def load_presets() -> dict[str, Any]:
    if "presets" not in _cache:
        with open(REGULATION_PRESETS_PATH, "r", encoding="utf-8") as f:
            _cache["presets"] = json.load(f)
    return _cache["presets"]


def load_longname_map() -> dict[str, Any]:
    if "longname_map" not in _cache:
        with open(LONGNAME_MAP_PATH, "r", encoding="utf-8") as f:
            _cache["longname_map"] = json.load(f)
    return _cache["longname_map"]


def table_b2_lookup(capacity: Optional[int]) -> Optional[dict[str, Any]]:
    """按 occupant capacity 查 Table B2 档位。

    - capacity <= 3 返回 None(Table B2 不适用, 走 Clause B13.4 绝对下限)
    - capacity > 3000 返回最后一档(字段为 null, 表示 BA 个案核定)
    - 否则返回匹配的 row
    """
    if capacity is None or capacity <= 3:
        return None
    presets = load_presets()
    for row in presets["table_b2_thresholds"]:
        cmin = row["capacity_min"]
        cmax = row["capacity_max"]
        if cmax is None:
            if capacity >= cmin:
                return row
        elif cmin <= capacity <= cmax:
            return row
    return None


def get_absolute_minimum_door_width_mm() -> int:
    """Clause B13.4: capacity>3 时门 >=750mm 的绝对下限。"""
    return load_presets()["absolute_minimums"]["clause_b13_4"]["min_door_width_mm"]


def get_absolute_minimum_double_leaf_mm() -> int:
    """Clause B13.4: 双扇门任一扇 >=600mm。"""
    return load_presets()["absolute_minimums"]["clause_b13_4"]["min_double_leaf_panel_mm"]


def get_temporary_refuge_min_width_mm() -> int:
    """Clause B30.3: 通向临时避难空间的门 >=850mm。"""
    return load_presets()["absolute_minimums"]["clause_b30_3"]["min_clear_width_mm"]


def is_excluded_space(longname: Optional[str]) -> bool:
    """判断空间是否被排除(不计入 capacity 推算),如厕所/走廊/楼梯/电梯。"""
    if not longname:
        return False
    text = longname.lower()
    for kw in load_longname_map()["excluded_keywords"]:
        if _keyword_match(text, kw):
            return True
    return False


def match_longname_to_use_class(longname: Optional[str]) -> dict[str, Any]:
    """LongName 关键词 → Table A1 Use Class 映射。

    返回字段对齐 docs/CONTRACT.md:
        use_class, accommodation, factor, factor_type, confidence, source, note
    source ∈ {"longname_keyword", "excluded", "ambiguous", "unknown"}
    """
    result: dict[str, Any] = {
        "use_class": None,
        "accommodation": None,
        "factor": None,
        "factor_type": "unknown",
        "confidence": "low",
        "source": "unknown",
        "note": None,
    }
    if not longname:
        return result

    text = longname.lower()
    map_data = load_longname_map()

    if is_excluded_space(longname):
        result["source"] = "excluded"
        result["note"] = "excluded space (toilet/corridor/stair/lift), not counted toward capacity"
        return result

    for entry in map_data["mapping"]:
        for kw in entry["keywords"]:
            if _keyword_match(text, kw):
                return {
                    "use_class": entry["use_class"],
                    "accommodation": entry["accommodation"],
                    "factor": entry["factor"],
                    "factor_type": entry["factor_type"],
                    "confidence": entry["confidence"],
                    "source": "longname_keyword",
                    "note": entry.get("note"),
                }

    for kw in map_data.get("ambiguous_unmatched_keywords", []):
        if _keyword_match(text, kw):
            result["source"] = "ambiguous"
            result["note"] = f"ambiguous keyword '{kw}' found, requires user override"
            return result

    return result


def get_use_class_entries(use_class: str) -> Optional[list[dict[str, Any]]]:
    """按 use_class 取 Table B1 所有 accommodation 条目。"""
    return load_presets()["table_b1_occupancy_factors"].get(use_class)


def get_default_factor_for_use_class(use_class: str) -> Optional[dict[str, Any]]:
    """按 use_class 取默认 factor(返回第一个条目, 即该 Use Class 的主 accommodation)。

    返回 {"accommodation": str, "factor": float|None, "factor_type": str} 或 None。
    设计选择: 返回第一个而非"优先 area_per_person_m2", 因为 Use Class 主语义优先
    (如 2=Hotels 需 bedspaces, 不应退化到 Dormitories 的 area/3 误算)。
    """
    entries = get_use_class_entries(use_class)
    if not entries:
        return None
    return entries[0]


def compute_capacity(area_m2: Optional[float], factor: Optional[float],
                     factor_type: str) -> tuple[Optional[int], str]:
    """按 factor_type 计算 occupant capacity。

    返回 (capacity_int_or_None, source_detail_str)。
    """
    import math
    if factor_type == "area_per_person_m2":
        if area_m2 is None or factor is None or factor <= 0:
            return None, "missing_area_or_factor"
        return math.ceil(area_m2 / factor), f"area/{factor}_m2_per_person"
    if factor_type in ("bedspaces", "seats"):
        return None, f"requires_{factor_type}_count"
    if factor_type == "bench_length_m_per_person":
        return None, "requires_bench_length"
    if factor_type == "case_by_case":
        return None, "case_by_case_by_BA"
    return None, "unknown_factor_type"
