# MVP 初版计划 — FSB 门净宽检查 Web 微原型

> 文档定位:本文件是初版计划,供用户校对预期。不符之处调整后再进入实现。
> 配套:`SSD.md`(系统序列图)、`EXPORT_DESIGN.md`(导出设计)、根目录 `README.md`。
> 依据:`taskrequest/door_width_regulation_preset.md`、`taskrequest/ifc_field_fill_rate.md`、`taskrequest/ifc_field_deep_lookup.md`、`taskrequest/occupant_capacity_research.md`。

***

## 1. 目标与范围

### 1.1 核心目标(2 天 MVP)

可运行的 Web 微原型:上传 IFC → 自动推算 Occupant Capacity → 按香港 FSB 2011 (2024) Part B Table B2 检查门净宽 → 3D 可视化 + 结果卡片 + 人工覆盖 + 导出设计。

### 1.2 选定规则(不变)

香港 FSB 2011 (2024) Part B 的**门净宽检查 + Occupant Capacity 自动推算**。

### 1.3 MVP 范围(做)

- IFC2x3 / IFC4 跨版本解析(ifcopenshell,同一套代码)
- 房间面积提取(动态匹配 `IfcQuantityArea.Name` ∈ {`NetFloorArea`, `GSA BIM Area`, `GrossFloorArea`})
- 房间用途识别(`IfcSpace.LongName` 关键词 → Table A1 + UI 覆盖)
- Occupant Capacity 推算(`capacity = area / factor`)
- 门宽提取(`IfcDoor.OverallWidth` 作代理,标 `overall_estimate`)
- 门↔房间关联(`IfcRelSpaceBoundary` 主 + 几何 point-in-polygon 兜底)
- 疏散门推断(跨两空间 + 名字 + 通向楼梯,标 `inferred_fire_exit`)
- Table B2 区间查阈值 + 四状态(`pass`/`fail`/`unknown`/`overridden`)
- 3D 渲染:旋转、门要素选取、非防火门半透明、门标记、楼层归属
- 右侧侧栏:规范信息 + 计算标准链接 + 阈值编辑/增删改 + 选中门基础信息 + 检查结果 + 快速定位
- **所有门可通过 ID 或点选取**(因字段不足判别防火门),UI 提供"标记为防火门"
- 导出**设计文档**(暂不实现导出本身)

### 1.4 MVP 范围(不做)

- 多扇门 Clause B13.4 自动检查(降级为人工复核项)
- 楼层喷淋自动识别(UI 手工标)
- 几何 clear width 推算(OverallWidth 代理足够 MVP)
- 导出实际功能(只设计格式,见 `EXPORT_DESIGN.md`)
- 用户登录/权限/数据库持久化(单会话内存态)
- IFC4.3 特殊适配(跨版本一套代码即可)

***

## 2. 架构总览 — 双结构 + 统一 ID

### 2.1 设计原则

| 层      | 职责                            | 技术                     |
| ------ | ----------------------------- | ---------------------- |
| 前端(FE) | 轻量逻辑:基础信息获取、3D 渲染、用户输入采集、本地状态 | Vue 3 + xeokit         |
| 后端(BE) | 重逻辑:IFC 深度解析、规则计算、阈值管理        | FastAPI + ifcopenshell |
| 统一 ID  | 前后端关联纽带                       | IFC GlobalId           |

**"双结构"的含义**:前端用 web-ifc(wasm,内嵌于 xeokit)在浏览器里直接读 IFC 的**几何 + 显式属性**(OverallWidth、Name、LongName、GlobalId),用于即时渲染和点选响应;后端用 ifcopenshell 做**关系链 + Pset + 规则计算**,因为 ifcopenshell 对关系/属性集的支持比 web-ifc 完整。两端通过 GlobalId 关联同一实体。

### 2.2 前端职责清单

- 3D 渲染(xeokit):旋转、楼层树、楼层隔离、门要素拾取
- 基础信息获取:从 xeokit 场景图直接读门/空间显式属性(无需后端往返)
- 视觉编码:非防火门半透明(X-ray),标记的防火门高亮,检查 fail 红色 / pass 绿色 / unknown 黄色
- 右侧侧栏:
  - 规范信息面板(jurisdiction、code、Table B2 全表、Clause 引用链接)
  - 阈值编辑器(以默认 preset 为参考,可增删改档位/阈值)
  - 门详情面板(选中门的基础信息 + 关联空间 + 容量 + 检查结果)
  - 检查结果列表(状态排序 + 快速定位交互键)
- 手动标记防火门:所有门可通过 ID 输入框或点选取,侧栏提供"标记为防火门/取消"操作
- 用户覆盖采集:房间用途、防火门标记、阈值、人数

### 2.3 后端职责清单

