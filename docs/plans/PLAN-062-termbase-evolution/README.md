# PLAN-062：术语工作台准确度与自动进化

> 状态：**已交付**（遗留 LIVE 三项与机器裁决回填见 [PLAN-063e](../PLAN-063-translation-quality-evolution/PLAN-063e-062-closeout.md)）
> 日期：2026-09-15
> 验收门：`bash scripts/verify-plan-062.sh`
> 后续：[PLAN-063](../PLAN-063-translation-quality-evolution/README.md)

## 目标

修复术语工作台六项缺陷：词库未 seed、噪声候选、实际/推荐译法不合格、已入库词重复审校、Concept ID 不可用、进度条卡死。

## 子计划

| 子计划 | 交付 |
| --- | --- |
| [PLAN-062a](./PLAN-062a-seed-and-purge.md) | 导入 curated 词库、提升 harvest 领域缩写、清理历史 pending |
| [PLAN-062b](./PLAN-062b-candidate-screen.md) | 词典优先 + LLM 裁定的候选准入 |
| [PLAN-062c](./PLAN-062c-paragraph-align.md) | 删除窗口启发式，按段落批次对齐 |
| [PLAN-062d](./PLAN-062d-no-recurring-pending.md) | 已入库词不再进待确认 |
| [PLAN-062e](./PLAN-062e-concept-picker.md) | Concept 选择器与混合检索 |
| [PLAN-062f](./PLAN-062f-nav-and-progress.md) | 保存后下一条 + 图表后处理实时进度 |
| [PLAN-062g](./PLAN-062g-verification-delivery.md) | 测试、verify、WT、部署 |

## 验收边界

- 不实现 PLAN-063 的规则归纳 / 台账 / SK-Q011。
- 不放宽批量确认白名单 `{exact, alias}`。
- LLM 失败只降级，不得让翻译任务失败。
- 语义检索结果不得升为 `hard_constraint`。
