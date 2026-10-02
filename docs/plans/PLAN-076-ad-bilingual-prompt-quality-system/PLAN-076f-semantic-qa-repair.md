# PLAN-076f：风险驱动语义 QA 与一次定点修复

> 状态：**部分实施（076i G-005：库函数就绪，流水线编排待接）**
> 父计划：[PLAN-076](./README.md)
> 依赖：[076e](./PLAN-076e-bidirectional-deterministic-qa.md)

## 目标

补足确定性规则难以识别的遗漏、因果关系、医学主客体和语义强度问题，同时限制模型成本、误报和修改范围。语义 QA 不直接批准任务，定点修复也不能绕过确定性 QA 与人工批准。

## 结构化输出契约

QA provider 只允许返回：

```json
{
  "findings": [
    {
      "category": "omission|addition|mistranslation|causality|modality|terminology",
      "severity": "critical|major|minor",
      "source_span": "源文原样片段",
      "target_span": "译文原样片段或空字符串",
      "reason": "简短可审计说明",
      "suggested_target": "仅建议修复后的目标片段",
      "confidence": 0.0
    }
  ]
}
```

source/target span 必须在提交文本中逐字定位；无法定位、schema 不合法或 confidence <0.8 的 finding 丢弃并计入 provider diagnostics。

## 任务

### Task 1：风险段落选择器

仅选择：高风险术语段、数字密集段、否定/情态复杂段、确定性 warning 段、跨页/跨段拼接段。作者、参考文献、纯表格数字和已标 PRESERVE 区域不送语义模型。

**验收标准：**

- [ ] 普通低风险段不调用 QA provider。
- [ ] 选择原因、源 span 和数据外发范围写入审计。
- [ ] confidential 资料只允许内网 provider；外发规则复用 PLAN-071/075。

**验证：**

```bash
uv run pytest tests/quality/test_plan076_risk_selector.py -q
```

**依赖：** 076e
**预计规模：** M（selector、audit adapter、tests，3–5 文件）

### Task 2：双向语义 QA prompt 与响应验证

实现 en-zh/zh-en 的 literature/clinical QA profiles；第三方/模型响应视为不可信输入，先过 JSON Schema、长度限制、span 定位和枚举校验再进入 QA items。

**验收标准：**

- [ ] 无源文证据的“风格建议”不能成为 critical/major finding。
- [ ] prompt injection 样本文本不能改变输出 schema 或要求。
- [ ] provider 超时/非法输出进入 `qa_degraded`，不静默 PASS。

**验证：**

```bash
uv run pytest tests/quality/test_plan076_semantic_qa.py \
  tests/security/test_plan076_qa_untrusted_output.py -q
```

**依赖：** Task 1、076b
**预计规模：** M（prompts、schema、validator、tests，4–5 文件）

### Task 3：一次定点修复

repair prompt 只接收一个源段、当前目标段、已验证 findings、命中术语 policy 和受保护 token。只允许返回替换后的目标段；一个段最多修复一次。

**验收标准：**

- [ ] 修复前后除目标段外所有内容和 ID 不变。
- [ ] 受保护事实变化时丢弃修复并产生 `AD_REPAIR_FACT_DRIFT` blocker。
- [ ] 修复后重新跑 076e 全部规则和语义 finding 定位；未解决问题保持 blocker。

**验证：**

```bash
uv run pytest tests/quality/test_plan076_targeted_repair.py -q
```

**依赖：** Task 2
**预计规模：** M（repair service、pipeline hook、tests，3–5 文件）

### Task 4：成本、时延与误报观测

记录候选段比例、QA 请求数、修复率、被丢弃 finding、修复回滚、token 和耗时；不得记录完整 confidential 文本。

**验收标准：**

- [ ] 每个 run 有 risk-selected/checked/repaired/rejected 聚合指标。
- [ ] P95 总耗时和 token 增幅可与 generic baseline 对比。
- [ ] 超过 25% 发布预算时 verify 标 FAIL，而不是只写 warning。

**验证：**

```bash
uv run pytest tests/quality/test_plan076_qa_metrics.py -q
uv run python scripts/plan076-ad-eval.py --report-performance
```

**依赖：** Tasks 1–3
**预计规模：** S（metrics、report、tests，2–3 文件）

## Checkpoint 076f

- [ ] 模型 QA 无法覆盖确定性 blocker。
- [ ] 一个段最多自动修复一次。
- [ ] provider 故障、非法 JSON、伪造 span 和 prompt injection 均 fail closed。
- [ ] 性能开销在父计划预算内。

## 不做

- 不全文二次“润色”。
- 不把模型置信度当作事实正确性的唯一证据。
- 不自动批准修复后的正式产物。
