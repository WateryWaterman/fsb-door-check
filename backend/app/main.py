"""FastAPI 入口 — 注册路由 + CORS + 健康检查。

启动:
    cd fsb-door-check/backend
    uvicorn app.main:app --reload --port 8000
Swagger:
    http://localhost:8000/docs
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import routes_check, routes_model, routes_override, routes_presets

app = FastAPI(
    title="FSB Door Check API",
    description="Hong Kong FSB 2011 (2024) Part B — Door Clear Width Check + Occupant Capacity",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "null"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_model.router)
app.include_router(routes_check.router)
app.include_router(routes_override.router)
app.include_router(routes_presets.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "fsb-door-check", "version": "0.1.0"}


@app.get("/api")
def api_info():
    return {
        "service": "fsb-door-check",
        "docs": "/docs",
        "endpoints": [
            "POST /model/upload",
            "GET /model/{sid}/summary",
            "GET /doors/{gid}?session={sid}",
            "POST /check/{sid}",
            "POST /override/{sid}",
            "GET /presets",
            "GET /presets/{sid}",
        ],
    }


FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
