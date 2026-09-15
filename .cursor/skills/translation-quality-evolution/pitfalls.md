# 踩坑（SK-Q011）

1. 空单元格顶掉输入框（`_qy060_table_confirmation` 返回 `""` 而非 `None`）。
2. HTTP 状态码被塌缩（`_bridge_request` 把 403/409 统一成「暂不可用」）。
3. `gr.Timer` 周期性擦除正在输入的内容。
4. 实际/推荐译法结构性为空（PDF 证据不带 term span）。
5. 剂量与数字进候选（未复用 `classify_cell_policy`）。
6. 词库 seed 未执行会让对齐静默退化成猜测（PLAN-062：Concept 库曾只有 2 条）。
7. LLM 裁定降级静默吞词：`generic` / `error` / `cap` 直接不进候选。
8. 补丁脚本粗标记幂等导致现场与仓库漂移（`already patched` 但缺 `_qy_tbl_progress`）。
9. 规则内容变更未 bump `version` 使台账指纹失真。
