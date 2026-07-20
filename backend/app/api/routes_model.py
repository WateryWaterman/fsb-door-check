"""路由 /model — 上传 IFC + 摘要 + normalize(fallback for viewer)。

对应 docs/SSD.md §1 上传初始化。
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import ifcopenshell
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response

from ..core.pipeline import analyze_ifc
from ..session import create_session, delete_session, get_session

router = APIRouter(prefix="/model", tags=["model"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
NORMALIZED_DIR = UPLOAD_DIR / "normalized"
NORMALIZED_DIR.mkdir(exist_ok=True)


def _cleanup_normalized_dir() -> None:
    """启动时清空 normalized/ 目录(重启即清,避免累积)。"""
    if not NORMALIZED_DIR.is_dir():
        return
    for p in NORMALIZED_DIR.glob("*.ifc"):
        try:
            p.unlink()
        except OSError:
            pass


_cleanup_normalized_dir()


@router.post("/upload")
async def upload_model(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".ifc"):
        raise HTTPException(status_code=400, detail={
            "error": "invalid_file", "detail": "only .ifc files accepted",
            "hint": "see samples/ directory for test files",
        })
    dest = UPLOAD_DIR / Path(file.filename).name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        result = analyze_ifc(dest)
    except Exception as e:
        raise HTTPException(status_code=422, detail={
            "error": "ifc_parse_failed", "detail": str(e),
            "hint": "check IFC schema version or try another sample",
        })
    session = create_session(str(dest), file.filename, result)
    return {
        "session_id": session.id,
        "ifc_schema": result["schema"],
        "counts": result["counts"],
        "storeys": result["storeys"],
        "spaces": result["spaces"],
        "doors": result["doors"],
        "summary": result["summary"],
        "warnings": result.get("warnings", []),
    }


@router.get("/{sid}/summary")
def get_summary(sid: str):
    s = get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail={
            "error": "session_not_found", "detail": sid,
            "hint": "POST /model/upload to create a session",
        })
    r = s.result
    return {
        "session_id": s.id,
        "filename": s.filename,
        "ifc_schema": s.schema,
        "counts": {
            "spaces": len(r.get("spaces", [])),
            "doors": len(r.get("doors", [])),
            "storeys": len(r.get("storeys", [])),
        },
        "summary": r["summary"],
        "overrides": s.overrides,
        "_custom_threshold_table": s.custom_threshold_table,
    }


@router.post("/normalize")
async def normalize_ifc(file: UploadFile = File(...)):
    """ifcopenshell 重写 IFC,规范化 STEP 序列化。

    用途:前端 web-ifc 解析失败时(xeokit WebIFCLoaderPlugin 的 fallback),
    POST 原文件到此端点,ifcopenshell 读入并重新写出,通常能绕开 web-ifc 的解析 bug。
    返回 normalize 后的 ArrayBuffer(application/octet-stream)。
    """
    if not file.filename or not file.filename.lower().endswith(".ifc"):
        raise HTTPException(status_code=400, detail={
            "error": "invalid_file", "detail": "only .ifc files accepted"})
    raw = await file.read()
    tmp_in = UPLOAD_DIR / f"_norm_in_{uuid.uuid4().hex}.ifc"
    tmp_out = NORMALIZED_DIR / f"{uuid.uuid4().hex}.ifc"
    try:
        tmp_in.write_bytes(raw)
        try:
            f = ifcopenshell.open(tmp_in)
            f.write(str(tmp_out))
            f = None  # 释放
        except Exception as e:
            raise HTTPException(status_code=422, detail={
                "error": "normalize_failed", "detail": str(e),
                "hint": "ifcopenshell could not parse the file — likely corrupt or unsupported schema",
            })
        data = tmp_out.read_bytes()
        return Response(content=data, media_type="application/octet-stream")
    finally:
        try: tmp_in.unlink(missing_ok=True)
        except OSError: pass
        try: tmp_out.unlink(missing_ok=True)
        except OSError: pass


@router.delete("/{sid}")
def delete_model_session(sid: str):
    """关闭网页时清理 session + 关联的 normalized 文件。"""
    s = get_session(sid)
    if not s:
        return {"ok": True, "note": "session not found, nothing to clean"}
    delete_session(sid)
    return {"ok": True, "session_id": sid}
