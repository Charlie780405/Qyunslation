# 踩坑（SK-Q001）

单一 SSOT；与 PLAN 正文不重复。来源标注 WT。

1. **异常字号恰好等于 `目标字号 × scale`（0.2/0.3/0.4/0.5/0.8）** → 一定是重叠区微段落，不是字体问题（WT-009 → WT-010）。
2. **恢复 `base_operations` 留 logo 会导致中英叠字**（PLAN-007 → PLAN-008）。正解是译后回插。
3. **`U+3000` 全角空格在思源字体下被映射成 `Ѵ`**，段首缩进用 BabelDOC `first_line_indent`（WT-009）。
4. **BabelDOC `Box.y` 是底边、`y2` 是顶边**，判「页顶/页底」必须换算 `(page_h - y2) / page_h`（WT-009）。
5. **封面/会议信息看似表格**（Meeting Type / Application Number / Indication）。HPD 常把多行挤进一个盒；再聚合后 BabelDOC 会串栏。必须 `split_kv_rows` + `pack_kv_table`；`kv` 禁止合并、禁止压到 6pt（WT-010）。
6. **`会议初步意见` 不是信头**。`y_ratio<0.22` 会把它标成 `header` 9pt；它与 `引言`/`背景` 同级，必须是 `section` 14pt。引言正文必须跟背景段落下文字号/行距一致（WT-010）。
7. **页底 `y_ratio>0.82` 不能单独当 footer**。跨页半句「The Agency sent a meeting request granted letter to Jiangsu on June 26…」必须与上句「该」接成一句；只对 Reference ID/附件或 `y>0.90` 的短页码行标 footer（WT-010）。
8. **章节标题要粗体**。仅调字号不够；`kv_reinsert` 用 `NotoSansSC-Bold.otf`。正文用 `NotoSansSC-Regular.otf`，fontname 勿复用已嵌入的 Thin（WT-010）。
9. **引言正文从 OCR 英文全文译**，禁止从已截断的 BabelDOC 译文回填；汉字间空格用 `_cjk_glue`（WT-010）。
10. **单页夹具没有跨页上下文**。页 2 末句接到页 3；生产必须译整本，夹具用 `QYUNSLATION_TRANSLATE_CONTEXT`（WT-010）。
11. **已验收金样** `letter.page2.mono.png` 是视觉 SSOT；改排版先对金样，规范在 `reference.md`（WT-010）。
12. **切回 qwen3.6:35b-a3b 只提升译文，不自动保版式**。模型 PDF / BabelDOC 仍会串栏缩字；必须空白页重绘。装不下时收行距，禁止丢段（WT-010）。
13. **`insert_textbox` 试号会真的落字**。12pt 装不下再试 11pt 会叠两层，下一块再叠上来。只排一次；按全角估高；用返回的剩余高度推进光标。绘完必须能在 PDF 里找回每段 `text_zh`（WT-010）。
14. **疏页只拉行距到 1.70 填不满**。12pt/1.50 占版心约 60% 时，1.70 只能到约 68%。估高 <68% 升正文 13pt、章节 15pt；68–80% 只拉行距到 1.88。少于 8 行仍不拉满（WT-010）。
