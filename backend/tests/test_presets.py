"""法规预设层单测 — 验证 Table B2 档位查询 + LongName 关键词映射。

跑法:
    cd D:\\ProgramData\\ArchiTestMajun\\fsb-door-check\\backend
    python -m pytest tests/test_presets.py -v
或:
    python -m unittest tests.test_presets -v
"""
import os
import sys
from pathlib import Path

# 让 tests/ 能 import 到 app/
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core import presets  # noqa: E402


# ============ Table B2 档位查询 ============

class TestTableB2Lookup:
    def test_capacity_le_3_returns_none(self):
        assert presets.table_b2_lookup(0) is None
        assert presets.table_b2_lookup(1) is None
        assert presets.table_b2_lookup(2) is None
        assert presets.table_b2_lookup(3) is None
        assert presets.table_b2_lookup(None) is None

    def test_first_tier_4_to_30(self):
        row = presets.table_b2_lookup(4)
        assert row is not None
        assert row["capacity_min"] == 4
        assert row["capacity_max"] == 30
        assert row["min_width_per_door_mm"] == 750
        row = presets.table_b2_lookup(30)
        assert row["min_width_per_door_mm"] == 750

    def test_second_tier_31_to_200(self):
        row = presets.table_b2_lookup(31)
        assert row["min_width_per_door_mm"] == 850
        assert row["min_doors"] == 2
        row = presets.table_b2_lookup(200)
        assert row["min_width_per_door_mm"] == 850

    def test_tier_201_to_300(self):
        assert presets.table_b2_lookup(201)["min_width_per_door_mm"] == 1050
        assert presets.table_b2_lookup(300)["min_width_per_door_mm"] == 1050

    def test_tier_501_to_750_three_doors(self):
        row = presets.table_b2_lookup(501)
        assert row["min_doors"] == 3
        assert row["min_width_per_door_mm"] == 1200

    def test_tier_751_to_1000_four_doors(self):
        assert presets.table_b2_lookup(751)["min_doors"] == 4

    def test_tier_1001_to_1250_1350mm(self):
        assert presets.table_b2_lookup(1001)["min_width_per_door_mm"] == 1350

    def test_tier_2751_to_3000_1500mm(self):
        row = presets.table_b2_lookup(3000)
        assert row["min_width_per_door_mm"] == 1500
        assert row["min_doors"] == 12

    def test_over_3000_ba_case(self):
        """capacity > 3000 由 BA 个案核定, 返回最后一档(字段为 null)。"""
        row = presets.table_b2_lookup(3001)
        assert row is not None
        assert row["capacity_max"] is None
        assert row["min_width_per_door_mm"] is None
        assert "note" in row
        row = presets.table_b2_lookup(99999)
        assert row["capacity_max"] is None

    def test_boundary_values(self):
        """档位边界: 30 vs 31, 200 vs 201, ..."""
        assert presets.table_b2_lookup(30)["min_width_per_door_mm"] == 750
        assert presets.table_b2_lookup(31)["min_width_per_door_mm"] == 850
        assert presets.table_b2_lookup(200)["min_width_per_door_mm"] == 850
        assert presets.table_b2_lookup(201)["min_width_per_door_mm"] == 1050
        assert presets.table_b2_lookup(500)["min_width_per_door_mm"] == 1050
        assert presets.table_b2_lookup(501)["min_width_per_door_mm"] == 1200


# ============ 绝对下限 ============

class TestAbsoluteMinimums:
    def test_clause_b13_4_min_750(self):
        assert presets.get_absolute_minimum_door_width_mm() == 750

    def test_clause_b13_4_double_leaf_600(self):
        assert presets.get_absolute_minimum_double_leaf_mm() == 600

    def test_clause_b30_3_refuge_850(self):
        assert presets.get_temporary_refuge_min_width_mm() == 850


# ============ LongName 关键词映射 ============

