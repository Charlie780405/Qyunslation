# PLAN-071h：专业词库推荐规则优化

> 状态：**已实现（浏览器证据 BLOCKED）**
> 父计划：[PLAN-071](./README.md)
> 依赖：[071e](./PLAN-071e-qa-term-gate-formal.md)、[071g](./PLAN-071g-settings-classification-models.md)

## 目标

保留并强化「确定性优先」术语链路；为外部术语调用增加脱敏、JSON Schema、六元组缓存键与风险禁自动批准；保证 QA 与检查器读取同一术语解析结果。

## 现状

| 阶段 | 模块 | 要点 |
| --- | --- | --- |
| exact/alias | `glossary/resolver.py` ~151–218 | semantic 仅 fallback |
| 硬约束 | `glossary/term_policy.py` 16–26 | exact/alias ≥0.99 |
| SSOT 注入 | `glossary/ssot.py` | — |
| 语义检索 | `persist/term_embedding_repo` + `workbench/term_align.suggest_from_termbase` ~198–312 | threshold 0.88 |
| LLM 候选 | `term_align.suggest_targets` ~315–413 | `gateway.provider` → Ollama chat |
| 缓存 | `~/.cache/qyunslation/term-align/v2` | env `QYUNSLATION_TERM_SUGGEST*` |
| 风险 | `glossary/candidate_rules.classify_risk_by_rules`；`workbench/evidence.classify_risk` | high/normal |
| 062 筛 | `glossary/term_screen.screen_terms` | 亦调 provider |
| 译后桥 | `workbench/bridge.py` | Gradio/API 审校 |

缺口：无统一脱敏报告；LLM 输出无强制 JSON Schema；缓存键未钉死模型/prompt/术语库版本；检查器与 QA 可能读不同解析快照。

## 任务

### Task 1：确定性优先链路不变（契约测试加固）

顺序强制：

1. 已批准 exact/alias 硬约束
2. 归一化、词干和领域规则匹配
3. 语义检索只作建议
4. LLM 只处理仍未解决的候选
5. 高风险候选始终人工审核

**验收：** 有序单测：命中 exact 时不调用 LLM（mock provider 断言）。

### Task 2：脱敏与外发门禁

新增 `qyunslation/glossary/redaction.py`：

- 术语请求只含最小必要上下文。
- 内部/机密文档先替换姓名、邮箱、编号、组织信息。
- 产出脱敏报告（替换计数、类别、是否失败）。
- 脱敏失败 → 回退内网 Qwen，**不**发送外部模型（与 071g classification 矩阵一致）。
- confidential：禁止外部术语模型，即使 UI 误传。

**验收：** fixture 含邮箱/姓名时外部请求 body 无原文；失败路径调用 internal provider。

### Task 3：JSON Schema 与缓存键

- 新增 `qyunslation/glossary/suggestion_schema.json`（建议译名、置信度、理由、领域、风险、来源）。
- `suggest_targets` 校验失败则丢弃并记 warning，不入库。
- 缓存键六元组：源术语、上下文摘要、语言方向、模型版本、prompt 版本、术语库版本。

**验收：** schema 不合规被拒；改 prompt 版本缓存不命中。

### Task 4：风险与批准策略

- 统一走 `candidate_rules.classify_risk_by_rules`（消除 bridge 双轨差异或明确委托）。
- 药名、靶点、剂量、适应症、终点、方案编号、禁用词：**不能自动批准**。
- 仅低风险 exact/alias 允许受限批量批准。
- 术语建议不静默改写历史任务；仅显式重新应用或新 generation 生效。

**验收：** 高风险批量批准 API 返回 400；旧 run 术语快照不变。

### Task 5：与 QA / 检查器同源

- 任务级术语解析结果写入可版本化快照（`term_summary` 从 `snapshot_pending` 推进到具体状态 + 内容哈希）。
- `pipeline/qa` 术语类检查与 RunDetail 检查器读同一快照 ID。

**验收：** 故意制造不一致时 QA 产物一致性检查报 blocker；正常路径两侧字段一致。

## 数据库 / 接口变更

- 可扩展 `term_summary` JSON schema（文档化）；必要时 `term_resolution_snapshot` 表（若 JSON 过大）。
- 现有 `/terms/*`、`/concepts/*/promote` 批准路径加风险校验。
- 外部调用审计日志字段：profile_version、redaction_report_id、egress=allowed|blocked|fallback_internal。

## 测试文件

- `tests/glossary/test_plan071h_redaction.py`
- `tests/glossary/test_plan071h_suggestion_schema.py`
- `tests/glossary/test_plan071h_cache_key.py`
- `tests/glossary/test_plan071h_risk_autobatch.py`
- `tests/pipeline/qa/test_term_snapshot_consistency.py`

## 完成门槛

- 每个推荐词可追溯到规则、模型、上下文、术语库版本和审核人。
- 脱敏失败不外发；高风险不自动批准；QA 与检查器同源。

## 验证命令

```bash
pytest -q tests/glossary/test_plan071h_*.py tests/pipeline/qa/test_term_snapshot_consistency.py
```

## 不做

- 不替换 embedding 模型或重建整库向量。
- 不重开 PLAN-062/063 台账大重构（只对接快照）。
- 不在客户端做脱敏（必须服务端）。
