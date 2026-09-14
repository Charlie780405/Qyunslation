# PLAN-058：医药专业术语闭环、预翻译解析与混合检索

> 状态：**工程实现已完成，真实金标门待执行**
> 日期：2026-09-14
> 目标分支：`codex/plan-058-pharma-termbase-loop`
> 工作树：`/home/dev/.cursor/worktrees/qyunslation/plan-058-pharma-termbase-loop`
> 验收门：`bash scripts/verify-plan-058.sh`

## 目标

形成可重复的闭环：

`翻译完成 → 提取文件术语 → 人工确认 → 项目词库入库 → 下次译前快速检索 → 注入确认译法 → 译后 QA`

核心路径是确定性优先：已确认术语由规范化索引和最长词组匹配直接命中，不调用 embedding；只有未知、变体或多义候选才进入 bge-m3 语义建议。语义建议永远不能直接覆盖译文。

作用域优先级固定为：

`组织强制词 > 固定表单词 > 项目确认词 > 临床基础词 > 会话词 > 自动采集词`

PostgreSQL 是正式事实源，`pgvector` 存储 ConceptTerm 向量；SQLite JSON 仅用于本地测试和离线回退。所有候选、出现位置、决定和版本变化都可审计。

## 已交付代码

- Concept 增加项目、术语类型、定义、权威来源和运行时作用域索引。
- ConceptTerm 增加规范化文本；支持 preferred、synonym、abbreviation。
- 新增 ConceptTermEmbedding、DocumentTermCandidate、DocumentTermOccurrence、TermDecision 及 `058a0001`/`058b0001` 迁移；058b 兼容修复首次部署缺少 Python pgvector 时的 JSON 向量列。
- 译前 `/api/v1/terms/resolve` 返回匹配、术语策略包和 termbase 版本；`/terms/search` 对未命中词提供低置信语义建议。
- 译后候选提取、位置聚合、乐观锁人工裁决、批量确认、词条提升和审校摘要 API。
- 术语策略可注入现有 TXT、Markdown、HTML、JSON、SRT、ASS 及 Markdown-based PDF/Office 路径；可比较文本的硬术语 QA 未通过时阻止正式稿，二进制原生写回路径明确记录 QA unavailable。
- 评测模块输出 Recall@5、出现级召回、Top-1 Precision、高置信覆盖率和精确/别名检出率。

## 子计划

| ID | 交付 |
| --- | --- |
| [PLAN-058a](./PLAN-058a-baseline-contract.md) | 基线、术语分类、指标与 API 契约 |
| [PLAN-058b](./PLAN-058b-storage-vector.md) | PostgreSQL 模型迁移、项目隔离、pgvector 与回填 |
| [PLAN-058c](./PLAN-058c-pretranslation-retrieval.md) | 译前确定性扫描、缓存与混合检索 |
| [PLAN-058d](./PLAN-058d-posttranslation-extraction.md) | 译后候选、双语对齐、出现位置和幂等聚合 |
| [PLAN-058e](./PLAN-058e-review-governance.md) | 术语面板契约、人工裁决、别名和作用域治理 |
| [PLAN-058f](./PLAN-058f-policy-qa-gate.md) | 策略注入、译后 QA、定点修订和正式稿门禁 |
| [PLAN-058g](./PLAN-058g-evaluation-delivery.md) | 金标评测、性能回归、全量门禁、WT 和交付 |

## 质量与性能门

真实金标至少覆盖 1,000 次术语出现、300 个 Concept、20 份医药文件，包含文献、临床、监管、CTD、PPT、poster 和图片 OCR，中英双向。

- 唯一术语召回率、出现级召回率、Concept Recall@5、Top-1 Precision：`≥95%`。
- 高置信覆盖率：`≥80%`；已批准精确术语检出率：`≥99%`；正式译文遵从率：`≥98%`。
- 10 万 ConceptTerm 规模下，500 个候选精确解析 P95 `≤200ms`；任务缓存命中 P95 `≤50ms`。
- 精确/别名命中不得调用 bge-m3；向量失败必须降级并标记，不得伪造硬译法；租户/项目越界为零。

默认门禁验证工程实现和离线测试；真实金标通过 `QYUNSLATION_PLAN058_LIVE=1` 与 `QYUNSLATION_PLAN058_GOLD` 接入。缺少金标、数据库或泰州 bge-m3 只报告 `BLOCKED`。

## 范围边界

本计划不训练翻译模型，也不下载或分发样本。优先使用确定性术语库、上下文提示约束和人工裁决；只有积累至少 5,000 条高质量人工裁决且指标仍不足时，另立计划评估微调。
