# PLAN-063c：SK-Q011 全局自进化总纲

> 父计划：[PLAN-063](./README.md)

目标：`.cursor/skills/` 下 SK-Q001..Q010 全是分域 skill，缺一份总纲。本子计划补上，并按症状做路由。

## 1. `.cursor/skills/translation-quality-evolution/SKILL.md`（SK-Q011）

**铁律**：

- 每次交付必须跑 SK-Q008 capture 与 `ledger.record_run`。
- 规则变更必须 bump `version` 并过 verify 门。
- 未跑金标回归不得改硬约束。
- 规则提案一律人工 promote，不自动落地。

**router 表**（症状到分域 skill）：

- 表格崩 / 串格 / 列并了 → SK-Q009
- 图内嵌字 / 译文丢字 / 遮盖 → SK-Q002
- 改了没效果 / 依然如故 → SK-Q004（进程边界）
- 补丁打了但现场没变 / `already patched` 却行为是旧的 → SK-Q004 + 本 skill 的标记清单 parity
- 译文段落丢 / 摘要碎片 → SK-Q005、SK-Q007
- 术语链（候选污染、两列空、保存被顶掉）→ 本 skill
- 候选突然很少 / 缩写一个都没进待确认 → 本 skill 的 screen 盲区排查

**每轮固定动作**：译后 → QA/QC 证据落盘 → 候选规则提案 → 人工裁决 → 词库/规则 bump → 金标回归 → 台账曲线。

`pitfalls.md` 初始条目（来自 PLAN-061/062 实测）：

1. 空单元格顶掉输入框（`_qy060_table_confirmation` 返回 `""` 而非 `None`）。
2. HTTP 状态码被塌缩（`_bridge_request` 把 403/409 统一成「暂不可用」）。
3. `gr.Timer` 周期性擦除正在输入的内容。
4. 实际/推荐译法结构性为空（PDF 证据不带 term span）。
5. 剂量与数字进候选（未复用 `classify_cell_policy` 这个不译 SSOT）。
6. **词库 seed 未执行会让上层所有对齐策略静默退化为猜测**，且猜测结果可经批量确认污染权威词库（PLAN-062 实测：线上 Concept 库只有 2 条概念，而 curated CSV 有 376 条）。
7. **LLM 裁定降级会静默吞词**：`screen_terms` 在 provider 异常、超 `max_per_doc`、开关关闭时一律判 `generic`，词直接不进候选，痕迹只剩一个不落库的计数器。候选变少要先怀疑裁定通道，而不是「这篇没有术语」。
8. **补丁脚本粗标记幂等导致现场与仓库漂移**：`apply-pdf2zh-*.py` 只按大标记判「已打过」，仓库新增的片段不会重打。PLAN-062 现场 `gui.py` 缺 `_qy_tbl_progress`，靠人肉 grep 才发现；`deploy-translate-stack.sh` 的指纹只覆盖 sidecar，GUI 补丁无门禁。判据必须是标记**清单**，不是单一 marker。
9. **规则内容变更未 bump `version` 会让台账指纹失真**：PLAN-062 现场手加 denylist 条目而 `version` 仍是 `062-v1`，跨版本趋势对比失去意义。

## 2. 扩 `.cursor/skills/skill-registry/error-signatures.toml`

紧随 PLAN-062 已登记的 `SIG-TERM-SEED-EMPTY`，新增六条签名：

- `SIG-TERM-SAVE-SWALLOWED` — 症状「保存后输入清空、状态仍 pending」→ 查 `_qy060_table_confirmation` 返回值与 `chosen_target` 优先级。
- `SIG-TERM-COLUMNS-EMPTY` — 症状「实际/推荐译法全是占位」→ 查 Concept 库是否已 seed、`align_observed` 命中层级、`QYUNSLATION_TERM_SUGGEST`。
- `SIG-TERM-CANDIDATE-NOISE` — 症状「300 mg / n/N / 两字母缩写 / OCR 乱码进候选」→ 查 `should_exclude_from_termbase` 与 `rules_version`。
- `SIG-TERM-SCREEN-BLIND` — 症状「候选突然很少 / 缩写一个都没进待确认」→ 查 `screen_generic_ratio`、`origin=error|cap` 计数、provider 可达性、`QYUNSLATION_TERM_SCREEN`。
- `SIG-GUI-PATCH-STALE` — 症状「补丁脚本打印 already patched 但现场行为是旧的」→ 比对现场 `gui.py` 与仓库补丁的标记清单，扩 `upgrade_post_if_stale` 的 stale 判定后重打。
- `SIG-RULES-VERSION-DRIFT` — 症状「规则明显改了但台账曲线没断点」→ 查 `term-candidate-rules.toml` 内容哈希与 `registry.md` 登记的 `version` 是否一致。

## 3. registry 补登

`registry.md` 补登 SK-Q010（当前游离未登记）与新增的 SK-Q011。
