# 前后端 JSON 契约 + 高亮映射规则

> **目的**:前后端 agent 字段名严格对齐,前端**禁止自行发明字段名**。所有字段以本文为准。
> 配套:`PLAN.md`(架构)、`SSD.md`(序列图)。Pydantic schema(`backend/app/models/`)与本文件保持一致。

---

## 1. 字段命名原则

1. **主键统一 `global_id`**:所有实体(门/空间/楼层)用 IFC GlobalId(22 字符 base64)关联,前端永不传数组下标或临时 ID
2. **字段名 snake_case**:前后端一致,前端 JS 直接用,后端 Pydantic 用 `alias` 兼容
3. **来源标签必填**:凡推算/估算的字段,必须带 `*_source` 字段(枚举值见 §6),不允许裸值
4. **复核标记必填**:凡非直接可信的字段,必须带 `needs_human_review: boolean`
5. **单位后缀**:长度 `_mm`,面积 `_m2`,人数无后缀(整数)
6. **状态枚举**:严格遵守 §5 的 4 个值,前端不高亮枚举外的值

---

## 2. 实体 schema

### 2.1 Storey(楼层)
```typescript
interface Storey {
  global_id: string;          // IFC GlobalId
  name: string;               // 如 "Level 1", 取 IfcBuildingStorey.Name
  long_name: string | null;   // 取 LongName, 可空
  elevation_m: number | null; // 取 Elevation, 单位 m
  storey_index: number;       // 按 elevation 排序后的序号, 0=最低
  door_count: number;         // 该楼层门数(后端统计)
  space_count: number;        // 该楼层空间数
  // 用户覆盖(可选, 后端 session 态)
  is_entrance_level?: boolean | null;       // UI 手工标, 来自 Pset_BuildingStoreyCommon.EntranceLevel (实测 0%)
  has_sprinkler?: boolean | null;           // UI 手工标, 来自 Pset_BuildingStoreyCommon.SprinklerProtection (实测 0%)
}
```

### 2.2 Space(空间)
```typescript
interface Space {
  global_id: string;
  name: string;               // IfcSpace.Name, 如 "1F-CONSULT-101"
  long_name: string | null;   // IfcSpace.LongName, 如 "Consultation Room" (实测 100% 填充)
  storey_global_id: string;   // 所属楼层
  area_m2: number | null;     // 房间面积
  area_source: AreaSource;    // 面积来源标签, 见 §6.2
  use_class: string | null;   // 香港 Table A1 Use Class, 如 "4a" / "1b" / null
  use_class_source: UseClassSource;  // 用途来源标签, 见 §6.3
  use_class_confidence: "high" | "medium" | "low" | "manual";  // 置信度
  occupant_capacity: number | null;   // 推算人数, 整数, null=无法推算
  capacity_source: CapacitySource;   // 人数来源标签, 见 §6.4
  door_global_ids: string[];  // 该空间关联的门 (通过 IfcRelSpaceBoundary)
}
```

### 2.3 Door(门)
```typescript
interface Door {
  global_id: string;
  name: string;               // IfcDoor.Name
  long_name: string | null;
  overall_width_mm: number | null;   // IfcDoor.OverallWidth (实测 100%)
  overall_height_mm: number | null;
  measured_width_mm: number | null;  // 用于检查的宽度 (优先 clear, 退化 overall)
  width_source: WidthSource;         // 宽度来源标签, 见 §6.1
  needs_human_review: boolean;       // true 当 width_source != "clear_width"
  storey_global_id: string | null;
  space_global_id: string | null;    // 主关联空间 (IfcRelSpaceBoundary)
  space_global_id_other: string | null;  // 跨两空间时的另一侧
  is_fire_exit: boolean;             // 是否疏散门 (推断或用户标)
  fire_exit_source: FireExitSource;  // 疏散门来源标签, 见 §6.5
  is_double_leaf: boolean | null;    // 是否双扇 (IfcDoorPanelProperties, MVP 可不实现)
  // 检查结果(检查后填充, 上传时为 null)
  check_result: CheckResult | null;
}
```

---

## 3. 检查结果 schema

