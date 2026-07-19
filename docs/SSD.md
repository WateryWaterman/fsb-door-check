# 系统序列图(SSD)— FSB 门净宽检查 MVP

> 本文用 Mermaid 序列图描述前后端核心交互。所有关联通过 **IFC GlobalId**(`global_id`)。
> 配套:`PLAN.md`(架构与统一 ID 规范)、`EXPORT_DESIGN.md`(导出流程)。

---

## 0. 角色与术语

| 角色 | 实现 | 职责 |
|---|---|---|
| 用户(U) | 浏览器 | 点选、编辑、标记 |
| 前端(FE) | Vue 3 + xeokit | 3D 渲染、基础信息获取、本地状态、用户输入采集 |
| 后端(BE) | FastAPI + ifcopenshell | IFC 深度解析、规则计算、会话态 |
| ID | IFC GlobalId | 前后端关联纽带 |

---

## 1. 主流程:上传 IFC 并初始化

```mermaid
sequenceDiagram
    autonumber
    participant U as 用户
    participant FE as 前端(xeokit)
    participant BE as 后端(FastAPI)

    U->>FE: 选择 IFC 文件
    FE->>FE: xeokit 加载几何(web-ifc wasm,本地)
    FE->>BE: POST /model/upload (file)
    BE->>BE: ifcopenshell 解析
    BE->>BE: 提取 storeys / spaces / doors 摘要(含 global_id)
    BE->>BE: 初始化 session_id + 默认 preset
    BE-->>FE: 200 {session_id, storeys[], spaces[], doors[]}
    FE->>FE: 渲染 3D + 楼层树 + 默认所有门半透明
    FE->>U: 显示主界面
```

**关键点**
- 前端用 xeokit 自带 web-ifc 解析几何,**不依赖后端**,加载即可点选
- 后端返回的 `doors[]` 每条带 `global_id`,前端以此建立 global_id → xeokit object 句柄映射
- 默认所有门半透明,等待"标记防火门"或"运行检查"后着色

---

## 2. 点选门 → 查看基础信息

```mermaid
sequenceDiagram
    autonumber
    participant U
    participant FE
    participant BE

    U->>FE: 点选 3D 中的门
    FE->>FE: xeokit 拾取 → 拿到 global_id
    FE->>FE: 高亮门 + 显示侧栏 DoorInspector
    FE->>BE: GET /doors/{global_id}?session={sid}
    BE->>BE: 查 ifcopenshell 模型 + 关联空间 + 容量
    BE-->>FE: 200 {global_id, 基础信息, 关联空间, capacity, 当前检查结果}
    FE->>U: 渲染门详情卡片
```

**关键点**
- 前端拾取后**立即**用本地缓存的基础信息(OverallWidth、Name)渲染,后端详情异步补全
- 所有调用都以 `global_id` 为主键,前端永不传数组下标

---

## 3. 触发全局检查

```mermaid
sequenceDiagram
    autonumber
    participant U
    participant FE
    participant BE

    U->>FE: 点击"运行检查"按钮
    FE->>BE: POST /check/{session_id}
    BE->>BE: 跑规则引擎(遍历所有门)
    BE->>BE: 每门:capacity → Table B2 查阈值 → 四状态
    BE-->>FE: 200 {results: [{global_id, status, threshold_mm, measured_mm, width_source, needs_human_review, preset_id, rule_source}]}
    FE->>FE: 按状态着色:pass=绿 / fail=红 / unknown=黄 / overridden=蓝
    FE->>FE: fail/unknown 门不再半透明(高亮),pass 门保持半透明
    FE->>U: 显示结果列表(按状态排序)+ 统计摘要
```

**关键点**
- 检查在后端跑,前端只渲染
- 结果列表的每条记录以 `global_id` 关联 3D 场景中的门

---

## 4. 用户覆盖阈值

```mermaid
sequenceDiagram
    autonumber
    participant U
    participant FE
    participant BE

    U->>FE: 在 PresetEditor 编辑 Table B2 某档阈值
    FE->>FE: 本地暂存(标"未保存")
    U->>FE: 点击"应用并重算"
    FE->>BE: PUT /presets/{session_id} {preset_id, override: {档位: 新阈值}}
    BE->>BE: 更新 session preset + 标记 overridden
    BE->>BE: 重算受影响门(capacity 落在该档的)
    BE-->>FE: 200 {更新后的结果列表, overridden_count}
    FE->>FE: 刷新着色 + 结果列表(overridden 标蓝)
    FE->>U: 显示新结果
```

**关键点**
- 阈值覆盖只重算落在该档位的门,不全量重算(性能)
- overridden 状态独立于 pass/fail,UI 用蓝色区分"用户改过阈值后的结果"

---

## 5. 手动标记/取消防火门

