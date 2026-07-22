# FSB Door Check — 功能总结与技术原理

> **用途**:拍演示视频时的讲解参考。按本文的结构顺序介绍即可覆盖全部亮点。
> 建议配合 `samples/Duplex_xeokit.ifc`(14 门,加载快)或 `samples/Clinic_Architectural_IFC2x3.ifc`(254 门,数据丰富)演示。

***

## 一、项目是什么

一个 **Web 微原型**,自动检查建筑 IFC 模型里的门是否满足香港《Fire Safety in Buildings 2011 (2024 Edition)》Part B 的门净宽要求。

**一句话定位**:上传 IFC → 自动算出每个空间的容纳人数 → 查法规表得到该空间需要的门宽 → 和门实际宽度比对 → 3D 模型里红/绿/灰标出达标/不达标/不适用。

**为什么做这个**:这是香港大学 AI+BIM 技术测试题。真实场景里,消防合规检查靠人工逐门核对,大型项目动辄几百扇门,容易漏检。用 AI+BIM 自动化能省大量人工。

***

## 二、技术栈(30 秒带过)

| 层   | 技术                                   | 为什么选它                                              |
| --- | ------------------------------------ | -------------------------------------------------- |
| 前端  | 纯 HTML + xeokit 2.6 + Alpine.js 3.14 | 无构建步骤,改完浏览器刷新即生效;xeokit 是开源 BIM viewer             |
| 后端  | Python 3.13 + FastAPI + ifcopenshell | ifcopenshell 是 IFC 解析的事实标准;FastAPI 自动生成 Swagger 文档 |
| 渲染  | web-ifc\@0.0.51 (WASM)               | 浏览器内直接读 IFC 几何,无需预转换格式                             |
| 关系链 | ifcopenshell (后端 Python)             | 读 IfcRelSpaceBoundary 等关系,xeokit 不擅长这个             |
| 测试  | pytest,115 个测试                       | 每个规则都有回归测试                                         |

**核心设计 — "双结构"**:前端用 xeokit+wasm 读 IFC 的几何(负责 3D 渲染),后端用 ifcopenshell 读 IFC 的关系链(负责规则计算)。两端通过 IFC GlobalId(22 字符唯一 ID)关联同一扇门。各取所长。

***

## 三、已实现功能 + 实现原理

### 功能 1:IFC 上传与双路径解析

**做什么**:用户拖入 `.ifc` 文件,前端 3D 渲染 + 后端关系解析同时进行。

**原理**:

- 前端:xeokit 的 `WebIFCLoaderPlugin` 用 web-ifc WASM 直接在浏览器里解析 IFC 几何,渲染成 3D 场景
- 后端:ifcopenshell 读取 IFC 的关系层(IfcRelSpaceBoundary 门-空间关系、IfcRelAggregates 空间层级等)
- 两路独立,互不阻塞 —— 3D 渲染失败不影响规则计算,反之亦然

**亮点**:有 fallback 机制 —— 如果 web-ifc 解析失败(旧版 IFC 格式 bug),自动调后端 `/model/normalize` 让 ifcopenshell 重写 STEP 文件再重试。零误判,只在真失败时触发。

### 功能 2:空间容纳人数(Occupant Capacity)自动推算

**做什么**:每个 IfcSpace(房间)自动算出它能容纳多少人。

**原理**(3 步):

1. **取面积**:优先 `IfcQuantityArea.NetFloorArea` → `GSA BIM Area`(Revit 同义词)→ 几何兜底
2. **识别用途**:用 `IfcSpace.LongName`(实测 100% 填充)做关键词匹配 → 映射到香港 Table A1 的 16 类 Use Class(如 "OFFICE" → 4a,"CLASSROOM" → 3a)
3. **算人数**:`capacity = ceil(面积 / 因子)`。因子来自 Table B1(如 4a 办公 = 9m²/人)

**排除空间**:厕所/走廊/楼梯/电梯等关键词命中 → `capacity=0`,不参与门宽检查(这些不是疏散门)。

**关键决策**:不依赖 `Pset_SpaceOccupancyRequirements`(实测填充率 0%),而是用 LongName 关键词。这适应了真实 IFC 文件的填充率现状。

### 功能 3:门宽合规检查(核心功能)

**做什么**:每扇门按 HK FSB Table B2 + Clause B13.4 检查,输出三态结果。

**原理**:

1. 取门宽:`IfcDoor.OverallWidth`(实测 100% 填充)作代理值(真实 ClearWidth 实测 0%)
2. 查阈值:按关联空间的 capacity 查 Table B2(如 4-30 人需 850mm,31-200 人需 1050mm...)
3. 比对:`measured_width >= threshold` → pass,否则 fail
4. 边界处理:capacity≤3 用 Clause B13.4 绝对下限 750mm(Table B2 不覆盖);capacity>3000 需屋宇署个案核定

