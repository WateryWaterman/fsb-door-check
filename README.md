# FSB Door Check — HKU AI+BIM 技术测试 MVP

香港《Code of Practice for Fire Safety in Buildings 2011 (2024 Edition)》Part B **门净宽检查 + Occupant Capacity 自动推算** 的 Web 微原型。

> 状态:**已完成 MVP**(2026-07-20)。可运行,86 测试全绿,4 个 IFC 样本端到端验证通过。

---

## 快速开始

### 前置
- Python 3.13+(含 ifcopenshell 0.8.5)
- 现代浏览器(Chrome/Edge,需支持 WebGL + ES modules)

### 启动
```powershell
cd fsb-door-check/backend
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
打开 http://127.0.0.1:8000/ ,点 "Load IFC" 加载样本。

**单一端口**:FastAPI 挂载 `frontend/` 静态文件,前后端同源,无 CORS 问题。

### 样本
| 文件 | 用途 | 规模 | web-ifc 兼容 |
|---|---|---|---|
| `samples/Duplex_xeokit.ifc` | **演示首选** | 14 门 / 21 空间 | ✓ |
| `samples/Clinic_Architectural_IFC2x3.ifc` | **功能验证** | 254 门 / 269 空间 / 2586 objects | ✓ |
| `samples/SampleHouse_IFC4.ifc` | IFC4 路径 | 3 门 / 4 空间 | ✓ |
| `samples/Duplex_Apartment_IFC2x3.ifc` | 2011 Revit 旧导出 | 14 门 | ✗(web-ifc@0.0.51 兼容性,后端分析仍可用,3D 会显示友好错误) |

---

## 功能演示流程(≤3 分钟)

1. **加载 IFC**:点 "Load IFC" → 选 `Duplex_xeokit.ifc` → 3D 模型渲染,侧栏显示 14 门 / 21 空间
2. **Run Check**:点顶部 "Run Check" → 每门按 HK FSB Table B2 + Clause B13.4 检查,3D 中门按 PASS(绿半透明)/ FAIL(红)/ UNKNOWN(黄)/ OVERRIDE(蓝)着色
3. **检查门**:点 3D 中的门 → 侧栏 Door tab 显示 GlobalId / OverallWidth / width_source / Fire Exit / 关联空间(UseClass / Capacity / 来源标签)/ 检查结果(规则 / 阈值 / 实测 / 缺口 / needs_human_review)
4. **标记防火门**:Door tab 勾选 "Mark as fire exit" → 重算
5. **覆盖空间用途/人数**:Door tab 下拉选 UseClass 或输入人数 → 重算
6. **阈值编辑器**:Regulation tab → "Threshold Override" 选 Table B2 档位 → 改宽度 → Apply → 全部门重算
7. **楼层过滤**:顶部 "Storey" 下拉选楼层 → 3D 中该层门突出,其它 x-ray 弱化,Results 列表同步过滤
8. **键盘导航**:按 `F` 跳下一个 FAIL,`U` 跳下一个 UNKNOWN
9. **导出**:顶部 "BCF/HTML/JSON" 按钮 → 提示"设计中,见 docs/EXPORT_DESIGN.md"(MVP 阶段返回 501,设计文档先行)

---

## 更新历史

### 4. viewer UX 改进第二批(commit `7713cd5`)

- **A. Results 搜索框**:Results tab 顶部增加"Search by GlobalId or Name"输入框,实时过滤(忽略大小写,部分匹配),与 status / storey 过滤叠加生效。Clear 按钮一键清空。
- **B. 修复选中门后状态卡住**:之前 `highlightDoor()` 会强制 `obj.xrayed = false`,导致 PASS 门被选中后丢失透明状态;现在只设 `obj.selected = true`(描边反馈),`xrayed / colorize` 由 `colorizeByStatus()` 唯一控制(runCheck / override 后调用),保持稳定。
- **C. 防火门高亮切换**(默认 ON):顶部 ctxbar 增 `Fire-exit ON/OFF` 按钮,用 xeokit `obj.highlighted` 通道(红色 0.937/0.267/0.267,alpha 0.6)显示所有 `is_fire_exit=true` 的门。**与 `selected` 描边、`colorize` 染色三通道独立互不冲突**:
  - 防火门外圈红光环 + 体色显示检查结果
  - 标记 / 取消防火门后自动重应用
  - 按钮关掉后切换 fire-exit 不会高亮,按钮重新打开立即应用

- **D. 楼层选中其它楼层淡显**:选中楼层实体保持原状(notXray),其它楼层的 x-ray 透明度 `alpha 0.85 → 0.92`(更淡,几乎只剩轮廓,含边线)。0-door 楼层选中时仍只有该楼层实体显示,门不亮。

### 关键技术修复

- **场景级 material 切换**:发现 xeokit WebIFCLoaderPlugin 加载的实体**没有 entity-level `xrayMaterial`/`highlightMaterial`**,所有 alpha/颜色必须设在 scene 级别。新增 `_setXrayAlpha()` helper,把 `setNonDoorsXrayed / colorizeByStatus / resetDoorColors / focusDoors / focusStorey` 全部统一改用 scene-level `scene.xrayMaterial.alpha = X`。

### 3. viewer UX 改进第一批(commit `83758e1`)

- **门限选**:`obj.pickable = isDoor`,非门要素不可拾取;配合 `_setupPicking` 里对 `_doorIds.has(gid)` 的双保险过滤。
- **flyTo 拉远**:用 aabb + padding(`max(maxDim*2, 1.5`)替代 `flyTo([obj])`,镜头到门距离约为门尺寸 **7 倍**,既能清晰看见门又有上下文。
- **楼层聚焦**:新增 `focusStorey(storeyId)`。`IfcBuildingStorey` 不在 `scene.objects`(无 3D 几何),改用 `metaObjects` 索引;新增 `_storeyEntityMap` 收集每个 storey 的全部子实体。

### 2. viewer fallback normalize + 单模型隔离 + 关闭清理(commit `04a1bf3`)

- `POST /model/normalize`:ifcopenshell 重写 STEP,返 octet-stream,作为 web-ifc@0.0.51 解析失败的 fallback。注:此方案对 Duplex_Apartment_IFC2x3.ifc(2011 Revit 导出)无效 — ifcopenshell 保留触发 web-ifc bug 的底层数据结构(web-ifc 0.0.51-0.0.54 全部有此 bug,0.0.55+ 修复但与 xeokit 2.6.112 不兼容)
- `_destroyCurrentModel()`:加载新模型前 destroy 旧的(避免 SceneModel 残留冲突);unique modelId 防止 id 碰撞
- `beforeunload` 清理 session;后端启动时 `_cleanup_normalized_dir()`

### 1 viewer IFC 加载修复(commit `73b61c4`)

- xeokit 2.6 `WebIFCLoaderPlugin` 必须显式注入 `{WebIFC, IfcAPI}`,本地化 `web-ifc-api.js` 到 `/lib/`
- 改 `loadIfcUrl → loadIfcArrayBuffer`(传 ArrayBuffer 而非 blob URL),绕开 blob URL + 缓存破坏参数导致的 `ERR_FILE_NOT_FOUND` bug

---

## 项目结构

```
fsb-door-check/
├── README.md
├── docs/
│   ├── PLAN.md              # 初版计划(目标/范围/架构/技术栈/阶段)
│   ├── SSD.md               # 系统序列图(Mermaid)
│   ├── CONTRACT.md          # 前后端 JSON 契约 + 高亮映射规则(字段名严格对齐)
│   └── EXPORT_DESIGN.md     # 导出格式设计(BCF>HTML>JSON,MVP 不实现)
├── backend/                 # FastAPI + ifcopenshell(Python 3.13)
│   ├── app/
│   │   ├── main.py          # FastAPI 入口 + 静态文件挂载 + wasm MIME
│   │   ├── api/             # 路由:model / check / override / presets / export
│   │   ├── core/            # 业务:ifc_loader / space_area / space_use /
│   │   │                    #      occupant_capacity / door_width / door_space_link /
│   │   │                    #      fire_exit_infer / rule_engine / pipeline
│   │   ├── models/schemas.py
│   │   └── session.py       # 会话内存态 + 覆盖态
│   ├── presets/
│   │   ├── regulation_presets.json   # Table B1(8 UseClass)+ Table B2(14 档)+ Clause B13.4/B30.3
│   │   └── longname_to_a1.json       # LongName 关键词→UseClass 映射(含 Revit 缩写)
│   └── tests/               # 86 测试:presets + samples + api + normalize + export
└── frontend/                # 纯 HTML + xeokit 2.6 + Alpine.js(无构建步骤)
    ├── index.html           # 左右分栏:左 3D canvas + 右侧栏(Regulation/Door/Results 三 tab)
    ├── src/
    │   ├── viewer.js        # xeokit 封装(加载/拾取/高亮/X-ray/楼层隔离/fallback normalize)
    │   ├── app.js           # Alpine 组件(状态 + API 调用 + 键盘 + beforeunload 清理)
    │   └── api.js           # fetch 后端
    └── lib/                 # 本地化(绕开 CDN Tracking Prevention)
        ├── xeokit-sdk.es.min.js   # xeokit 2.6.112
        ├── web-ifc-api.js         # web-ifc@0.0.51 ES module
        ├── web-ifc.wasm           # web-ifc 运行时
        └── alpine.cdn.min.js      # Alpine.js 3.14
```

---

## 架构 — 双结构 + 统一 ID

| 层 | 职责 | 技术 |
|---|---|---|
| 前端 | 轻量逻辑:3D 渲染、用户输入采集、基础信息展示 | 纯 HTML + xeokit 2.6(web-ifc@0.0.51)+ Alpine.js 3.14 |
| 后端 | 重逻辑:IFC 深度解析、规则计算、阈值管理、normalize fallback | FastAPI + ifcopenshell 0.8.5 + Pydantic v2 |
| **统一 ID** | 前后端关联纽带 | **IFC GlobalId**(22 字符 base64) |

### 双结构(前后端各自读 IFC)
- **前端**:xeokit 内置 `WebIFCLoaderPlugin` + 本地 `web-ifc.wasm` 直接读 IFC 几何 + 显式属性,用于 3D 渲染和拾取
- **后端**:ifcopenshell 做关系链(`IfcRelSpaceBoundary` / `IfcRelAggregates`)+ Pset + 量集 + 规则计算
- **关联**:两端通过 `global_id` 关联同一实体;前端点选门 → `GET /doors/{gid}` 取后端分析结果

### normalize fallback(零误判)
- 前端 xeokit 加载失败时(如 2011 Revit 旧 STEP 变体)→ 自动 `POST /model/normalize` → 后端 ifcopenshell 重写 STEP → 前端重试
- 只在真失败时触发,不预测、不误判
- 仍失败的文件(如 `Duplex_Apartment_IFC2x3.ifc`):后端分析不受影响(sidebar 数据有效),3D 显示友好错误提示

### 单模型隔离 + 关闭清理
- 每次加载新 IFC 前 `destroy()` 旧 SceneModel + `DELETE` 老 session,确保只分析单一模型
- `beforeunload` 事件触发 `DELETE /model/{sid}` 清理 session
- 后端启动时清空 `uploads/normalized/`(双保险)

---

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/model/upload` | 上传 IFC,ifcopenshell 解析,返回 session_id + doors + spaces + summary |
| GET | `/model/{sid}/summary` | 会话摘要 |
| POST | `/model/normalize` | ifcopenshell 重写 STEP,返回 octet-stream(viewer fallback 用) |
| DELETE | `/model/{sid}` | 删 session(关闭网页 / 加载新模型时) |
| GET | `/doors/{gid}?session={sid}` | 单门详情 + 关联空间 + 楼层 |
| POST | `/check/{sid}` | 运行检查,返回每门 CheckResult + summary |
| POST | `/override/{sid}` | 覆盖(fire_exit / space_use / occupancy / threshold / storey_sprinkler / storey_entrance) |
| GET | `/presets` | 法规预设(Table B1/B2 + Clause B13.4/B30.3 + UseClass 描述) |
| POST | `/export/{sid}?format=bcf\|html\|json` | 导出(MVP 返 501 + 设计文档链接) |
| GET | `/health` | 健康检查 |
| GET | `/docs` | Swagger UI |

---

## 核心约束(摘自 `taskrequest/ifc_field_fill_rate.md` 实测)

- ✅ 可用字段:`IfcDoor.OverallWidth`(100%)、`IfcSpace.LongName`(100%)、`IfcElementQuantity.IfcQuantityArea`(100%)、`IfcRelSpaceBoundary`(IFC2x3 100%)
- ❌ 不可依赖(实测 0%):`Qto_SpaceBaseQuantities`、`Pset_SpaceOccupancyRequirements`、`IfcDoorLiningProperties.LiningThickness`、`Pset_DoorCommon.FireExit`/`FireRating`、`Pset_BuildingStoreyCommon`
- 门宽用 `OverallWidth` 作代理,标 `width_source="overall_estimate"` + `needs_human_review=true`
- 疏散门用推断(跨空间 + 名字 + 通向楼梯),标 `inferred_fire_exit`
- 因 `FireExit` 字段 0%,**所有门默认可选取**,UI 让用户手动标记防火门
- Table B2 起始档 4–30 人(1–3 人档不存在,capacity≤3 用 Clause B13.4 绝对下限 750mm)
- 跨版本:IFC2x3 / IFC4 / IFC4.3 同一套代码

---

## 测试

```powershell
cd fsb-door-check/backend
python -m pytest tests/ -v
```
**86 测试全绿**:
- `test_presets.py` — Table B1/B2 数据完整性
- `test_samples.py` — 4 样本回归(Duplex/Clinic/SampleHouse/Snowdon,跨 IFC2x3/IFC4)
- `test_api.py` — 15 + 4 + 4 测试:upload/check/override/presets/export(501)/normalize/delete
- `test_samples.py` — GlobalId 唯一性、跨版本兼容

---

## 与工作区其他目录的关系

| 目录 | 关系 | 说明 |
|---|---|---|
| `taskrequest/` | 只读 | 调研文档(法规预设、字段深查、填充率实测、调研报告) |
| `samples/` | 只读 | 4 个 IFC 样本 + 填充率分析脚本 |
| `research/` | 只读 | IFC 4.3 规范本地副本(用 `ifc-spec-lookup` skill 查) |
| `AGENTS.md` | 项目指南 | IFC 规范查询规则、网络代理要求 |
| **`fsb-door-check/`** | **读写** | **本项目,所有实现在此** |

---

## 部署

### 本地开发
```powershell
cd fsb-door-check/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Docker(规划中)
Dockerfile + docker-compose 将在后续添加。预计结构:
- 单容器:Python 3.13 + ifcopenshell + uvicorn,挂载 `frontend/` 静态文件
- 端口 8000
- 体积关注:ifcopenshell 依赖较多,镜像约 500MB

---

## 技术决策记录

| 决策 | 选择 | 原因 |
|---|---|---|
| 前端框架 | 纯 HTML + xeokit + Alpine.js(无构建) | 快速 MVP,避免 Vite/构建步骤,xeokit 2.6 ES module 本地化绕开 Edge Tracking Prevention |
| IFC 渲染 | xeokit 2.6 WebIFCLoaderPlugin + web-ifc@0.0.51 | 浏览器内直接读 IFC,无需预转换 XKT |
| 双结构 | 前端 xeokit 读几何 + 后端 ifcopenshell 读关系 | 各取所长,xeokit 擅长渲染,ifcopenshell 擅长关系链 |
| 门宽代理 | OverallWidth(实测 100%) | ClearWidth / LiningThickness 实测 0%,无法用 |
| 防火门 | UI 手动标记 + 推断 | Pset_DoorCommon.FireExit 实测 0% |
| 导出 | 501 + 设计文档先行(BCF>HTML>JSON) | MVP 不实现,但体现"懂行业标准" |
| normalize fallback | 失败时触发 ifcopenshell 重写 | 零误判,只在真失败时触发 |

---

## 交付清单

- [x] GitHub 仓库(代码 + 文档)
- [ ] ≤3 分钟演示视频(用户自录,用 `Duplex_xeokit.ifc` 演示)
- [ ] 邮件发 `junnaifj@hku.hk`,主题 `【HKU AI Agent Technical Test】姓名_学校`
- [ ] 截止 **2026-07-20 23:59**

考察重点:可运行 + 有思考 + 有品味(不追求完美)
