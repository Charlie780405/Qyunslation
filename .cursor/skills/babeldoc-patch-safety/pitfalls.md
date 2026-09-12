# 踩坑（SK-Q005）

1. **`return units, fit and overflow_n == 0` + `min_scale=0.8`（PLAN-046→047 回归）** — 单行紧框（Abstract 高 7.38pt）基线本就贴框底，440 条 overflow 误判 → scale 循环耗尽 → `Unable to export` 16 条 → 摘要/目的静默消失。正解：overflow 不折 fit；容差 0.5×字号；min_scale 回 0.12；pdf_creater unicode 兜底。
2. **证据链**：`PdfParagraph(box=Box(x=42.57,y=363.21,x2=82.64,y2=370.59), composition=[], scale=None, optimal_scale=0.8)` 正是原文 Abstract 标题框。
3. **三表 COLUMN_CLUSTER_DRIFT / OVERFLOW 全拦、无 `.tbltr.pdf`** — BabelDOC 已把表格当段落翻完，跳过只交付 9 种字号的乱表。正解：literature OVERFLOW 软化 + `pdf_table_normalize`。