class TestMatchLongname:
    def test_office_high_confidence(self):
        r = presets.match_longname_to_use_class("Open Plan Office")
        assert r["use_class"] == "4a"
        assert r["factor"] == 9
        assert r["confidence"] == "high"
        assert r["source"] == "longname_keyword"

    def test_case_insensitive(self):
        r = presets.match_longname_to_use_class("OFFICE AREA")
        assert r["use_class"] == "4a"

    def test_meeting_room(self):
        r = presets.match_longname_to_use_class("Meeting Room 101")
        assert r["use_class"] == "4a"

    def test_consultation_clinic(self):
        """Clinic 样本常见: Consultation Room → 3a"""
        r = presets.match_longname_to_use_class("Consultation Room")
        assert r["use_class"] == "3a"
        assert r["factor"] == 9

    def test_waiting_excluded_or_ambiguous(self):
        """waiting 在 ambiguous 列表里 → source=ambiguous"""
        r = presets.match_longname_to_use_class("Waiting Area")
        assert r["source"] in ("ambiguous", "unknown")
        assert r["use_class"] is None

    def test_toilet_excluded(self):
        r = presets.match_longname_to_use_class("Mens Toilet")
        assert r["source"] == "excluded"
        assert r["use_class"] is None

    def test_corridor_excluded(self):
        r = presets.match_longname_to_use_class("Corridor 1F")
        assert r["source"] == "excluded"

    def test_lift_lobby_excluded(self):
        r = presets.match_longname_to_use_class("Lift Lobby")
        assert r["source"] == "excluded"

    def test_stair_excluded(self):
        r = presets.match_longname_to_use_class("Staircase 1")
        assert r["source"] == "excluded"

    def test_living_room_flat(self):
        r = presets.match_longname_to_use_class("Living Room")
        assert r["use_class"] == "1b"
        assert r["factor"] == 9

    def test_bedroom_flat(self):
        r = presets.match_longname_to_use_class("Master Bedroom")
        assert r["use_class"] == "1b"

    def test_dining_restaurant(self):
        r = presets.match_longname_to_use_class("Dining Hall")
        assert r["use_class"] == "4b"
        assert r["factor"] == 1

    def test_classroom_5b(self):
        r = presets.match_longname_to_use_class("Classroom 201")
        assert r["use_class"] == "5b"
        assert r["factor"] == 2

    def test_gym_5d(self):
        r = presets.match_longname_to_use_class("Gymnasium")
        assert r["use_class"] == "5d"
        assert r["factor"] == 3

    def test_warehouse_6b(self):
        r = presets.match_longname_to_use_class("Storage Room")
        assert r["use_class"] == "6b"
        assert r["factor"] == 30

    def test_parking_7(self):
        r = presets.match_longname_to_use_class("Car Park Level 1")
        assert r["use_class"] == "7"

    def test_lobby_ambiguous(self):
        """单独 'Lobby' 在 ambiguous 列表 → 不映射"""
        r = presets.match_longname_to_use_class("Lobby")
        assert r["source"] == "ambiguous"
        assert r["use_class"] is None

    def test_empty_longname(self):
        r = presets.match_longname_to_use_class(None)
        assert r["source"] == "unknown"
        assert r["use_class"] is None
        r2 = presets.match_longname_to_use_class("")
        assert r2["source"] == "unknown"

    def test_unknown_random(self):
        r = presets.match_longname_to_use_class("XYZ Random Space")
        assert r["source"] == "unknown"
        assert r["use_class"] is None

    def test_bank_priority_over_dining(self):
        """banking 在 mapping 列表前面, 'Banking Hall' 应优先匹配 4b banking(0.5) 而非 hall 歧义"""
        r = presets.match_longname_to_use_class("Banking Hall")
        assert r["use_class"] == "4b"
        assert r["factor"] == 0.5


# ============ Capacity 计算 ============

class TestComputeCapacity:
    def test_area_per_person(self):
        cap, src = presets.compute_capacity(18.5, 9, "area_per_person_m2")
        assert cap == 3  # ceil(18.5/9) = ceil(2.055) = 3
        assert "area" in src

    def test_office_9m2_per_person(self):
        cap, _ = presets.compute_capacity(90.0, 9, "area_per_person_m2")
        assert cap == 10

    def test_banking_half_m2(self):
        cap, _ = presets.compute_capacity(100.0, 0.5, "area_per_person_m2")
        assert cap == 200

    def test_bedspaces_requires_count(self):
        cap, src = presets.compute_capacity(50.0, None, "bedspaces")
        assert cap is None
        assert "bedspaces" in src

    def test_missing_area(self):
        cap, _ = presets.compute_capacity(None, 9, "area_per_person_m2")
        assert cap is None

    def test_round_up(self):
        """ceil(10.1 / 9) = 2"""
        cap, _ = presets.compute_capacity(10.1, 9, "area_per_person_m2")
        assert cap == 2


# ============ 默认 factor 查询 ============

class TestGetDefaultFactor:
    def test_4a_office(self):
        r = presets.get_default_factor_for_use_class("4a")
        assert r["factor"] == 9
        assert r["factor_type"] == "area_per_person_m2"

    def test_2_hotel_bedspaces(self):
        """2 (hotel) 第一个是 bedspaces, 没有 area_per_person_m2, 返回第一个"""
        r = presets.get_default_factor_for_use_class("2")
        assert r is not None
        assert r["factor_type"] == "bedspaces"

    def test_unknown_class(self):
        assert presets.get_default_factor_for_use_class("XYZ") is None


if __name__ == "__main__":
    # 允许 python tests/test_presets.py 直接跑(无 pytest)
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
