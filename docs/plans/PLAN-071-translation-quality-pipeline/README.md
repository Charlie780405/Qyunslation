# PLAN-071：可审计翻译质量流水线与真实工作台

状态：**已冻结计划，待 Cursor 按子计划实施**

## 接手摘要

截至 `16e65d4`，PLAN-066–070 的 Vue 工作台、SSO/BFF、预检、任务生命周期、QA 产物门禁和实时进度改动均已提交到 `main` 并推送到 `origin/main`。本计划收拢下一阶段的质量修复，不回滚既有提交。

当前生产质量问题不是单纯 UI 问题：新 TranslationRun 走非 GUI `pdf2zh_next` CLI 后，旧版 `gui.py` 中的图片/表格后处理、Logo/印章回填和部分版式链路没有迁入；runner 在 CLI 成功后直接标记 `succeeded/export/100%`，因此 UI 看不到真实 QA、人工复核和导出门禁。现有 FDA 扫描 PDF 已出现 Logo 丢失、版式漂移、邮箱断裂和 `^{th}` 等格式缺陷。

## 冻结决策

- PDF、DOCX、PPTX、图片在同一发布批次接入统一流水线。
- 翻译前强制选择资料等级：`confidential | internal | public`，默认 `internal`。
- `confidential` 只允许内网模型；`internal` 全文只允许内网 Qwen，脱敏后的未决术语可使用外部术语模型；`public` 可选择管理员批准的外部模型。
- 首批模型配置为现有内网 `qwen3.6:35b-a3b`、DeepSeek `deepseek-flash`，以及仅处理脱敏术语的 DeepSeek 配置。用户不能填写任意 API 地址、密钥或模型 ID。
- 所有正式产物必须经过 reviewer 人工批准；QA blocker 未解决时只能生成带水印 review draft。
- 历史产物保留并标记 `legacy_unverified`，允许基于原文件重试，不批量自动重翻、不删除旧数据。
- 新流水线只能调用应用服务，禁止依赖 Gradio DOM、事件队列或浏览器自动化。

## 子计划顺序

| 子计划 | 目标 | 依赖 |
|---|---|---|
| 071a | 质量基线、旧能力盘点、FDA/表格/图片/Office 金标样本 | 无 |
| 071b | 统一 PDF/Office/图片处理服务与版本化 Manifest | 071a |
| 071c | 表格、图片、Logo、印章、签名和版式保真 | 071b |
| 071d | 持久化阶段事件、真实进度和服务重启恢复 | 071b |
| 071e | 确定性 QA、术语门禁、人工审核和正式产物门禁 | 071b–071d |
| 071f | 源译双画布预览、对象检查器和按页懒加载 | 071d–071e |
| 071g | 设置分区、资料等级、模型配置和外部模型治理 | 071b、071e |
| 071h | 专业词库推荐、脱敏、候选风险与审计 | 071e、071g |
| 071i | 历史迁移、灰度、真实浏览器验收和回滚 | 071a–071h |

## 核心契约

### TranslationRun 阶段

`validation → structure → ocr(可跳过) → text → table_figure → layout → qa → review → export`

CLI 成功不能直接产生 `succeeded`。不适用阶段必须记录 `skipped`；无法计算可靠分母时 `progress=null`。只有 reviewer 批准、重新渲染成功且产物与最新 Manifest/QA 快照一致后，任务才能进入 `succeeded/export/100%`。

### 新增接口

- `PATCH /api/v1/preflights/{preflightId}`：资料等级、语言方向、模型配置。
- `GET /api/v1/model-profiles?classification=...`：返回服务端允许的模型配置。
- `GET /api/v1/translation-runs/{runId}/events`：阶段事件流。
- `GET /api/v1/translation-runs/{runId}/preview/source`。
- `GET /api/v1/translation-runs/{runId}/preview/translated`：授权、Range、inline 响应。
- `GET /api/v1/translation-runs/{runId}/qa-items`。
- `POST /api/v1/translation-runs/{runId}/review-decision`：`approve | request_changes | reject`。
- `GET/PUT /api/v1/settings/schema`、`/settings/effective`、`/admin/policies`。

