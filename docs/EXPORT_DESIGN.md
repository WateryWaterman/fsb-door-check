# 导出设计 — FSB 门净宽检查 MVP

> **状态**:设计阶段,不在 MVP 实现。后端 `/export` 端点返回 501 + 本文档链接。
> **目的**:从"检查目的"反推导出文件应含内容,以及如何嵌入 Revit / 其它 viewer 工作流。
> 演示视频口述本设计,体现"有思考 + 有品味"。

---

## 1. 设计原则 — 从检查目的反推

合规检查的本质目的有四个,导出格式必须分别满足:

| 检查目的 | 导出须满足 | 对应字段 |
|---|---|---|
| **留痕** | 谁、何时、用什么规则、对哪个模型、得到什么结论 | 元信息 + 规则信息 + 结果 |
| **可追溯** | 每个 fail 都能定位到规则条文 + 模型元素 + 字段来源 | rule_source + global_id + width_source + capacity_source |
| **可嵌入** | 能回到 Revit / Navisworks / Solibri / BIMcollab 继续工作 | BCF 格式(行业标准) |
| **可复议** | 审图员 / 第三方能用相同输入复现检查 | 模型 SHA256 + 预设快照 + 覆盖历史 |

**核心原则**:导出不是"截图 + 表格",而是**可重现的检查记录**。任何 fail 都应让审图员能:(1) 找到模型里的门,(2) 找到规则条文,(3) 知道为什么判 fail,(4) 知道数据是否可信。

---

## 2. 导出格式(三种,优先级递减)

### 2.1 BCF(BIM Collaboration Format)— 首选 ⭐

**是什么**:buildingSMART 国际标准,Revit / Navisworks / Solibri / BIMcollab / Trimble Connect 原生支持。

**为什么首选**:无缝嵌入现有 BIM 工作流,设计师在 Revit 里直接看到 issue,改完关闭。

**怎么映射**:
| BCF 字段 | FSB 检查内容 |
|---|---|
| `Topic.title` | `门净宽不足 — ${door_name} (${global_id})` |
| `Topic.topic_status` | `open`(fail)/ `closed`(pass after override) |
| `Topic.priority` | `critical`(fail 缺口 >200mm) / `warning`(其它) |
| `Topic.topic_type` | `Code Compliance` |
| `Comment` | 规则条文 + 阈值 + 实测值 + 字段来源标记 |
| `Viewpoint` | 引用 `global_id` + 视角快照(相机位置 + 可见性) |
| `Viewpoint.snapshot` | 3D 截图(可选) |
| `Label` | `HK_FSB_2011_B2` / `Clause_B13_4` |

**MVP 后实现路径**:
- Python 库 `bcf-xdk` 或直接写 XML(BCF v2.1 是 XML)
- 每个 fail / unknown 生成一个 Topic
- pass 不生成 Topic(避免噪音)

### 2.2 HTML 报告 — 次选

**是什么**:自包含单 HTML 文件(内联 CSS + 3D 截图 base64),可邮件发送。

**为什么有**:业主、审图员、非 BIM 人员没装 Revit 也要能看。

**结构**:
```
报告封面(项目名、检查时间、检查者、模型 SHA256)
├── 1. 模型摘要(空间数、门数、检查门数、IFC 版本)
├── 2. 适用规则(Table B2 全表 + Clause 引用链接)
├── 3. 统计摘要(pass/fail/unknown/overridden 计数 + 饼图)
├── 4. 失败门详情卡片(每个 fail 一张)
│   ├── 门基础信息(global_id、Name、OverallWidth、width_source)
│   ├── 关联空间(LongName、面积、capacity、capacity_source)
│   ├── 阈值(threshold_mm + 档位 + rule_source)
│   ├── 实测值(measured_mm)+ 缺口(deficit_mm)
│   ├── needs_human_review 标记
│   ├── 3D 截图(标注门位置)
│   └── 人工覆盖记录(如有)
├── 5. 待人工复核门清单(unknown 状态)
└── 6. 附录:预设快照 + 覆盖历史
```

### 2.3 JSON(机器可读)— 兜底

**是什么**:完整结构化数据,供下游 API / CI / 二次开发用。

**用途**:
- 接 CI/CD:每次模型提交自动跑检查,JSON 结果入库
- 接自研 dashboard:多项目汇总
- 接 LLM:把 JSON 喂给 LLM 做合规问答

**Schema**:与后端 `/check/{sid}` 返回一致,外加元信息 + 预设快照 + 覆盖历史。

---

## 3. 导出内容清单(无论格式,必含)

### 3.1 元信息(session meta)
```json
{
  "check_time_utc": "2026-07-20T14:30:00Z",
  "checker": "anonymous (MVP)",
  "model": {
    "filename": "Clinic_Architectural_IFC2x3.ifc",
    "sha256": "abc123...",
    "ifc_schema": "IFC2X3_TC1",
    "counts": {"spaces": 269, "doors": 254, "storeys": 5}
  },
  "preset_id": "hk_fsb_2011_b2_default",
  "preset_version": "1.0.0",
  "preset_snapshot": { /* 完整预设 + 覆盖 */ },
  "override_history": [ /* 用户覆盖时间线 */ ]
}
```

