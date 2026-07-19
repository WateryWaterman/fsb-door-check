"""IFC 加载 + 跨版本兼容工具。

支持 IFC2x3 / IFC4 / IFC4.3(ifcopenshell 0.8.5 验证)。
对应 docs/CONTRACT.md §6 来源标签。
对应 samples/_fill_rate_analyze.py 的 ifcopenshell 用法参考。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import ifcopenshell
from ifcopenshell.file import file as IfcFile


def load_ifc(path: str | Path) -> IfcFile:
    return ifcopenshell.open(str(path))


def get_schema(f: IfcFile) -> str:
    return f.schema


def get_storeys(f: IfcFile) -> list:
    return f.by_type("IfcBuildingStorey")


def get_spaces(f: IfcFile) -> list:
    return f.by_type("IfcSpace")


def get_doors(f: IfcFile) -> list:
    return f.by_type("IfcDoor")


def get_stairs(f: IfcFile) -> list:
    """IfcStair 用于疏散门推断(通向楼梯)。"""
    try:
        return f.by_type("IfcStair")
    except Exception:
        return []


def get_door_types(f: IfcFile) -> list:
    """IFC4: IfcDoorType, IFC2x3: IfcDoorStyle。"""
    for tname in ("IfcDoorType", "IfcDoorStyle"):
        try:
            t = f.by_type(tname)
            if t:
                return t
        except RuntimeError:
            continue
    return []


def get_psets(elem) -> dict[str, dict[str, Any]]:
    """返回元素的所有 property set: {pset_name: {prop_name: value}}。

    三条路径(参考 samples/_fill_rate_analyze.py):
    1. occurrence pset via IfcRelDefinesByProperties
    2. type pset via IsTypedBy (IFC4 IfcDoorType.HasPropertySets)
    3. IFC2x3 type pset via IfcRelDefinesByType → IfcDoorStyle.HasPropertySets
    """
    result: dict[str, dict[str, Any]] = {}
    try:
        for rel in elem.IsDefinedBy:
            if rel.is_a("IfcRelDefinesByProperties"):
                pds = rel.RelatingPropertyDefinition
                if pds.is_a("IfcPropertySet"):
                    ps: dict[str, Any] = {}
                    for p in pds.HasProperties:
                        try:
                            nv = p.NominalValue
                            ps[p.Name] = nv.wrappedValue if nv is not None else None
                        except Exception:
                            ps[p.Name] = None
                    result[pds.Name] = ps
    except Exception:
        pass

    type_rels: list = []
    try:
        type_rels.extend(list(elem.IsTypedBy))
    except Exception:
        pass
    try:
        for rel in elem.IsDefinedBy:
            if rel.is_a("IfcRelDefinesByType"):
                type_rels.append(rel)
    except Exception:
        pass

    for rel in type_rels:
        try:
            t = rel.RelatingType
            if t is None:
                continue
            type_psets = getattr(t, "HasPropertySets", None)
            if type_psets:
                for pds in type_psets:
                    if pds.is_a("IfcPropertySet"):
                        ps: dict[str, Any] = {}
                        for p in pds.HasProperties:
                            try:
                                nv = p.NominalValue
                                ps[p.Name] = nv.wrappedValue if nv is not None else None
                            except Exception:
                                ps[p.Name] = None
                        if pds.Name not in result:
                            result[pds.Name] = ps
        except Exception:
            continue
    return result


def get_pset_prop(psets: dict[str, dict[str, Any]], pset_name: str,
                  prop_name: str) -> Any:
    """返回某 pset 的某属性值,未找到返回 None。"""
    ps = psets.get(pset_name) or psets.get(pset_name.upper())
    if not ps:
        return None
    v = ps.get(prop_name)
    if v is None:
        return None
    try:
        if hasattr(v, "wrappedValue"):
            return v.wrappedValue
    except Exception:
        pass
    return v


def get_element_quantities(elem) -> list:
    """返回元素关联的所有 IfcElementQuantity(含 Quantities 列表)。"""
    result: list = []
    try:
        for rel in elem.IsDefinedBy:
            if rel.is_a("IfcRelDefinesByProperties"):
                pds = rel.RelatingPropertyDefinition
                if pds.is_a("IfcElementQuantity"):
                    result.append(pds)
    except Exception:
        pass
    return result


def get_storey_of_element(elem) -> Optional[str]:
    """通过 IfcRelContainedInSpatialStructure 找元素所在 IfcBuildingStorey 的 GlobalId。"""
    try:
        for rel in elem.ContainedInStructure:
            struct = rel.RelatingStructure
            if struct.is_a("IfcBuildingStorey"):
                return struct.GlobalId
    except Exception:
        pass
    return None
