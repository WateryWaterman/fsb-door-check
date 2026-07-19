"""4 样本回归测试 — 验证 pipeline 在所有样本上能跑通且结果合理。

跑法:
    cd D:\\ProgramData\\ArchiTestMajun\\fsb-door-check\\backend
    python -m pytest tests/test_samples.py -v -s
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.pipeline import analyze_ifc  # noqa: E402

SAMPLES_DIR = Path(__file__).parent.parent.parent.parent / "samples"

CLINIC = SAMPLES_DIR / "Clinic_Architectural_IFC2x3.ifc"
DUPLEX = SAMPLES_DIR / "Duplex_Apartment_IFC2x3.ifc"
SAMPLEHOUSE = SAMPLES_DIR / "SampleHouse_IFC4.ifc"
SNOWDON = SAMPLES_DIR / "Revit_SnowdonTower_ARC_FireRating_IFC4.ifc"


def _print_summary(name: str, r: dict) -> None:
    print(f"\n{'='*70}")
    print(f"  {name}  schema={r['schema']}")
    print(f"  counts: {r['counts']}")
    print(f"  summary: {r['summary']}")
    if r.get("warnings"):
        print(f"  warnings: {r['warnings'][:3]}")
    print(f"{'='*70}")


@pytest.fixture(scope="module")
def clinic_result():
    return analyze_ifc(CLINIC)


@pytest.fixture(scope="module")
def duplex_result():
    return analyze_ifc(DUPLEX)


@pytest.fixture(scope="module")
def samplehouse_result():
    return analyze_ifc(SAMPLEHOUSE)


@pytest.fixture(scope="module")
def snowdon_result():
    return analyze_ifc(SNOWDON)


# ============ Clinic (IFC2x3, 269 空间 + 254 门, MVP 主样本) ============

class TestClinic:
    def test_loads_and_counts(self, clinic_result):
        assert clinic_result["schema"].startswith("IFC2X3")
        assert clinic_result["counts"]["spaces"] == 269
        assert clinic_result["counts"]["doors"] == 254

    def test_all_doors_have_check_result(self, clinic_result):
        for d in clinic_result["doors"]:
            assert "check_result" in d
            assert d["check_result"]["status"] in ("pass", "fail", "unknown", "overridden")

    def test_spaces_have_area(self, clinic_result):
        has_area = sum(1 for s in clinic_result["spaces"] if s["area_m2"] is not None)
        assert has_area > 0.5 * len(clinic_result["spaces"]), "大多数空间应有面积"

    def test_doors_have_width(self, clinic_result):
        has_width = sum(1 for d in clinic_result["doors"] if d["overall_width_mm"] is not None)
        assert has_width > 0.9 * len(clinic_result["doors"]), "几乎所有门应有 OverallWidth"

    def test_some_doors_linked_to_space(self, clinic_result):
        linked = sum(1 for d in clinic_result["doors"] if d["space_global_id"])
        assert linked > 0.5 * len(clinic_result["doors"]), "IfcRelSpaceBoundary 应命中多数门"

    def test_summary_consistent(self, clinic_result):
        s = clinic_result["summary"]
        total = s["by_status"]["pass"] + s["by_status"]["fail"] + s["by_status"]["unknown"] + s["by_status"]["overridden"]
        assert total == s["total_doors"]

    def test_print_summary(self, clinic_result):
        _print_summary("Clinic_Architectural_IFC2x3", clinic_result)


# ============ Duplex (IFC2x3, 21 空间 + 14 门, 演示视频用) ============

class TestDuplex:
    def test_loads_and_counts(self, duplex_result):
        assert duplex_result["schema"].startswith("IFC2X3")
        assert duplex_result["counts"]["spaces"] >= 10
        assert duplex_result["counts"]["doors"] >= 10

    def test_all_doors_have_check_result(self, duplex_result):
        for d in duplex_result["doors"]:
            assert d["check_result"]["status"] in ("pass", "fail", "unknown", "overridden")

    def test_print_summary(self, duplex_result):
        _print_summary("Duplex_Apartment_IFC2x3", duplex_result)


# ============ SampleHouse (IFC4, 4 空间 + 3 门, IFC4 路径验证) ============

class TestSampleHouse:
    def test_loads(self, samplehouse_result):
        assert samplehouse_result["schema"].startswith("IFC4")
        assert samplehouse_result["counts"]["doors"] >= 1

    def test_all_doors_have_check_result(self, samplehouse_result):
        for d in samplehouse_result["doors"]:
            assert d["check_result"]["status"] in ("pass", "fail", "unknown", "overridden")

    def test_print_summary(self, samplehouse_result):
        _print_summary("SampleHouse_IFC4", samplehouse_result)


# ============ Snowdon Tower (IFC4, 无 IfcSpace, 不适合门检查) ============

class TestSnowdon:
    def test_loads_without_crash(self, snowdon_result):
        """Snowdon 无 IfcSpace, pipeline 应不崩溃, doors 的 capacity 都 unknown。"""
        assert snowdon_result["schema"].startswith("IFC4")

    def test_doors_unknown_capacity(self, snowdon_result):
        if snowdon_result["counts"]["doors"] == 0:
            pytest.skip("no doors in Snowdon")
        for d in snowdon_result["doors"]:
            assert d["check_result"]["status"] == "unknown"
            assert "capacity" in d["check_result"]["reason"].lower() or "excluded" in d["check_result"]["reason"].lower()

    def test_print_summary(self, snowdon_result):
        _print_summary("Revit_SnowdonTower_IFC4", snowdon_result)


# ============ 跨样本一致性 ============

class TestCrossSample:
    def test_all_results_have_required_fields(self, clinic_result, duplex_result,
                                              samplehouse_result, snowdon_result):
        """所有 check_result 必须含 CONTRACT.md §3 的字段。"""
        required = {
            "door_global_id", "preset_id", "rule_source", "rule_clause", "status",
            "threshold_mm", "threshold_source", "measured_mm", "deficit_mm",
            "occupant_capacity", "capacity_source", "width_source",
            "needs_human_review", "reason", "overridden", "human_review_notes",
        }
        for r in [clinic_result, duplex_result, samplehouse_result, snowdon_result]:
            for d in r["doors"]:
                cr = d["check_result"]
                missing = required - set(cr.keys())
                assert not missing, f"door {d['global_id']} check_result missing fields: {missing}"

    def test_status_enum_valid(self, clinic_result, duplex_result,
                               samplehouse_result, snowdon_result):
        valid = {"pass", "fail", "unknown", "overridden"}
        for r in [clinic_result, duplex_result, samplehouse_result, snowdon_result]:
            for d in r["doors"]:
                assert d["check_result"]["status"] in valid

    def test_width_source_enum_valid(self, clinic_result, duplex_result,
                                     samplehouse_result, snowdon_result):
        valid = {"clear_width", "overall_minus_lining", "overall_estimate", "geometry", "unknown"}
        for r in [clinic_result, duplex_result, samplehouse_result, snowdon_result]:
            for d in r["doors"]:
                assert d["width_source"] in valid, f"invalid width_source: {d['width_source']}"

    def test_capacity_source_enum_valid(self, clinic_result, duplex_result,
                                        samplehouse_result, snowdon_result):
        valid = {"OccupancyNumber", "AreaPerOccupant", "table_b1_factor",
                 "user_input", "unknown", "excluded"}
        for r in [clinic_result, duplex_result, samplehouse_result, snowdon_result]:
            for s in r["spaces"]:
                assert s["capacity_source"] in valid, f"invalid capacity_source: {s['capacity_source']}"

    def test_global_id_unique(self, clinic_result):
        ids = [d["global_id"] for d in clinic_result["doors"]]
        assert len(ids) == len(set(ids)), "door global_id should be unique"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