- IFC 深度解析(ifcopenshell):`IfcRelSpaceBoundary`、`IfcRelFillsElement`、`IfcElementQuantity`、Pset
- 核心计算:房间面积、房间用途映射、Occupant Capacity、门↔房间关联、疏散门推断、Table B2 查询、四状态
- 阈值预设管理:默认 preset + 会话内用户覆盖
- 接收前端人工输入并触发重算
- 导出数据准备(设计阶段,端点返回 501 + 文档链接)

### 2.4 通信

- REST + JSON,自动 OpenAPI 文档(FastAPI 自带)
- IFC 文件:前端上传到后端(后端用 ifcopenshell 解析);同时前端用 xeokit 直接加载同一文件(本地 wasm 解析几何)
- 大模型优化:Duplex(14 门)用于演示视频,Clinic(254 门)用于功能验证

***

## 3. 统一 ID 规范

### 3.1 主键

- **`global_id`**:IFC GlobalId(22 字符 base64,如 `3cO6iV$Hj5M8t$3Q2n$R0V`)
- 所有实体(门、空间、楼层、墙)前后端共享此 ID,作为唯一关联键

### 3.2 派生 ID(后端生成)

- `session_id`:上传文件时后端生成的会话 ID(UUID)
- `check_id`:检查结果 ID,格式 `door:<global_id>`(一个门一条结果)
- `preset_id`:规则预设 ID,如 `hk_fsb_2011_b2_default`

### 3.3 ID 流转一致性

```
前端点选门  →  拿到 global_id  →  GET /doors/{global_id}      →  后端返回详情
后端检查结果 = [{door_global_id, status, ...}]  →  前端按 global_id 在 3D 场景里定位/着色
用户覆盖    →  POST /override {global_id, payload}  →  后端更新 + 重算受影响实体
```

- 前端**永不**用数组下标/临时 ID 关联实体,统一用 global\_id
- 后端返回的所有列表都带 global\_id 字段

***

## 4. 项目结构

```
fsb-door-check/                        # MVP monorepo(根: D:\ProgramData\ArchiTestMajun\fsb-door-check)
├── README.md                          # 项目入口、运行方式、与工作区其他目录关系
├── docs/
│   ├── PLAN.md                        # 本文件
│   ├── SSD.md                         # 系统序列图(Mermaid)
│   └── EXPORT_DESIGN.md               # 导出格式设计(暂不实现)
├── backend/                           # FastAPI + ifcopenshell
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI 入口 + CORS + 路由注册
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes_model.py        # POST /model/upload, GET /model/{sid}/summary
│   │   │   ├── routes_check.py        # POST /check/{sid}, GET /doors/{gid}
│   │   │   ├── routes_override.py     # POST /override/{sid} (用途/防火门/阈值/人数)
│   │   │   └── routes_presets.py      # GET /presets, PUT /presets/{sid}
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── ifc_loader.py          # ifcopenshell 加载 + 跨版本兼容
│   │   │   ├── space_area.py          # 房间面积(动态 Quantity Name 匹配)
│   │   │   ├── space_use.py           # 房间用途(LongName → Table A1 + UI 覆盖)
│   │   │   ├── occupant_capacity.py   # capacity = area / factor
│   │   │   ├── door_width.py          # OverallWidth 代理 + width_source
│   │   │   ├── door_space_link.py     # IfcRelSpaceBoundary + 几何兜底
│   │   │   ├── fire_exit_infer.py     # 推断疏散门(跨空间+名字+通向楼梯)
│   │   │   └── rule_engine.py         # Table B2 查询 + 四状态 + preset_id/rule_source
│   │   ├── models/                    # Pydantic schema(前后端共享字段定义)
│   │   │   ├── __init__.py
│   │   │   ├── space.py
│   │   │   ├── door.py
│   │   │   ├── check_result.py
│   │   │   └── override.py
│   │   └── session.py                 # 会话内存态(session_id → 模型+预设+覆盖)
│   ├── presets/
│   │   ├── regulation_presets.json    # Table B1(8 大 Use Class factor)+ Table B2(14 档)+ Clause B13.4/B30.3
│   │   └── longname_to_a1.json        # IfcSpace.LongName 关键词 → Table A1 Use Class 映射
│   ├── tests/
│   │   ├── test_rule_engine.py        # Table B2 档位查询、四状态判定
│   │   ├── test_space_use.py          # LongName 关键词匹配
│   │   └── test_samples.py            # 4 样本回归(Clinic/Duplex/SampleHouse/Snowdon)
│   ├── requirements.txt
│   └── README.md
├── frontend/                          # Vue 3 + Vite + xeokit
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.ts
│       ├── App.vue                    # 左右分栏布局
│       ├── viewer/                    # 左侧 3D
│       │   ├── IfcViewer.ts           # xeokit 封装(加载/拾取/高亮/X-ray/楼层树)
│       │   ├── DoorPicker.ts          # 门要素拾取 → global_id
│       │   ├── DoorHighlight.ts       # 状态着色 + 半透明
│       │   └── StoreyTree.vue         # 楼层归属树 + 隔离
│       ├── sidebar/                   # 右侧侧栏
│       │   ├── RegulationPanel.vue    # 规范信息 + 条文链接
│       │   ├── PresetEditor.vue       # 阈值编辑/增删改
│       │   ├── DoorInspector.vue      # 选中门基础信息
│       │   ├── CheckResultList.vue    # 结果列表 + 快速定位
│       │   └── FireExitToggle.vue     # 手动标记/取消防火门
│       ├── store/
│       │   └── useSessionStore.ts     # pinia: session_id + global_id 选中态 + 覆盖态
│       └── api/
│           └── client.ts              # axios 封装,所有调用带 global_id
└── prompts/                           # 提交要求:代码 + prompts
    └── development-log.md             # 开发过程 prompt 记录
```

