---
name: 文档内嵌图片翻译架构定稿
overview: 基于30年全栈专家视角重构PLAN-027：补齐PDF共享XObject解耦、DOCX DrawingML实例级语义、Alpha透明度保真、双层预扫描代际防线以及Hermes裁剪的安全边界防护，建立5个独立子计划，实现DOCX/PDF文档内设计图的中英双向无损翻译与原位遮盖回嵌。
todos:
  - id: p27a-policy-probe
    content: PLAN-027a：实现 doc_image_policy.py（物理尺寸/语种/纯数字门控）、RGBA保真通道与 sidecar /service/image-probe 探针
    status: completed
  - id: p27b-prescan-guard
    content: PLAN-027b：实现 apply-pdf2zh-prescan.py，落地左栏状态组件、Tier-1/2 双阶段扫描与 task_run_id 代际防线
    status: completed
  - id: p27c-docx-overlay
    content: PLAN-027c：重构 DocxTranslator，基于 DrawingML XML 树实现实例解耦、多引用克隆、平滑进度与 Manifest 生成
    status: completed
  - id: p27d-pdf-dual
    content: PLAN-027d：实现 PDF 共享XObject解耦、去整页回退的矢量安全裁剪、透明贴片回嵌与 apply-pdf2zh-docimg.py 补丁
    status: completed
  - id: p27e-verify-ship
    content: PLAN-027e：编写 verify-plan-027.sh 自动化套件（含透明度/共享引用/026回归）、更新 SK-Q002 规范、发布与 WT-027
    status: completed
isProject: false
---

# PLAN-027 文档内嵌图片翻译：工业级双向嵌字与原位回嵌（纲领与子计划体系）

## 一、专家审查：前序方案核心缺陷剖析

经过对抗审查，前序方案存在 7 个致命工程缺陷，已全部在子计划中完成闭环设计：

- **缺陷 1：PDF 共享 XObject 作用域污染（Shared XObject Hazard）**。PDF 中图片以 XObject 字典存在，同一 xref 常被正文、页眉 Logo 或不同尺寸图复用。直接调用 `page.replace_image(xref)` 是全文档破坏性替换。
  - **对策（027d）**：多引用时克隆独立 XObject，仅重定向当前页面局部资源字典，确保零交叉污染。
- **缺陷 2：透明通道与色彩空间毁损（Alpha/SMask Bleed）**。现有 `image_translate.py` 使用 3 通道 BGR，透明 PNG 或带 `/SMask` 的设计图经 PIL 嵌字后，透明区域变成黑框或不透明白底死斑。
  - **对策（027a）**：引入双通道处理，前景文字带嵌字与背景 Alpha 分离，原样恢复 Alpha 蒙版通道。
- **缺陷 3：DOCX 物理包与排版语义脱节（Package Part vs. DrawingML Occurrence）**。仅遍历 `package.iter_parts()` 无法获取显示尺寸（EMU）、裁剪比例（`srcRect`）以及图所在容器（页眉/正文）。
  - **对策（027c）**：解析 DrawingML DOM 树提取 `<wp:extent>` 物理宽高，跨容器或不同裁剪时自动克隆新 ImagePart。
- **缺陷 4：Hermes 抽图逻辑的错误外推（Crop Heuristics Mismatch）**。Hermes 文献入库算法目标是“截一张图保存，宁多勿缺”，失败时允许退回整页；而文档翻译回嵌是“原地覆盖，宁缺勿滥”。
  - **对策（027d）**：剔除整页回退，加入正文文字重叠 >10% 即熔断拒绝的强安全门禁。
- **缺陷 5：上传预扫描的代际竞争与状态污染（Generation Race & Stale Write）**。多文件上传、频繁切换或取消时，异步预扫描回调会无序覆写 UI 与 `state`。
  - **对策（027b）**：建立 `task_run_id` 代际状态机与 per-file state 映射，过期回调直接丢弃。
- **缺陷 6：语种与可翻译度门控缺失（Language & Translatability Gate）**。图中的纯数字、计量单位、化学式或已是目标语言的文字被盲目送翻。
  - **对策（027a）**：建立双向语种判别与纯数字/坐标轴过滤正则，已是目标语种或纯数字图跳过翻译。
- **缺陷 7：单图失败导致文档崩溃（Missing Fault Isolation）**。单张图片 OCR 或 LLM 异常没有局部熔断机制。
  - **对策（027c/027d）**：单图超时或 QC C10 违规时熔断保留原图，生成 `<stem>.imgtr.json` 详细审计清单。

---

## 二、架构全景与子计划索引

```
[用户上传文档 (DOCX / PDF)]
       │
       ▼ (Generation Token 代际防线 - 027b)
[Tier-1 瞬时结构化扫描 (<300ms)] ──> 左栏提示: "检测到 N 处候选设计图"
       │
       ▼ (异步调用 sidecar /service/image-probe, 纯 OCR - 027a)
[Tier-2 文本存在性探针] ────────────> 左栏精确化: "N 处插图中 M 处含可翻译文本"
       │
       ▼ (用户点击翻译)
[文档类型路由与实例解析]
   ├─► DOCX: 解析 DrawingML 树，按实例隔离 ImagePart (027c)
   └─► PDF: 建立实例表，解耦共享 XObject，矢量图安全聚类 (027d)
       │
       ▼
[图片安全预处理 (保留 Alpha/SMask + 语种门控) - 027a]
       │
       ▼
[高精度嵌字流水线 (复用 PLAN-026 C1-C10 QC) - 027a]
       │
       ▼
[原位回嵌与局部遮盖]
   ├─► DOCX: 实例级 Part 替换 / 克隆 (027c)
   ├─► PDF 位图: 尺寸严格对齐，重写 XObject 流 (027d)
   └─► PDF 矢量图: 边界防碰正文，生成局部透明贴片 (027d)
       │
       ▼
[输出 <filename>.imgtr.json 清单 + 自动化全量验收 (027e)]
```

### 详细开发子计划清单

1. **[PLAN-027a: 判定策略、探针 API 与 Alpha 保真](docs/plans/PLAN-027-doc-image-translation/PLAN-027a-policy-and-probe.md)**
   - 物理尺寸/语种/纯数字门控、RGBA 通道保持、轻量级 `/service/image-probe` 接口。
2. **[PLAN-027b: 上传两段预扫描与代际防线](docs/plans/PLAN-027-doc-image-translation/PLAN-027b-upload-prescan-guard.md)**
   - 左栏 `qy_prescan_status` 状态卡片、Tier-1 瞬时结构分析、Tier-2 异步探针、`task_run_id` 代际防线。
3. **[PLAN-027c: DOCX DrawingML 实例解耦与嵌字回填](docs/plans/PLAN-027-doc-image-translation/PLAN-027c-docx-occurrence-overlay.md)**
   - DrawingML DOM 解析、物理尺寸计算、共享 ImagePart 克隆解耦、并发翻译与平滑进度。
4. **[PLAN-027d: PDF 双策略与安全原位贴片](docs/plans/PLAN-027-doc-image-translation/PLAN-027d-pdf-dual-strategy.md)**
   - 页面级实例表、共享 XObject 解耦克隆、去整页回退的矢量安全聚类（重叠>10%拒收）、扫描件 HPD 降级保护。
5. **[PLAN-027e: 自动化验收、Skill 沉淀与发布交付](docs/plans/PLAN-027-doc-image-translation/PLAN-027e-verify-skill-delivery.md)**
   - `verify-plan-027.sh` 6 维自动化断言（透明度/共享引用/正文防覆盖/026回归）、SK-Q002 规范沉淀、部署与发布。