**三状态系统**(不是简单的 pass/fail 二分):

| 状态            | 含义                       | 颜色 |
| ------------- | ------------------------ | -- |
| `pass`        | 门宽达标                     | 深绿 |
| `fail`        | 门宽不足                     | 红色 |
| `non_passage` | 不适用/无法判定(排除空间、宽度缺失、人数未知) | 灰色 |

> 为什么要有 `non_passage`:厕所的门不需要查疏散宽度,强行标 fail 是误报。这个状态避免了"什么都 fail"的噪音。

### 功能 4:双扇门(Double-leaf)检测

**做什么**:识别双扇门,额外校验每扇叶 ≥600mm(Clause B13.4)。

**原理**:

- 读 `IfcDoor.OperationType` 或经 `IsTypedBy`/`IsDefinedByType` 关联的 `IfcDoorType.OperationType`
- 枚举值前缀为 `DOUBLE_DOOR`(如 `DOUBLE_DOOR_SINGLE_SWING`)才是真双扇门
- **易错点**:`DOUBLE_SWING_LEFT/RIGHT` 是单扇双向摆动,不是双扇 —— 必须要求 `DOUBLE_DOOR` 前缀,不能用 `DOUBLE` 子串匹配

**校验逻辑**:总宽通过 Table B2 后,如果双扇门,估算每叶 = `measured_width / 2`(假设 50/50 均分),若 <600mm → fail。因为 IFC 几乎不提供逐叶净宽,估算结果始终标 `needs_human_review=True`。

### 功能 5:疏散门(Fire Exit)推断

**做什么**:自动推断哪些门是疏散门。

**原理**(因为 `Pset_DoorCommon.FireExit` 实测 0%,只能推断):

1. **跨空间**:门通过 IfcRelSpaceBoundary 关联两个空间 → 可能是疏散通道门
2. **名字关键词**:门名含 "exit"/"corridor"/"stair" → 推断疏散
3. **通向楼梯**:门关联的空间靠近 IfcStair → 推断疏散
4. **用户标记**:UI 可手动勾选,覆盖推断

每个推断都带 `fire_exit_source` 标签(如 `inferred_cross_space`),用户可看到判定依据。

### 功能 6:用户覆盖(Override)系统

**做什么**:用户可修正自动推算的任何字段,后端立即重算受影响的门。

**支持的覆盖类型**:

| 覆盖类型                | 作用                           | 示例                    |
| ------------------- | ---------------------------- | --------------------- |
| `space_use`         | 改空间用途 → 重算 capacity → 重算门宽阈值 | LongName 识别错了,手动改为 4a |
| `occupancy`         | 直接指定人数                       | 知道某房间固定 50 人          |
| `fire_exit`         | 标记/取消防火门                     | <br />                |
| `threshold` (table) | 自定义 Table B2 阈值表             | 项目有特殊审批口径             |
| `storey_sprinkler`  | 标楼层有无喷淋                      | (影响阈值,规划中)            |
| `checked`           | 人工已复核标记                      | 不影响计算,只做进度跟踪          |

**技术细节**:覆盖存在内存 session 里,后端用 `affected_results` 返回受影响的门,前端局部更新 —— 不需要全量重拉。覆盖后会保留操作历史(导出 JSON 时包含)。

### 功能 7:3D 可视化与交互

**做什么**:3D 模型里门按状态着色,点选门显示详情,楼层过滤,键盘导航。

**交互清单**:

- 点门 → 侧栏显示 Door tab(GlobalId/宽度/来源/关联空间/检查结果/判定理由)
- 楼层下拉 → 只看该层,其他层淡显
- 按 `F` → 跳到下一个 fail 门
- 按 `U` → 跳到下一个 non\_passage 门
- Results 列表 → 搜索/过滤/点行飞到 3D 对应门
- 非门元素半透明(xray),让门突出

**技术细节**:xeokit 2.6 的 WebIFCLoaderPlugin 加载的实体没有 entity-level material,所有透明度/颜色必须设在 scene 级别。踩过坑后统一用 `scene.xrayMaterial.alpha` + `obj.colorize`。

### 功能 8:可追溯性(Traceability)— 每个判定都能解释

**做什么**:每个门的 status 都有完整的推理链,用户能看懂"为什么是这个结果"。

**三层追溯**:

1. **来源标签**:每个推算字段都带 `*_source`(如 `width_source="overall_estimate"`,`capacity_source="table_b1_factor"`)—— 用户知道这个值怎么来的
2. **"Why this status?" 面板**:点门后侧栏显示编号推理链,如:
   ```
   1. 空间 LongName="CORRIDOR" → 命中排除关键词
   2. capacity = 0(排除空间,不计人数)
   3. status = non_passage(不是疏散门,不查宽度)
   ```
3. **计算公式 + 条款引用**:Regulation tab 里有 5 个公式的完整写法 + 对应法规条款号(B7.1/B13.4/B30.3),并附 BD 官方 PDF 链接

### 功能 9:阈值表编辑器

**做什么**:用户可自定义 Table B2 阈值(断点式 UI),改完全部门重算。

**原理**:

- 用户只填容量断点(30, 200, 500...),系统自动拼区间 \[3,30] \[31,200] \[201,500] \[501,∞]
- 后端验证:无重叠、无缝隙、cmin≥3、末条 max=null
- 保存后 `custom_threshold_table` 存在 session 里,`GET /presets/{sid}` 返回自定义表
- Reset 按钮一键恢复默认 Table B2

**边界处理**:capacity≤3 默认走 Clause B13.4(750mm);如果用户自定义表第一档 cmin≤3,优先用自定义值 —— 这个边界 case 有专门测试。

### 功能 10:JSON 导出

**做什么**:一键导出完整检查报告(JSON 格式,浏览器直接下载)。

**导出内容**(自包含,约 500KB):

- `export_meta`:导出时间/工具/版本
- `session`:文件名/IFC 版本/计数
- `regulation`:法规预设全表 + 自定义阈值表
- `summary`:统计摘要(pass/fail/non\_passage + top fails)
- `doors`:全部门(每扇内联 related\_space + check\_result)
- `overrides`:用户覆盖历史
- `field_dictionary`:61 条字段说明(含义/来源/可能取值)

**设计决策**:没有用 BCF(BIM Collaboration Format,XML)是因为它是 issue 交换格式,不适合 compliance report。JSON 自包含 + 字段字典,既可给人读,也可喂给 LLM/CI 做 dashboard。BCF/HTML 格式留了 501 占位 + 设计文档,体现"懂行业标准但克制"。

### 功能 11:Markdown 质检报告 + 邮件发送(LLM 驱动)

**做什么**:一键生成 Markdown 格式的质检报告并通过邮件发送给指定收件人。

**原理**:

1. **数据压缩**:`_build_report_input()` 把完整 JSON 导出数据压缩成 LLM 友好的格式(model_info / check_stats / threshold_state / user_overrides / storey_stats / door_samples),避免 token 浪费
2. **LLM 生成**:`_generate_markdown()` 调 DeepSeek API,system prompt 锚定 6 段式结构 + 800-1200 字,生成专业 Markdown 报告
3. **降级机制**:DeepSeek 不可用(无 key / 429 / 超时 / 网络错误)时,`_fallback_markdown()` 用纯逻辑生成报告(`llm_used=false`),保证功能可用
4. **邮件发送**:`_send_email_resend()` 调 Resend API `/emails` 端点发送
5. **容错**:Resend 失败时返回 502,但 Markdown 报告保留在响应体里(用户可复制)

**前端交互**:点 "Email Report" → 弹 dialog 填收件人邮箱 + 可选 focus\_fail\_only(只报 fail 门)+ storey\_filter(按楼层过滤)→ 发送 → 显示发送结果。

**环境变量**(`.env` 文件,见 `backend/.env.example`):
- `DEEPSEEK_API_KEY` / `DEEPSEEK_API_BASE` / `DEEPSEEK_MODEL_NAME` — LLM 生成
- `RESEND_API_KEY` / `REPORT_FROM_EMAIL` — 邮件发送
- 不配 key → 降级纯逻辑报告 + 502(发不出邮件但报告内容可用)

***

## 四、当前局限性(诚实说明)

### 局限 1:门宽是代理值,不是净宽

**问题**:`IfcDoor.OverallWidth` 是门总宽(含门框),不是疏散净宽(clear width)。真实的 ClearWidth 实测填充率 0%,LiningThickness(门框厚度)也是 0%。

**影响**:所有门都标 `needs_human_review=True`,提示"宽度是代理值,需现场实测净宽"。

**缓解**:Override 系统允许用户手动输入实测净宽(规划中,当前只能改空间属性)。

### 局限 2:双扇门每叶宽度是估算

**问题**:IFC 几乎不提供逐叶净宽,代码用 `measured_width / 2` 假设 50/50 均分。