**说明**:

- `backend/app/core/` 严格对应 `ifc_field_fill_rate.md` 第三节"修正后的流水线",每个函数一个文件,便于单测
- `backend/presets/` 是"法规预设层"的物化,JSON 格式便于前端直接读展示
- `backend/app/models/` 是"统一 ID"的 schema 物化,Pydantic 字段名前后端一致
- `frontend/src/store/` 是"统一 ID"在前端的物化,所有选中/覆盖以 global\_id 为键
- `prompts/` 是任务交付明确要求的"代码 + prompts"

***

## 5. 技术栈

### 5.1 后端

| 库            | 版本        | 用途                          |
| ------------ | --------- | --------------------------- |
| Python       | 3.13      | 运行时                         |
| FastAPI      | latest    | Web 框架 + 自动 OpenAPI         |
| ifcopenshell | 0.8.5(已装) | IFC 解析,跨 IFC2x3/IFC4/IFC4.3 |
| Pydantic     | v2        | schema 校验,前后端共享字段           |
| uvicorn      | latest    | ASGI server                 |

### 5.2 前端

| 库                         | 用途                                                       |
| ------------------------- | -------------------------------------------------------- |
| Vue 3 + Vite + TypeScript | 轻量、SFC 适合侧栏表单                                            |
| xeokit-sdk                | IFC web viewer,内置 web-ifc、拾取、X-ray 半透明、storey model tree |
| pinia                     | 状态管理(global\_id 选中态、覆盖态)                                 |
| axios                     | HTTP 客户端                                                 |

### 5.3 选型理由

- **xeokit vs 纯 Three.js + web-ifc**:xeokit 内置拾取/高亮/X-ray/storey tree,满足"门选取 + 非防火门半透明 + 楼层归属"全部需求,MVP 时间紧用现成的
- **Vue vs React**:Vue 3 SFC 写侧栏表单更直接;xeokit 与框架解耦,Vue 只包一层
- **FastAPI**:自动文档 + Pydantic 共享 schema,前后端联调快;ifcopenshell 已装
- **monorepo**:前后端同仓,演示/部署/提交都简单

***

## 6. 实现阶段(2 天)

| 阶段               | 时长   | 内容                                                     | 产出             |
| ---------------- | ---- | ------------------------------------------------------ | -------------- |
| 0. 脚手架           | 0.5h | 目录结构 + PLAN/SSD/EXPORT\_DESIGN                         | 本轮已完成          |
| 1. 法规预设层         | 2h   | `regulation_presets.json` + `longname_to_a1.json` + 单测 | JSON + 测试通过    |
| 2. IFC 解析 + 规则引擎 | 6h   | `core/` 全部模块 + 在 Clinic/Duplex 上回归                     | 后端能输出完整结果 JSON |
| 3. FastAPI 路由    | 2h   | 所有端点 + OpenAPI 文档                                      | Swagger 可调     |
| 4. 前端 3D viewer  | 4h   | xeokit 加载 + 楼层树 + 拾取 + 高亮 + X-ray                      | 3D 可交互         |
| 5. 前端侧栏 + 联调     | 4h   | 5 个侧栏组件 + 端到端联调                                        | 完整可演示          |
| 6. 演示视频 + 提交     | 2h   | Duplex 录视频 + README + prompts + GitHub                 | 提交邮件           |

**关键里程碑**:

- M1(阶段 2 末):后端 `python -m backend.tests.test_samples` 在 4 样本上全绿
- M2(阶段 4 末):前端能加载 Duplex + 点选门 + 看到基础信息
- M3(阶段 5 末):端到端可演示完整检查流程

***

## 7. 关键约束(来自调研,不可违反)

### 7.1 字段不可依赖(实测 0%)

