# 踩坑（SK-Q005）

1. **`return units, fit and overflow_n == 0` + `min_scale=0.8`（PLAN-046→047 回归）** — 单行紧框（Abstract 高 7.38pt）基线本就贴框底，440 条 overflow 误判 → scale 循环耗尽 → `Unable to export` 16 条 → 摘要/目的静默消失。正解：overflow 不折 fit；容差 0.5×字号；min_scale 回 0.12；pdf_creater unicode 兜底。
2. **证据链**：`PdfParagraph(box=Box(x=42.57,y=363.21,x2=82.64,y2=370.59), composition=[], scale=None, optimal_scale=0.8)` 正是原文 Abstract 标题框。
3. **三表 COLUMN_CLUSTER_DRIFT / OVERFLOW 全拦、无 `.tbltr.pdf`** — BabelDOC 已把表格当段落翻完，跳过只交付 9 种字号的乱表。正解：literature OVERFLOW 软化 + `pdf_table_normalize`。
4. **`is_reference_entry` 无条件保留（PLAN-080a）** — `paragraph_is_preserved` 写成 `if is_reference_heading(b) or is_reference_entry(b): return True`，`ENTRY_RE` 含 `\d+\.\s+\S+` 与 `\d{1,3}\s+[A-Z]`，于是监管信函里所有编号问题段（"2. The protocol synopsis…"）和脚注（"1 We update…"）在送 LLM 前被保留，整段英文且无日志。同一文件的 `filter_paragraphs_for_llm` 与既有测试都是"只在参考文献区内"。正解：状态门控；`[n]` 形式可无条件。
5. **机构/作者误判正文句（PLAN-080a）** — `Co., Ltd.`、`Division of`、正文里的邮箱，配上不在动词表里的句子，被判为署名/机构而保留（背景段、第 18–20 页长段）。正解：>30 词不算机构；功能词线索（this/that/the/to…）兜底；邮箱/corresponding 标记要求非正文句。
6. **`REMOVE_IF_COVERED` 删不掉零高度的描边线（PyMuPDF）** — 装饰线擦除要用 `REMOVE_IF_TOUCHED`，但"触碰即删"会连带删底纹，所以擦除矩形只能碰到线自身，否则放弃这一条。
