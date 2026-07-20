"""会话内存态 — session_id → 模型 + 预设 + 覆盖。

MVP 单进程内存态, 无持久化。重启丢失。
对应 docs/SSD.md §1 上传后 session_id 贯穿所有后续交互。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .core.presets import load_presets


@dataclass
class Session:
    id: str
    ifc_path: str
    filename: str
    schema: str
    result: dict[str, Any]
    overrides: list[dict[str, Any]] = field(default_factory=list)
    custom_threshold_table: Optional[list[dict[str, Any]]] = None
    door_fire_exit_overrides: dict[str, bool] = field(default_factory=dict)
    space_use_overrides: dict[str, str] = field(default_factory=dict)
    space_occupancy_overrides: dict[str, int] = field(default_factory=dict)
    storey_sprinkler_overrides: dict[str, bool] = field(default_factory=dict)
    storey_entrance_overrides: dict[str, bool] = field(default_factory=dict)
    door_checked_overrides: dict[str, bool] = field(default_factory=dict)

    def find_door(self, global_id: str) -> Optional[dict[str, Any]]:
        for d in self.result.get("doors", []):
            if d.get("global_id") == global_id:
                return d
        return None

    def find_space(self, global_id: str) -> Optional[dict[str, Any]]:
        for s in self.result.get("spaces", []):
            if s.get("global_id") == global_id:
                return s
        return None

    def find_storey(self, global_id: str) -> Optional[dict[str, Any]]:
        for s in self.result.get("storeys", []):
            if s.get("global_id") == global_id:
                return s
        return None

    def get_threshold_table(self) -> list[dict[str, Any]]:
        if self.custom_threshold_table is not None:
            return self.custom_threshold_table
        from .core.presets import load_presets
        return load_presets()["table_b2_thresholds"]

    def set_custom_threshold_table(self, bands: list[dict[str, Any]]) -> None:
        self.custom_threshold_table = bands

    def reset_custom_threshold_table(self) -> None:
        self.custom_threshold_table = None


_sessions: dict[str, Session] = {}


def create_session(ifc_path: str, filename: str, result: dict[str, Any]) -> Session:
    sid = str(uuid.uuid4())
    s = Session(
        id=sid,
        ifc_path=ifc_path,
        filename=filename,
        schema=result.get("schema", "unknown"),
        result=result,
    )
    _sessions[sid] = s
    return s


def get_session(sid: str) -> Optional[Session]:
    return _sessions.get(sid)


def list_sessions() -> list[str]:
    return list(_sessions.keys())


def delete_session(sid: str) -> bool:
    return _sessions.pop(sid, None) is not None