- `Qto_SpaceBaseQuantities`(全 0%)
- `Pset_SpaceOccupancyRequirements`(全 0%)
- `IfcDoorLiningProperties.LiningThickness`(全 0%)
- `Pset_DoorCommon.FireExit`(全 0%)
- `Pset_DoorCommon.FireRating`(IFC2x3 是字符串占位符,IFC4 是 0%)
- `Pset_BuildingStoreyCommon` 大部分字段(除 AboveGround)
- `IfcRelContainedInSpatialStructure` 把门挂到 IfcSpace(全 0%,挂 storey 才有)

### 7.2 字段可用(实测 ≥50%,多数 100%)

- `IfcDoor.OverallWidth` / `OverallHeight`(100% × 4)
- `IfcSpace.LongName`(100% × 3)
- `IfcElementQuantity` 里的 `IfcQuantityArea`(100% × 3)
- `IfcRelSpaceBoundary`(IFC2x3 大样本 100%,IFC4 小样本 0% → 几何兜底)
- `IfcDoor` 通过 `IfcRelFillsElement` 填 `IfcOpeningElement`(56–100%)
- `IfcDoor` 通过 `IfcRelContainedInSpatialStructure` 挂 `IfcBuildingStorey`(68–100%)

### 7.3 语义标记(必须)

- 门宽必须标 `width_source`(`overall_estimate` / `clear_width` / `geometry` / `unknown`)
- 门宽必须标 `needs_human_review`(OverallWidth 作代理时为 `true`)
- 疏散门必须用推断,标 `inferred_fire_exit=true` + `needs_human_review=true`
- Table B2 起始档是 4–30 人(1–3 人档不存在,Capacity ≤ 3 时用 Clause B13.4 绝对下限 750mm)

### 7.4 跨版本兼容

- 同一套读取代码可跨 IFC2x3 / IFC4 / IFC4.3 工作(Pset 在 IFC2x3 TC1 就存在)
- 不为 IFC4.3 做特殊设计
- ifcopenshell 0.8.5 已验证可读 4 个样本

### 7.5 流程禁止

- 禁止把"数据不完整"判为"不合规"(用 `unknown` 状态)
- 禁止把 `OverallWidth` 直接当 clear width(必须标代理)
- 禁止联网 buildingsmart.org(IFC 规范查询走本地 `research/`)
- 禁止依赖 `IfcSpaceTypeEnum` 区分用途(实测不可信)

***

## 8. 风险与降级

| 风险                                | 概率 | 降级策略                                   |
| --------------------------------- | -- | -------------------------------------- |
| xeokit 加载 Clinic(254 门)慢          | 中  | 演示视频用 Duplex(14 门);Clinic 只做后端回归       |
| ifcopenshell 在 IFC4 上关系链差异        | 低  | 阶段 2 在 4 样本上回归覆盖                       |
| LongName 关键词映射不全                  | 高  | UI 强制 fallback:未匹配的房间让用户手工选 Use Class  |
| IfcRelSpaceBoundary 在 IFC4 小样本 0% | 已知 | 几何 point-in-polygon 兜底(SampleHouse 验证) |
| 前后端联调时间不够                         | 中  | 阶段 5 优先保证"上传→检查→看结果"主链路,侧栏美化后置         |
| 演示视频超 3 分钟                        | 中  | 用 Duplex 小样本 + 写好脚本先彩排                 |

***

## 9. 交付清单(对应任务要求)

- [ ] GitHub 仓库(代码 + prompts)
- [ ] ≤3 分钟演示视频链接
- [ ] 邮件发 `junnaifj@hku.hk`,主题 `【HKU AI Agent Technical Test】姓名_学校`
- [ ] 截止 2026-07-20 23:59

考察重点映射:

- **可运行**:阶段 0–5 产出可演示 Web app
- **有思考**:`docs/`(PLAN/SSD/EXPORT\_DESIGN)+ `taskrequest/`(调研文档)+ 代码内字段来源标记
- **有品味**:四状态设计(不把数据缺失误判为不合规)、统一 ID 架构、导出设计前瞻性、字段陷阱注释

***

## 10. 待用户确认的决策点

1. **前端框架**:Vue 3(推荐) vs React vs 纯 HTML+xeokit CDN(最轻量)
2. **3D 引擎**:xeokit-sdk(推荐,功能全) vs Three.js + web-ifc(更轻但要自己写 picking)
3. **目录命名**:`fsb-door-check/`(当前) vs 其他
4. **阶段顺序**:是否同意先做后端(M1)再做前端(M2/M3),还是并行
5. **演示样本**:Duplex 录视频 + Clinic 验证(当前) vs 反过来
6. **导出格式优先级**:BCF(行业通用) > HTML(可读) > JSON(机器读),是否同意