### 3.2 规则信息(per rule)
```json
{
  "preset_id": "hk_fsb_2011_b2_default",
  "rule_source": "HK FSB 2011 (2024) Part B, Table B2 + Clause B7.1",
  "rule_link": "https://www.bd.gov.hk/.../fs_code2011.pdf#page=43",
  "thresholds_table": "Table B2 完整 14 档",
  "absolute_minimum": {"clause": "B13.4", "value_mm": 750, "note": "capacity>3 时门 ≥750mm,双扇任一扇 ≥600mm"}
}
```

### 3.3 元素结果(per door)
```json
{
  "door_global_id": "3cO6iV$Hj5M8t$3Q2n$R0V",
  "door_name": "M_900x2100",
  "door_basic": {
    "overall_width_mm": 900,
    "overall_height_mm": 2100,
    "width_source": "overall_estimate",
    "needs_human_review": true,
    "storey_global_id": "...",
    "storey_name": "Level 1"
  },
  "related_space": {
    "space_global_id": "...",
    "space_longname": "Consultation Room 101",
    "area_m2": 18.5,
    "area_source": "IfcQuantityArea.Name=NetFloorArea",
    "use_class": "4a",
    "use_class_source": "longname_keyword:consultation → 4a office",
    "use_class_overridden": false
  },
  "occupant_capacity": {
    "value": 3,
    "source": "area/factor: 18.5/9",
    "factor": 9,
    "overridden": false
  },
  "fire_exit": {
    "value": true,
    "source": "inferred_fire_exit",
    "overridden": false,
    "inference_reason": "crosses two spaces + name contains 'exit'"
  },
  "check_result": {
    "status": "unknown",
    "reason": "capacity<=3, Table B2 not applicable, B13.4 absolute minimum 750mm applies",
    "threshold_mm": 750,
    "threshold_source": "Clause B13.4 (absolute minimum)",
    "measured_mm": 900,
    "deficit_mm": null,
    "b13_4_pass": true,
    "needs_human_review": true
  },
  "human_review_notes": []
}
```

### 3.4 统计摘要
```json
{
  "total_doors": 254,
  "checked_doors": 87,
  "by_status": {"pass": 60, "fail": 5, "unknown": 20, "overridden": 2},
  "top_fails": [ /* deficit_mm 降序,前 5 */ ],
  "needs_review_count": 22
}
```

---

## 4. Revit / viewer 嵌入工作流

### 4.1 Revit(BCF 路径)— 主推荐
```
FSB MVP 导出 BCF.zip
  ↓ 设计师在 Revit 用 BCF Manager 插件(免费)导入
每个 fail 变成 Revit 视图批注 + 视角
  ↓ 设计师点击 issue,Revit 跳到该门
设计师修改门宽(如 900 → 1050)
  ↓ 在 BCF Manager 关闭 issue,附注释
重新导出 IFC → 再跑 FSB 检查 → 验证 pass
```

**兼容插件**Revit 自带 BCF 支持外,还有 BIMcollab、Solibri Office Connector、Trimble Connect。

### 4.2 Navisworks / Solibri
BCF 原生支持,直接打开 .bcfzip,无需插件。

### 4.3 web viewer(后续)
- 导出 JSON → 自研 viewer 加载 → 链接分享给业主
- 优点:业主无需装软件,点击链接看结果
- MVP 后可基于现有 frontend 复用

### 4.4 IFC 回写(高级,不做)
理论上可把检查结果作为自定义 Pset 写回 IFC:
```
Pset_FireSafetyCheck:
  - CheckStatus: enum (pass/fail/unknown/overridden)
  - CheckRule: "HK_FSB_2011_B2"
  - CheckTime: timestamp
  - DeficitMM: number
```
**不推荐**:污染原模型,审图员不喜欢;且 IFC 回写工具链不成熟。BCF 更合适。

### 4.5 报告邮件(HTML 路径)
HTML 报告作为附件直接邮件发送,适合:
- 业主/审图员非技术人员
- 初步沟通,后续走 BCF 跟进
- 归档存证

---

## 5. MVP 阶段做法

| 项 | MVP | 后续 |
|---|---|---|
| `/export` 端点 | 返回 501 + 本文档链接 | 实现 BCF 导出 |
| 前端"导出"按钮 | 点击弹"设计中"提示 + 文档链接 | 三种格式下拉选择 |
| 演示视频 | 口述导出设计思路(1 句话) | 实录导出 → Revit 导入 |
| 数据准备 | 后端 check 结果 JSON 已具备所有字段 | 加元信息 + 预设快照 + 覆盖历史 |

---

## 6. 设计取舍说明

**为什么 BCF 优先而非自定义 JSON**:
- BCF 是 buildingSMART 标准,与 IFC 同源,体现"懂行业标准"
- Revit/Navisworks 原生支持,真正"嵌入工作流"而非停在报告
- 评审看到 BCF 会理解作者懂 BIM 协同,加分

**为什么 HTML 也保留**:
- 业主/审图员不装 Revit,HTML 是最低门槛的可读格式
- 邮件发送方便,归档存证

**为什么 IFC 回写不做**:
- 污染原模型,审图员抵触
- 工具链不成熟(ifcopenshell 写 Pset 容易破坏文件)
- BCF 已解决"关联模型元素"需求

**为什么 JSON 兜底**:
- 机器可读,接 CI/CD / LLM / dashboard
- 与 `/check` 返回一致,实现成本最低
