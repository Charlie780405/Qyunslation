# PLAN-043a：042b 直替写回修复

> 状态：已完成
> 父计划：[PLAN-043](./PLAN-043-regulatory-form-label-leakage.md)
> 优先级：**P0**（042 部署后 P1 汉字 89→177 的回归止血）

## 背景

表格链未交付时，表单标签由 BabelDOC 段落链绘制。042b 在词表命中后调用不存在的 `set_paragraph_translated`，只改 `paragraph.unicode`，**composition 仍为源汉字**，且标记已译跳过 LLM——这是当前漏译的**直接触发器**。

## 交付

改 [`scripts/apply-pdf2zh-042b-short-label.py`](../../../scripts/apply-pdf2zh-042b-short-label.py)：

1. 命中词表后：`get_translate_input` + `post_translate_paragraph(..., glossary_target)`（绕过 `pre_translate` 的 min_length 拦截）。
2. `post_translate` 返回 False 或抛错 → **不** `translated_ids.add`，落入 LLM。
3. `_lookup` 使用 `normalize_source`；支持 optional 下一行 1–2 字 suffix 拼回（与 043b 共用 helper）。
4. 补丁脚本须**替换**旧 inject 块（idempotent upgrade），避免现场仍跑 broken 042b。

## 验收

- 合成夹具：词表命中短段落后 composition 为英文；LLM translator 不被调用。
- 611-2期再译后 P1 汉字 **< 177**（相对 042b 回归基线）。
- `test_042b_patcher_injects_marker` 仍 PASS；新增 writeback composition 断言。
