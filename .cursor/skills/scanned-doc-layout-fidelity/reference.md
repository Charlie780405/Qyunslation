# 已验收页规范（会议初步意见页）

金样：`deliverables/plan-010-fidelity/letter.page2.mono.png`  
实现：`kv_reinsert.py`（译后重绘是视觉 SSOT）+ `letter_layout.py` / `doc_profiles.toml` `[letter]`。

BabelDOC 排完后仍可能串栏、缩字、截断；**以重绘结果为准**，禁止从已截断译文回填。

## 字号与字体

| 角色 | 内容 | 字号 | 字体 | 对齐 |
| --- | --- | --- | --- | --- |
| header | 美国食品与药品管理局（信头，logo 旁） | 9pt | Regular | 随 logo |
| **section** | **会议初步意见 / 引言 / 背景**（同级） | **14pt** | **NotoSansSC-Bold** | 标题居中或左齐；三者同级加粗 |
| kv | 会议信息表「标签：」「值」 | 10pt | NotoSansSC-Regular | 左列标签、右列值，行高一致 |
| body | 引言正文、背景下文 | 12pt | NotoSansSC-Regular | 同宽、同行距；禁止 Thin/微字 |
| footer | 参考编号 / Reference ID | 8.5pt | Regular | 页脚 |

- 正文字体必须用 `NotoSansSC-Regular.otf`（插入时 fontname 勿复用已嵌入的 Thin）。
- 标题必须 Bold，只加大字号不够。
- 产品名称值 `GS301` 与其它 kv 值同 10pt，禁止 `_fit_fontsize` 降到 6–8pt。

## 会议信息表

- 两列：`x_label ≈ 67`，`x_value ≈ 245`（A4）；`pack_kv_table` 后 `kv_reinsert` 按盒重绘。
- **申办方名称** 与 **监管路径** 必须分行，禁止并栏。
- 标签后的值盒（如 `351(k)…`）并入上一 kv 行，勿当 body。
- 行高约 17pt、行距约 8pt，给引言留足高度。

## 段落

- 引言 / 背景正文从 **OCR 英文全文** 译出（`_body_zh`），去汉字间空格（`问 题`→`问题`）。
- 原文未断句则译文不断开。页 2 末「The Agency sent a meeting request granted letter」与页 3「to Jiangsu on June 26…」接成一句正文。
- 页底半句不得因 `y_ratio>0.82` 标成 footer。

## 跨页

- 生产译整本。单页夹具：`letter_translate_prompt.py` + `QYUNSLATION_TRANSLATE_CONTEXT`（上页末段 + 下页首段）。
- **译文质量**走 `qwen3.6:35b-a3b`（`translate_blocks`）；**版式**仍以空白页 + `kv_reinsert` 重绘为准。生产入口 `letter_pipeline.translate_scanned_letter`（GUI `_qy_letter_reflow`）。禁止用 BabelDOC 排版当终稿。未命中 `_KNOWN_BODIES` 的段落写入 `text_zh` 后再绘。

## 问答续页（页 3 起）

| 块 | 字号 | 字体 |
| --- | --- | --- |
| 对问题的初步回复 / CMC / 非临床 / 临床 等 section | 14pt | Bold |
| 问题N，及问题下的（a）（b） | 与当页正文同号（常页 12 / 疏页 13） | Bold |
| FDA 回复及回复下的（a）（b）/续句 | 与当页正文同号 Regular（原文斜体，不粗体） | |
| PIND / 第N页 | 9pt | Regular |
| 页脚信头（英文）+ 参考编号 | 8.5pt | Regular |

金样：`deliverables/plan-010-fidelity/letter.page3.mono.png`。后续页同一套重绘，不回退模型直出 PDF。

## 版心与行距（问答续页）

中文比英文短，按英文盒原位贴会在页下留大空白。重绘按**整页版心**排，不按 OCR 盒高度。

只拉行距（上限 1.70）填不满疏页（60% 内容最多到约 68%）。字号与行距要一起分档，并保住章节比正文大 **2pt**。

| 项 | 口径 |
| --- | --- |
| 版心 | 左 67pt，右页边 36pt；正文顶 ≈118pt，底到页脚上沿（约 740pt） |
| 常页 | 12pt 估高 ≥ 版心 80%：正文 **12pt**、章节 **14pt**、行距 **1.50**、段距 **12pt** |
| 中疏 | 12pt 估高 68–80%：仍 12/14pt，行距升到 ≤1.88、段距 ≤24pt，目标占 80–88% |
| 疏页 | 12pt 估高 < 68%：正文 **13pt**、章节 **15pt**（仍 +2pt）、行距 1.58–1.88、段距 14–24pt |
| 短页 | **≤8 行**：13/15pt、行距 1.56、段距 14pt；下空白保留，禁止拉成「两行顶天立地」 |
| 密页 | 12pt 估高 > 版心：锁 12/14pt、行距 **1.38**、段距 8pt；装不下打 log，禁止丢段、禁止 `insert_textbox` 试号叠字 |

问题与回复跟当页正文同号（问题 Bold、回复 Regular）。页 2 会议表页仍以金样为准，不套这套弹性档。
