"""API 集成测试 — 用 FastAPI TestClient 测所有端点。

跑法:
    cd fsb-door-check/backend
    python -m pytest tests/test_api.py -v -s
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "samples"
CLINIC = SAMPLES_DIR / "Clinic_Architectural_IFC2x3.ifc"
DUPLEX = SAMPLES_DIR / "Duplex_Apartment_IFC2x3.ifc"


# ============ 基础端点 ============

class TestBasic:
    def test_health(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_root(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        # /api returns the endpoint listing (JSON)
        r2 = client.get("/api")
        assert r2.status_code == 200
        assert "endpoints" in r2.json()

    def test_presets(self):
        r = client.get("/presets")
        assert r.status_code == 200
        data = r.json()
        assert "default" in data
        assert data["default"]["preset_id"] == "hk_fsb_2011_b2_default"
        assert "table_b2_thresholds" in data["default"]
        assert "longname_map" in data
        assert len(data["default"]["table_b2_thresholds"]) == 15  # 14 档 + >3000


# ============ 上传 + 摘要 ============

class TestUpload:
    @pytest.fixture(scope="class")
    def clinic_session(self):
        with open(CLINIC, "rb") as f:
            r = client.post(
                "/model/upload",
                files={"file": ("Clinic_Architectural_IFC2x3.ifc", f, "application/octet-stream")},
            )
        assert r.status_code == 200, f"upload failed: {r.text}"
        return r.json()

    def test_upload_clinic(self, clinic_session):
        data = clinic_session
        assert data["ifc_schema"].startswith("IFC2X3")
        assert data["counts"]["doors"] == 254
        assert data["counts"]["spaces"] == 269
        assert data["session_id"]
        assert len(data["doors"]) == 254
        assert data["summary"]["total_doors"] == 254

    def test_get_summary(self, clinic_session):
        sid = clinic_session["session_id"]
        r = client.get(f"/model/{sid}/summary")
        assert r.status_code == 200
        assert r.json()["session_id"] == sid
        assert r.json()["counts"]["doors"] == 254

    def test_upload_invalid_file(self):
        r = client.post("/model/upload", files={"file": ("test.txt", b"not ifc", "text/plain")})
        assert r.status_code == 400

    def test_session_not_found(self):
        r = client.get("/model/nonexistent-sid/summary")
        assert r.status_code == 404


# ============ 门详情 + 检查 ============

class TestDoorsAndCheck:
    @pytest.fixture(scope="class")
    def clinic_session(self):
        with open(CLINIC, "rb") as f:
            r = client.post(
                "/model/upload",
                files={"file": ("Clinic_Architectural_IFC2x3.ifc", f, "application/octet-stream")},
            )
        return r.json()

    def test_get_door(self, clinic_session):
        sid = clinic_session["session_id"]
        first_door = clinic_session["doors"][0]
        gid = first_door["global_id"]
        r = client.get(f"/doors/{gid}", params={"session": sid})
        assert r.status_code == 200
        data = r.json()
        assert data["door"]["global_id"] == gid
        assert "check_result" in data["door"]

    def test_get_door_not_found(self, clinic_session):
        sid = clinic_session["session_id"]
        r = client.get("/doors/FAKE_GLOBAL_ID", params={"session": sid})
        assert r.status_code == 404

    def test_run_check(self, clinic_session):
        sid = clinic_session["session_id"]
        r = client.post(f"/check/{sid}")
        assert r.status_code == 200
        data = r.json()
        assert data["session_id"] == sid
        assert len(data["results"]) == 254
        assert "checked_at" in data
        statuses = {x["status"] for x in data["results"]}
        assert statuses <= {"pass", "fail", "non_passage"}


# ============ 覆盖 ============

class TestOverride:
    @pytest.fixture(scope="class")
    def clinic_session(self):
        with open(CLINIC, "rb") as f:
            r = client.post(
                "/model/upload",
                files={"file": ("Clinic_Architectural_IFC2x3.ifc", f, "application/octet-stream")},
            )
        return r.json()

    def test_override_fire_exit(self, clinic_session):
        sid = clinic_session["session_id"]
        first_door = clinic_session["doors"][0]
        gid = first_door["global_id"]
        r = client.post(f"/override/{sid}", json={
            "type": "fire_exit",
            "global_id": gid,
            "value": True,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["applied"]["type"] == "fire_exit"
        assert len(data["affected_results"]) >= 1

        r2 = client.get(f"/doors/{gid}", params={"session": sid})
        assert r2.json()["door"]["is_fire_exit"] is True
        assert r2.json()["door"]["fire_exit_source"] == "user_override"

    def test_override_occupancy(self, clinic_session):
        sid = clinic_session["session_id"]
        first_space = clinic_session["spaces"][0]
        gid = first_space["global_id"]
        r = client.post(f"/override/{sid}", json={
            "type": "occupancy",
            "global_id": gid,
            "value": 500,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["applied"]["value"] == 500

    def test_override_threshold(self, clinic_session):
        sid = clinic_session["session_id"]
        r = client.post(f"/override/{sid}", json={
            "type": "threshold",
            "global_id": "hk_fsb_2011_b2_default",
            "value": {
                "capacity_min": 4,
                "capacity_max": 30,
                "min_width_per_door_mm": 2000,
            },
        })
        assert r.status_code == 200
        data = r.json()
        assert len(data["affected_results"]) > 0
        for cr in data["affected_results"]:
            if cr["occupant_capacity"] is not None and 4 <= cr["occupant_capacity"] <= 30:
                assert cr["status"] in ("pass", "fail")
                assert cr["threshold_mm"] == 2000
                assert cr["has_threshold_override"] is True

    def test_override_invalid_type(self, clinic_session):
        sid = clinic_session["session_id"]
        r = client.post(f"/override/{sid}", json={
            "type": "invalid_type",
            "global_id": "x",
            "value": True,
        })
        assert r.status_code == 400


# ============ 端到端: 上传 → 检查 → 覆盖 → 重算 ============

class TestEndToEnd:
    def test_duplex_full_flow(self):
        with open(DUPLEX, "rb") as f:
            r = client.post(
                "/model/upload",
                files={"file": ("Duplex_Apartment_IFC2x3.ifc", f, "application/octet-stream")},
            )
        assert r.status_code == 200
        data = r.json()
        sid = data["session_id"]
        assert data["counts"]["doors"] >= 10

        r2 = client.post(f"/check/{sid}")
        assert r2.status_code == 200
        assert len(r2.json()["results"]) == data["counts"]["doors"]

        if data["doors"]:
            gid = data["doors"][0]["global_id"]
            r3 = client.post(f"/override/{sid}", json={
                "type": "fire_exit",
                "global_id": gid,
                "value": True,
            })
            assert r3.status_code == 200

            r4 = client.get(f"/doors/{gid}", params={"session": sid})
            assert r4.json()["door"]["is_fire_exit"] is True

        print(f"\n  Duplex end-to-end OK: {data['counts']} summary={data['summary']['by_status']}")


class TestExport:
    """导出端点 MVP 返回 501(设计文档先行)。"""

    def test_export_bcf_returns_501(self):
        with open(DUPLEX, "rb") as f:
            r = client.post(
                "/model/upload",
                files={"file": ("Duplex_Apartment_IFC2x3.ifc", f, "application/octet-stream")},
            )
        sid = r.json()["session_id"]
        r2 = client.post(f"/export/{sid}", params={"format": "bcf"})
        assert r2.status_code == 501
        detail = r2.json()["detail"]
        assert detail["error"] == "export_not_implemented"
        assert detail["requested_format"] == "bcf"
        assert detail["design_doc"] == "docs/EXPORT_DESIGN.md"
        assert "planned_formats" in detail

    def test_export_html_and_json_return_501(self):
        with open(DUPLEX, "rb") as f:
            r = client.post(
                "/model/upload",
                files={"file": ("Duplex_Apartment_IFC2x3.ifc", f, "application/octet-stream")},
            )
        sid = r.json()["session_id"]
        for fmt in ("html", "json"):
            r2 = client.post(f"/export/{sid}", params={"format": fmt})
            assert r2.status_code == 501, f"{fmt} should return 501"
            assert r2.json()["detail"]["requested_format"] == fmt

    def test_export_invalid_format_returns_400(self):
        with open(DUPLEX, "rb") as f:
            r = client.post(
                "/model/upload",
                files={"file": ("Duplex_Apartment_IFC2x3.ifc", f, "application/octet-stream")},
            )
        sid = r.json()["session_id"]
        r2 = client.post(f"/export/{sid}", params={"format": "pdf"})
        assert r2.status_code == 400
        assert r2.json()["detail"]["error"] == "invalid_format"

    def test_export_unknown_session_returns_404(self):
        r = client.post("/export/does-not-exist", params={"format": "bcf"})
        assert r.status_code == 404


class TestNormalizeAndCleanup:
    """POST /model/normalize(ifcopenshell 重写)+ DELETE /model/{sid}。"""

    def test_normalize_returns_ifc_bytes(self):
        with open(DUPLEX, "rb") as f:
            r = client.post(
                "/model/normalize",
                files={"file": ("Duplex_Apartment_IFC2x3.ifc", f, "application/octet-stream")},
            )
        assert r.status_code == 200
        data = r.content
        assert data.startswith(b"ISO-10303-21")
        assert b"FILE_SCHEMA" in data
        assert b"IFC2X3" in data
        assert len(data) > 1_000_000
        # content-type 应是 octet-stream(非 JSON)
        ct = r.headers.get("content-type", "")
        assert "octet-stream" in ct or "text/plain" in ct

    def test_normalize_rejects_non_ifc(self):
        r = client.post(
            "/model/normalize",
            files={"file": ("test.txt", b"hello", "text/plain")},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "invalid_file"

    def test_delete_session_cleans_up(self):
        with open(DUPLEX, "rb") as f:
            r = client.post(
                "/model/upload",
                files={"file": ("Duplex_Apartment_IFC2x3.ifc", f, "application/octet-stream")},
            )
        sid = r.json()["session_id"]
        r2 = client.delete(f"/model/{sid}")
        assert r2.status_code == 200
        assert r2.json()["ok"] is True
        # 删除后再访问应 404
        r3 = client.get(f"/model/{sid}/summary")
        assert r3.status_code == 404

    def test_delete_unknown_session_returns_ok(self):
        r = client.delete("/model/does-not-exist")
        assert r.status_code == 200
        assert r.json()["ok"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