```typescript
interface CheckResult {
  door_global_id: string;          // 关联键
  preset_id: string;               // 如 "hk_fsb_2011_b2_default"
  rule_source: string;             // 如 "HK FSB 2011 (2024) Table B2 + Clause B7.1"
  rule_clause: string;             // 如 "B7.1" / "B13.4" / "B30.3"
  status: CheckStatus;             // 见 §5
  threshold_mm: number | null;     // 适用阈值 (Table B2 档位值 或 B13.4 的 750)
  threshold_source: string;        // 如 "Table B2 row[4-30]" / "Clause B13.4 absolute"
  measured_mm: number | null;      // 实测宽度 (= door.measured_width_mm)
  deficit_mm: number | null;       // 仅 fail 时: threshold - measured
  occupant_capacity: number | null;
  capacity_source: CapacitySource;
  width_source: WidthSource;
  needs_human_review: boolean;
  reason: string;                  // 人类可读的原因, 如 "OverallWidth 900mm < threshold 1050mm"
  overridden: boolean;             // 是否因用户覆盖阈值/用途/人数而重算
  human_review_notes: string[];    // 待人工复核项列表
}

type CheckStatus = "pass" | "fail" | "unknown" | "overridden";
```

**status 判定规则**(后端 rule_engine 严格遵守):
| 条件 | status | 说明 |
|---|---|---|
| `capacity == null` | `unknown` | 无法推算人数,Table B2 不适用 |
| `capacity <= 3` 且 `measured >= 750` | `pass` | Clause B13.4 绝对下限满足 |
| `capacity <= 3` 且 `measured < 750` | `fail` | Clause B13.4 触发 |
| `capacity <= 3` 且 `measured == null` | `unknown` | 宽度缺失 |
| `capacity > 3` 且 `measured == null` | `unknown` | 宽度缺失 |
| `capacity > 3` 且 `measured >= threshold` | `pass` | Table B2 满足 |
| `capacity > 3` 且 `measured < threshold` | `fail` | Table B2 不满足 |
| 用户覆盖阈值后重算 | `overridden` | 独立标记,叠加在 pass/fail 之上(见 §5) |

---

## 4. 覆盖请求 schema(前端 → 后端)

```typescript
// POST /override/{session_id}  body
interface OverrideRequest {
  type: OverrideType;
  global_id: string;        // 被覆盖实体的 global_id (门/空间/楼层)
  value: OverrideValue;
  note?: string;
}

type OverrideType =
  | "fire_exit"           // 标记/取消防火门 (global_id=door, value=boolean)
  | "space_use"           // 改空间用途 (global_id=space, value=UseClass string)
  | "occupancy"           // 直接指定人数 (global_id=space, value=number)
  | "threshold"           // 覆盖某档阈值 (global_id=preset_id, value=ThresholdOverride)
  | "storey_sprinkler"    // 标楼层喷淋 (global_id=storey, value=boolean)
  | "storey_entrance";    // 标楼层是否入口层 (global_id=storey, value=boolean)

type OverrideValue = boolean | number | string | ThresholdOverride;

interface ThresholdOverride {
  capacity_min: number;       // 档位下限 (匹配 Table B2 行)
  capacity_max: number | null;
  min_width_per_door_mm: number;  // 新阈值
}

// PUT /presets/{session_id}  body (整体替换预设, 较少用)
interface PresetUpdate {
  preset_id: string;
  overrides: OverrideRequest[];
}
```

---

## 5. 高亮映射规则(前端渲染用)

前端**严格按 status 着色**,不允许自行判断颜色。

### 5.1 颜色与透明度
| status | 颜色(RGB) | 透明度 | 边框 | 说明 |
|---|---|---|---|---|
| `pass` | `#22c55e`(绿) | 0.3(半透明) | 无 | 通过,不抢视觉焦点 |
| `fail` | `#ef4444`(红) | 1.0(不透明) | 红色高亮 | 失败,最高视觉优先级 |
| `unknown` | `#eab308`(黄) | 1.0(不透明) | 黄色高亮 | 待人工复核 |
| `overridden` | `#3b82f6`(蓝) | 1.0(不透明) | 蓝色高亮 | 用户覆盖后的结果 |
| 未检查(`check_result == null`) | 默认材质 | 0.3(半透明) | 无 | 上传后未点"运行检查" |
| 非门元素 | 默认材质 | 0.5(半透明) | 无 | 让门突出 |