**影响**:双扇门的 Clause B13.4 校验(每叶≥600mm)结果不可信,只能提示人工复核。

**缓解**:明确标注 `needs_human_review=True` + human\_review\_notes 里写"估算值,需核实实际 active/inactive leaf 宽度"。

### 局限 3:空间用途靠关键词,不是权威数据

**问题**:LongName 关键词匹配(如 "OFFICE" → 4a)是启发式推断,不是建筑师的权威分类。

**影响**:可能误匹配(如 "STORAGE" 命中但实际是档案室,用途分类有争议)。

**缓解**:每个匹配带 `use_class_source="longname_keyword"` + `confidence` 标签,用户可 Override 修正。模糊关键词(如 "lab")标 `ambiguous` 要求人工确认。

### 局限 4:无持久化,重启丢数据

**问题**:session 存在后端内存,进程重启或 Railway sleep 后丢失。

**影响**:用户需要重新上传 IFC + 重跑检查。覆盖操作也丢失。

**原因**:MVP 范围内不引入数据库,降低部署复杂度。这是明确的取舍。

### 局限 5:web-ifc 兼容性 bug

**问题**:web-ifc\@0.0.51-0.0.54 对 2011 Revit 导出的 IFC2x3 有 `offset is out of bounds` bug;0.0.55+ 修复但移除了 `OPTIMIZE_PROFILES` 与 xeokit 2.6.112 不兼容。

**影响**:`Duplex_Apartment_IFC2x3.ifc`(2011 Revit)前端 3D 渲染失败,但后端分析正常(侧栏有数据)。会显示友好错误提示。

**缓解**:normalize fallback(ifcopenshell 重写 STEP)对部分文件有效,但对这个特定 bug 无效(底层数据结构保留)。在 MVP 范围内无法修复。

### 局限 6:单用户、单模型、无协作

**问题**:一次只能分析一个 IFC 文件,没有用户认证,没有多用户协作。

**原因**:MVP 定位是技术演示,不是生产系统。真实部署需要加数据库 + 认证 + WebSocket 实时同步。

### 局限 7:BCF/HTML 导出未实现

**问题**:BCF 和 HTML 导出返回 501,只有 JSON 可用。

**原因**:MVP 优先级 —— JSON 覆盖了数据需求,BCF/HTML 是锦上添花。设计文档已写好(`docs/EXPORT_DESIGN.md`),代码留了 501 占位 + 设计说明,体现"知道该做什么但克制不实现"。

### 局限 8:防火门推断是启发式

**问题**:`Pset_DoorCommon.FireExit` 实测 0%,只能靠跨空间/名字/楼梯推断。

**影响**:推断可能误报(如跨空间但不是疏散门)。

**缓解**:所有门默认可选取,UI 让用户手动标记/取消。推断结果带 `fire_exit_source` 标签,用户可看到依据。

### 局限 9:缺乏方便的批量修改属性的能力

**问题**:目前check仍需要极大的人工参与和判断，还不能做到批量check或者批量更改归属面积等属性。

**影响**:对效率提升有限，仅能作为可视化粗略了解情况，并且unknown的门过多。

**缓解**:待定。

<br />

***

## 五、演示建议流程(≤3 分钟)

1. **加载 IFC**(15 秒):点 "Load IFC" → 选 `Duplex_xeokit.ifc` → 3D 渲染,侧栏显示 14 门
2. **Run Check**(10 秒):点 "Run Check" → 3D 里门按 pass(绿)/fail(红)/non\_passage(灰)着色
3. **看点门**(30 秒):点一扇绿门 → 侧栏 Door tab → 看 width\_source / 关联空间 / capacity / 阈值 / 判定理由。点 "Why this status?" 看推理链
4. **改空间用途**(30 秒):Door tab 下拉改 UseClass → 看 capacity 变化 → 门颜色可能从 non\_passage 变 pass
5. **阈值编辑器**(30 秒):Regulation tab → Edit Thresholds → 改一档 → Apply → 全部门重算,顶部统计变化
6. **楼层过滤 + 键盘**(15 秒):选楼层 → 按 F 跳 fail 门
7. **JSON 导出**(10 秒):点 JSON 按钮 → 下载文件 → 打开看 field\_dictionary
8. **邮件报告**(20 秒):点 "Email Report" → 填邮箱 → 发送 → 查看 Markdown 报告(LLM 生成的专业质检报告)

**一句话收尾**:这个原型证明 AI+BIM 能自动化消防合规检查的"粗筛"环节 —— 把几百扇门里真正需要人工复核的十几扇筛出来,每扇都带完整推理链和法规引用。不是替代审图员,而是给他们一个"优先级队列"。
