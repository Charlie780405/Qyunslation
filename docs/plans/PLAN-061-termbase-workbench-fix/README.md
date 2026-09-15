# PLAN-061：术语工作台可用性修复

> 状态：**工程实现完成；真实工作台五项实点待验收**
> 日期：2026-09-15
> 验收门：`bash scripts/verify-plan-061.sh`

## 目标

修复 PLAN-060 工作台三处硬伤：保存被空单元格顶掉、实际/推荐译法结构性为空、`300 mg` 类噪声被当术语抽取。

## 已交付

- 桥接异常携带 HTTP 状态码；保存回调表格空值不再覆盖输入框；Timer 不再擦除确认译法。
- `glossaries/term-candidate-rules.toml` + `candidate_rules.py`：数字/剂量委托 `classify_cell_policy == PRESERVE`。
- 译后抽取前置排除；`classify_risk` 改读规则文件。
- `term_align.py`：词库 / 逐字保留 / 窗口三级对齐；整篇一次 LLM 只补推荐译法，失败降级。

## 子计划

| 子计划 | 交付 |
| --- | --- |
| [PLAN-061a](./PLAN-061a-save-path-diagnosability.md) | 保存链路与错误可诊断 |
| [PLAN-061b](./PLAN-061b-candidate-admission-rules.md) | 候选准入规则 SSOT |
| [PLAN-061c](./PLAN-061c-observed-and-suggested-target.md) | 实际译法与 AI 推荐译法 |
| [PLAN-061d](./PLAN-061d-verification-delivery.md) | 回归、部署与 WT |

## 验收边界

- 不训练模型，不放宽批量确认白名单 `{exact, alias}`。
- LLM 建议失败只降级，不得让翻译任务失败。
- LIVE 浏览器五项缺失时 verify 报 `BLOCKED`，不得写成 PASS。