### 5.2 着色优先级(一个门同时满足多条件时)
1. `overridden` 优先于 `pass`/`fail`/`unknown`(因为用户改过,要让他看到自己的修改生效)
2. `fail` > `unknown` > `pass`(失败最显眼)
3. `check_result == null` 时用"未检查"色

### 5.3 交互行为映射
| 用户操作 | 前端行为 | 后端调用 |
|---|---|---|
| 点选门 | 高亮该门(恢复不透明)+ 隔离楼层 + 显示 DoorInspector | `GET /doors/{global_id}` |
| 结果列表点击 fail 门 | 相机飞行到门 + 高亮 + 隔离楼层 | 无(纯前端) |
| 按 `F` 键 | 跳到下一个 fail 门 | 无 |
| 按 `U` 键 | 跳到下一个 unknown 门 | 无 |
| 点"标记防火门" | 门改为 fire_exit 高亮 + 触发重算 | `POST /override` type=fire_exit |
| 编辑阈值并应用 | 所有受影响门重算 + 着色刷新 | `POST /override` type=threshold |

### 5.4 xeokit 实现要点
- 半透明:`viewer.objects[globalId].xrayed = true; .xrayMaterial.alpha = 0.3`
- 着色:`.colorize = [r, g, b]`(xeokit 用 0-1 浮点)
- 飞行:`viewer.cameraFlight.flyTo([globalId])`
- 隔离楼层:`viewer.scene.setVisibilityObjects(...)`

---

## 6. 来源标签枚举(严格遵守,前端用于显示来源说明)

### 6.1 WidthSource(`width_source`)
```typescript
type WidthSource =
  | "clear_width"           // 自定义 Pset 有 ClearWidth 字段 (未来兼容, MVP 不会有)
  | "overall_minus_lining"  // OverallWidth - 2*LiningThickness (LiningThickness 实测 0%, MVP 不会有)
  | "overall_estimate"      // OverallWidth 直接作代理 (MVP 主路径)
  | "geometry"              // 几何分析量得
  | "unknown";              // 无任何宽度数据
```

### 6.2 AreaSource(`area_source`)
```typescript
type AreaSource =
  | "IfcQuantityArea.NetFloorArea"   // IFC4 SampleHouse 命中
  | "IfcQuantityArea.GSA BIM Area"   // IFC2x3 Revit 命中 (NetFloorArea 同义词)
  | "IfcQuantityArea.GrossFloorArea" // 兜底
  | "Qto_SpaceBaseQuantities"        // 标准量集 (实测 0%, 留兼容)
  | "geometry_footprint"             // 几何计算
  | "unknown";
```

### 6.3 UseClassSource(`use_class_source`)
```typescript
type UseClassSource =
  | "Pset_SpaceOccupancyRequirements.OccupancyType"  // 标准 (实测 0%, 留兼容)
  | "longname_keyword"        // LongName 关键词映射 (MVP 主路径)
  | "user_override"           // UI 手工指定
  | "unknown";                // 无法识别
```

### 6.4 CapacitySource(`capacity_source`)
```typescript
type CapacitySource =
  | "OccupancyNumber"         // Pset 直接给人数 (实测 0%, 留兼容)
  | "AreaPerOccupant"         // Pset 给人均面积反算 (实测 0%, 留兼容)
  | "table_b1_factor"         // area / Table B1 factor (MVP 主路径)
  | "user_input"              // UI 直接输入人数
  | "unknown";                // 无法推算
```

### 6.5 FireExitSource(`fire_exit_source`)
```typescript
type FireExitSource =
  | "Pset_DoorCommon.FireExit"        // 标准字段 (实测 0%, 留兼容)
  | "inferred_cross_space"            // 推断: 跨两空间 (IfcRelSpaceBoundary)
  | "inferred_name_keyword"           // 推断: 名字含 exit/corridor/stair
  | "inferred_to_stair"               // 推断: 通向 IfcStair 所在空间
  | "user_override"                   // UI 手工标记
  | "not_fire_exit";                  // 确定不是 (默认)
```
> `is_fire_exit=true` 时,`fire_exit_source` 可能是上述任一非 `not_fire_exit` 值;`is_fire_exit=false` 时固定为 `not_fire_exit`。多个推断命中时,前端显示首个,后端记录全部到 `human_review_notes`。

