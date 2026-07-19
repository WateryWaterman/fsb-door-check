# FSB Door Check — HKU AI+BIM 技术测试 MVP

香港《Code of Practice for Fire Safety in Buildings 2011 (2024 Edition)》Part B **门净宽检查 + Occupant Capacity 自动推算** 的 Web 微原型。

> 状态:🚧 计划阶段(2026-07-19)。完整计划见 `docs/PLAN.md`。

---

## 快速开始(计划中,代码未实现)

### 后端
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# Swagger: http://localhost:8000/docs
```

### 前端
```powershell
cd frontend
npm install
npm run dev
# http://localhost:5173
```

### 样本
- 演示视频用:`../samples/Duplex_Apartment_IFC2x3.ifc`(14 门,快)
- 功能验证用:`../samples/Clinic_Architectural_IFC2x3.ifc`(254 门,全)
- IFC4 路径验证:`../samples/SampleHouse_IFC4.ifc`

---

## 项目结构(摘要)

```
fsb-door-check/
├── README.md                  # 本文件
├── docs/
│   ├── PLAN.md                # 初版计划(目标/范围/架构/技术栈/阶段/ID 规范)
│   ├── SSD.md                 # 系统序列图(Mermaid)
│   └── EXPORT_DESIGN.md       # 导出格式设计(BCF/HTML/JSON)
├── backend/                   # FastAPI + ifcopenshell
│   ├── app/                   # main + api/ + core/ + models/ + session
│   ├── presets/               # regulation_presets.json + longname_to_a1.json
│   └── tests/                 # 4 样本回归
├── frontend/                  # Vue 3 + Vite + xeokit
│   └── src/
│       ├── viewer/            # 3D 渲染(左侧)
│       ├── sidebar/           # 侧栏(右侧)
│       ├── store/             # global_id 选中/覆盖态
│       └── api/               # axios 客户端
└── prompts/                   # 开发 prompt 记录(交付要求)
```

详细职责见 `docs/PLAN.md` 第 4 节。

---

## 架构 — 双结构 + 统一 ID

| 层 | 职责 | 技术 |
|---|---|---|
| 前端 | 轻量逻辑:基础信息获取、3D 渲染、用户输入采集 | Vue 3 + xeokit(web-ifc) |
| 后端 | 重逻辑:IFC 深度解析、规则计算、阈值管理 | FastAPI + ifcopenshell |
| **统一 ID** | 前后端关联纽带 | **IFC GlobalId** |

- 前端用 xeokit 内置 web-ifc 直接读 IFC 几何 + 显式属性(本地 wasm)
- 后端用 ifcopenshell 做关系链 + Pset + 规则计算
- 两端通过 `global_id` 关联同一实体

详见 `docs/PLAN.md` 第 2-3 节、`docs/SSD.md`。

---

## 与工作区其他目录的关系

| 目录 | 关系 | 说明 |
|---|---|---|
| `taskrequest/` | 只读 | 调研文档(法规预设、字段深查、填充率实测、调研报告) |
| `samples/` | 只读 | 4 个 IFC 样本 + 填充率分析脚本 |
| `research/` | 只读 | IFC 4.3 规范本地副本(用 ifc-spec-lookup skill 查) |
| `AGENTS.md` | 项目指南 | IFC 规范查询规则、网络代理要求 |
| **`fsb-door-check/`** | **读写** | **本项目,所有实现在此** |

---

## 核心约束(摘自 `taskrequest/ifc_field_fill_rate.md`)

- ✅ 可用字段:`IfcDoor.OverallWidth`(100%)、`IfcSpace.LongName`(100%)、`IfcElementQuantity.IfcQuantityArea`(100%)、`IfcRelSpaceBoundary`(IFC2x3 100%)
- ❌ 不可依赖:`Qto_SpaceBaseQuantities`、`Pset_SpaceOccupancyRequirements`、`IfcDoorLiningProperties.LiningThickness`、`Pset_DoorCommon.FireExit`/`FireRating`(实测全 0%)
- 门宽用 `OverallWidth` 作代理,必须标 `width_source="overall_estimate"` + `needs_human_review=true`
- 疏散门用推断(跨空间 + 名字 + 通向楼梯),标 `inferred_fire_exit`
- 因 `FireExit` 字段 0%,**所有门默认可选取**,UI 让用户手动标记防火门
- Table B2 起始档 4–30 人(1–3 人档不存在,capacity≤3 用 Clause B13.4 绝对下限 750mm)
- 跨版本:IFC2x3 / IFC4 / IFC4.3 同一套代码

---

## 交付(对应任务要求)

- [ ] GitHub 仓库(代码 + prompts)
- [ ] ≤3 分钟演示视频链接
- [ ] 邮件发 `junnaifj@hku.hk`,主题 `【HKU AI Agent Technical Test】姓名_学校`
- [ ] 截止 **2026-07-20 23:59**

考察重点:可运行 + 有思考 + 有品味(不追求完美)