任务创建必须保存模型供应商/模型版本、资料等级、prompt 版本、术语库版本、Manifest 版本和数据外发范围快照。浏览器不得接触 OIDC/API/模型密钥。

## 格式质量要求

- Logo、印章、签名和监管机构标识作为 `PRESERVE` 对象，复用原始图像或矢量对象，按原边界框和层级回填，并保存源对象哈希。
- 普通图片只翻译确认的文字区域；低置信度保留原图并生成 warning，不臆造内容。
- 表格先锁定行列、合并单元格、表头、阅读顺序和数字列，再按单元格翻译；数字、剂量、单位、百分比和统计符号作为保护 token。
- 邮箱、URL、PIND/IND 编号、法规引用、楼层序号等作为原子 span，禁止断裂或产生 `^{th}`。
- DOCX/PPTX 克隆原始 OOXML 包，仅替换可翻译文本，保持媒体关系、主题、页眉页脚和 Logo 二进制。

## 术语与模型规则

批准 exact/alias → 规则归一化 → 语义候选 → LLM 未决候选；高风险药名、靶点、剂量、适应症、终点、方案编号和禁用词不能自动批准。外部术语请求只携带最小脱敏上下文，脱敏失败时回退内网 Qwen。候选输出必须通过 JSON Schema，并记录模型版本、上下文摘要、风险和审计轨迹。

DeepSeek `deepseek-flash` 需在实施时做能力探测并记录具体版本；别名升级不能影响既有任务快照。模型配置以白名单形式提供，不开放自由填写模型 ID。

## 验收门槛

1. FDA 20 页扫描样本：Logo 原样保留，PIND、Reference ID、邮箱、地址、日期、签名区完整，无明显重叠、截断、`^{th}` 或邮箱断裂。
2. 表格密集 PDF：行列、合并关系、数字、表头和图注保持；图片密集 PDF：底图不被重绘，图片文字可复核。
3. DOCX/PPTX：样式、页眉页脚、表格、文本框、母版、图片和媒体关系保持。
4. UI 阶段条、任务列表和右侧流程读取同一服务端事件；QA、review 和 export 不得被伪造为已完成。
5. 源文与译文可在同一任务页对照预览，刷新后恢复页码、缩放和对象选择。
6. 内部文件不能通过前端或直接 API 选择外部全文模型；脱敏术语请求不能包含原始身份信息。
7. 未批准任务只能下载带水印预览稿；直接调用下载接口也不能绕过门禁。
8. 自动化测试、Alembic 迁移测试、真实 Chrome DevTools 流程和真实样本证据全部通过；缺少真实浏览器证据时不得标记发布完成。

## Cursor 接手入口

建议 Cursor 从 `071a` 开始，先阅读：

- `docs/plans/PLAN-066-clinical-workbench/README.md`
- `docs/plans/PLAN-068-workbench-preflight-task-lifecycle/README.md`
- `docs/walkthroughs/WT-068-preflight-task-lifecycle.md`
- `docs/walkthroughs/WT-069-qa-artifact-gate-recovery.md`
- `docs/walkthroughs/WT-070-live-progress-and-stale-preflight.md`
- 当前文件 `docs/plans/PLAN-071-translation-quality-pipeline/README.md`

每个子计划遵循“失败测试 → 最小修复 → 聚焦回归 → 精确提交 → WT 证据”的顺序。禁止用静态截图代替真实翻译闭环证据。

## 本次提交明确排除

- `.cursor/mcp.json`：本机绝对路径的开发配置，不适合推送。
- `var/oidc/pilot-rsa.pem`：未加密私钥，禁止进入 Git。
- `slide-deck/`：与本计划无关的大型用户工作资产。

这些文件保持工作区原状，不影响 Cursor 读取已提交计划。