---

## 7. API 端点响应 schema(摘要)

完整序列见 `SSD.md` §11。这里只列响应体字段。

### 7.1 POST /model/upload → 200
```typescript
{
  session_id: string;
  model: {
    filename: string;
    ifc_schema: string;        // "IFC2X3_TC1" / "IFC4" / ...
    counts: { spaces: number; doors: number; storeys: number; };
  };
  storeys: Storey[];
  spaces: Space[];
  doors: Door[];               // 含 check_result=null
  preset: PresetSnapshot;      // 默认预设快照
}
```

### 7.2 POST /check/{session_id} → 200
```typescript
{
  session_id: string;
  checked_at: string;          // ISO 8601
  results: CheckResult[];      // 每门一条
  summary: {
    total_doors: number;
    checked_doors: number;     // is_fire_exit=true 的门数
    by_status: { pass: number; fail: number; unknown: number; overridden: number; };
    needs_review_count: number;
    top_fails: CheckResult[];  // deficit_mm 降序前 5
  };
}
```

### 7.3 GET /doors/{global_id} → 200
```typescript
{
  door: Door;                  // 完整对象, 含 check_result
  related_space: Space | null; // 关联空间
  storey: Storey | null;
}
```

### 7.4 POST /override/{session_id} → 200
```typescript
{
  session_id: string;
  applied: OverrideRequest;    // 回显已应用的覆盖
  affected_results: CheckResult[];  // 受影响重算的结果(可能多条)
}
```

### 7.5 GET /presets → 200
```typescript
{
  default: PresetSnapshot;     // regulation_presets.json 的内容
  longname_map: LongnameMap;   // longname_to_a1.json 的内容 (前端展示用)
}
```

### 7.6 错误响应
```typescript
{
  error: string;               // 机器码, 如 "ifc_parse_failed"
  detail: string;              // 人类可读
  hint?: string;               // 建议动作
}
```

---

## 8. PresetSnapshot schema

```typescript
interface PresetSnapshot {
  preset_id: string;           // "hk_fsb_2011_b2_default"
  preset_version: string;      // "1.0.0"
  jurisdiction: string;        // "Hong Kong"
  code: string;                // "Code of Practice for Fire Safety in Buildings 2011 (2024 Edition)"
  scope: string;               // "Part B - Means of Escape"
  rule_source: string;
  rule_link: string;           // "taskrequest/fs_code2011.pdf#page=43"
  table_b1_occupancy_factors: Record<UseClass, AccommodationEntry[]>;
  table_b2_thresholds: TableB2Row[];
  absolute_minimums: {
    clause_b13_4: { applies_when: string; min_door_width_mm: number; min_double_leaf_panel_mm: number; note: string; };
    clause_b30_3: { applies_when: string; min_clear_width_mm: number; note: string; };
  };
  use_classes: Record<string, string>;  // UseClass -> 描述
  overrides?: OverrideRequest[];        // session 内的覆盖(默认预设无)
}
```

---

## 9. 字段一致性检查清单(联调前确认)

前端实现时,以下字段必须能从后端响应中读到(否则报 bug):
- [ ] `door.global_id` 存在且与 xeokit object id 一致
- [ ] `door.check_result.status` ∈ {pass, fail, unknown, overridden}
- [ ] `door.check_result.threshold_mm` 为数字或 null
- [ ] `door.width_source` ∈ §6.1 枚举
- [ ] `door.fire_exit_source` ∈ §6.5 枚举
- [ ] `space.use_class_source` ∈ §6.3 枚举
- [ ] `space.capacity_source` ∈ §6.4 枚举
- [ ] 结果列表的 `door_global_id` 能在 3D 场景里找到对应 object

后端实现时,以下字段必须返回(否则前端报错):
- [ ] 所有 `*_source` 字段非 null(即使值为 unknown 也要返回 `"unknown"`)
- [ ] `needs_human_review` 是 boolean 不是 0/1
- [ ] `overridden` 在用户覆盖后必须为 true
- [ ] `deficit_mm` 仅 fail 时非 null,其它状态为 null