```mermaid
sequenceDiagram
    autonumber
    participant U
    participant FE
    participant BE

    U->>FE: 选中门(点选或 ID 输入)
    U->>FE: 点"标记为防火门"
    FE->>BE: POST /override/{session_id} {type: "fire_exit", global_id, value: true}
    BE->>BE: 更新门 fire_exit 标记(用户覆盖优先于推断)
    BE->>BE: 重算该门(纳入检查范围)
    BE-->>FE: 200 {更新后的该门结果}
    FE->>FE: 门高亮(不再半透明)+ 着色
    FE->>U: 显示新结果
```

**关键点**
- 因 `Pset_DoorCommon.FireExit` 实测 0%,**所有门默认可选取**,用户手动标记哪些是防火门
- 用户标记优先级 > 后端推断(`inferred_fire_exit`)
- 取消标记走同样端点,value=false

---

## 6. 用户覆盖房间用途 / 人数

```mermaid
sequenceDiagram
    autonumber
    participant U
    participant FE
    participant BE

    U->>FE: 选中空间(或选中门→关联空间)
    U->>FE: 在 DoorInspector 改 Use Class / 直接输入人数
    FE->>BE: POST /override/{session_id} {type: "space_use"|"occupancy", global_id, value}
    BE->>BE: 更新空间映射 + 重算 capacity + 重算该空间所有门
    BE-->>FE: 200 {更新后的该空间所有门结果}
    FE->>U: 刷新结果
```

**关键点**
- 房间用途覆盖影响 capacity → 影响档位 → 影响阈值 → 影响结果,链式重算
- 直接输入人数跳过 factor 计算,标 `capacity_source="user_input"`

---

## 7. 快速定位

```mermaid
sequenceDiagram
    autonumber
    participant U
    participant FE

    U->>FE: 在结果列表点某 fail 门(或按快捷键)
    FE->>FE: xeokit 视角飞行到门(global_id)
    FE->>FE: 隔离所在楼层 + 高亮门 + X-ray 其它
    FE->>U: 3D 视图聚焦该门
```

**关键点**
- 纯前端操作,无需后端往返
- 快捷键(如 `F` 跳到下一个 fail)在 CheckResultList 组件内绑定

---

## 8. 导出(暂不实现)

```mermaid
sequenceDiagram
    autonumber
    participant U
    participant FE
    participant BE

    U->>FE: 点"导出"按钮
    FE->>BE: GET /export/{session_id}?format=bcf
    BE-->>FE: 501 Not Implemented + Link: docs/EXPORT_DESIGN.md
    FE->>U: 显示"导出功能设计中,设计文档:..."
```

**MVP 阶段**:端点返回 501 + 文档链接,演示视频口述设计思路。

---

## 9. 统一 ID 流转图

```mermaid
flowchart LR
    IFC[(IFC 文件)] -->|web-ifc wasm| FE[前端 xeokit 场景]
    IFC -->|ifcopenshell| BE[后端 模型]
    BE -->|global_id + 结果| REST[REST JSON]
    FE -->|global_id 点选/覆盖| REST
    REST -->|global_id 关联| Result[检查结果]
    Result -->|global_id 着色/定位| FE
```

**核心**:IFC 文件被两端各自解析一次,但通过 global_id 始终指向同一实体。前端不持有"后端模型副本",只持有 global_id → 视觉句柄的映射。

---

## 10. 错误与降级流程

### 10.1 后端解析失败
```mermaid
sequenceDiagram
    participant FE
    participant BE
    FE->>BE: POST /model/upload
    BE-->>FE: 422 {error: "ifc_parse_failed", detail}
    FE->>FE: 显示错误提示 + 建议(检查 IFC 版本/用其他样本)
```

### 10.2 前端拾取的门后端找不到(罕见,IFC4 几何兜底场景)
```mermaid
sequenceDiagram
    participant FE
    participant BE
    FE->>BE: GET /doors/{global_id}
    BE-->>FE: 404 {error: "door_not_in_model"}
    FE->>FE: 仍显示前端本地基础信息 + 标"后端无此门关联"
```

### 10.3 capacity 无法推算
后端返回 `status: "unknown"`, `reason: "cannot_derive_occupant_capacity"`,前端用黄色着色 + 提示用户手工输入人数。

---

## 11. 端点清单(对应 SSD)

| 方法 | 路径 | 用途 | 对应序列图 |
|---|---|---|---|
| POST | `/model/upload` | 上传 IFC,初始化 session | §1 |
| GET | `/model/{sid}/summary` | 楼层/空间/门摘要 | §1 |
| GET | `/doors/{gid}` | 单门详情 | §2 |
| POST | `/check/{sid}` | 跑全量检查 | §3 |
| PUT | `/presets/{sid}` | 覆盖阈值 | §4 |
| POST | `/override/{sid}` | 标记防火门 / 改用途 / 改人数 | §5 §6 |
| GET | `/export/{sid}` | 导出(暂 501) | §8 |
| GET | `/presets` | 默认预设(前端首屏展示) | §1 |
