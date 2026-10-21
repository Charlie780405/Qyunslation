# 文献表行线重建（PLAN-082 S5 / 083 / 083b / 083c / 083d）

**取代**主 SKILL 里「文献默认不整区落笔」「禁止文献整区 redact+paint」的旧说法：自 PLAN-083 起，文献表在**行线重建成功**时按格落笔；**任何失败整表交回 BabelDOC**，不再叠加归一/居中。

## 路径

`run_table_figure_stage` → `translate_pdf_tables`（mono）→ 再对 dual 以 `x_min_frac=0.5` 落笔（复用译文缓存）→ `_paint_literature_rebuild`：

1. `extend_frame_to_bottom_rule`：表框延伸到三线表底线（只用于重建）。
2. `rebuild_from_page`：行线分行；三线表（只有顶/表头/底线）按文字行分行；HPD 只在 `no_row_rules` 时出网格形状，**文本永远来自文字层**。
3. `translate_table_blocks(drift_fallback_source=True)` → `_fit_uniform` → `assert_table_qc_clean`。
4. 擦除 → `paint_fitted_blocks`（中文内嵌子集字体）。
5. `output_evidence`：`literature_rebuild_painted`，或 `EXPLICITLY_SKIPPED` + `literature_rebuild_failed:<原因>`。

## 铁律

### R1 数字比对

| 项 | 内容 |
| --- | --- |
| 症状 | 日志 `TABLE_DIGIT_DRIFT:table:N:r0c1`，整表交回；列居中把表头改成别的药名 |
| 先查 | `assert_digit_tokens_preserved` 对源/译的 token；`n\u2009=\u200930`（细空格） |
| 修法 | `extract_digit_tokens` 先归一：空白、全角括号、上标数字（`m²`≡`m2`）；单格漂移用 `drift_fallback_source` 保留该格原文 |
| 判据 | `（n = 30）`≡`(n=30)`；`611 Group A`→`A组`（丢了 611）仍判漂移 |

### R2 失败无声无害

| 项 | 内容 |
| --- | --- |
| 症状 | 重建失败后表被改得更乱（列居中、字号归一又动一遍） |
| 先查 | 失败是否在擦除之前就返回；`checks.grid_source` 是否 `literature_rebuild` |
| 修法 | 重建内全部异常在擦除前捕获；normalize 兜底与 `should_center_literature_table` 都对 `literature_rebuild` 跳过 |
| 判据 | 失败表输出与 BabelDOC 原件逐字节同区 |

### R3 写死表头不可泛化

| 项 | 内容 |
| --- | --- |
| 症状 | 4 列安慰剂对照表表头被改成「曲罗芦单抗 Q2W/Q4W」；「611 Group A」→曲罗芦单抗 |
| 先查 | `header_slots_from_blob` 是否仅凭「安慰剂/Q2W」触发 |
| 修法 | 只在表头同时含曲罗芦/Tralokinumab **且** Q2W/Q4W 才套该槽 |
| 判据 | 611 表不含「曲罗芦单抗」 |

### R4 单元格策略看内容

| 项 | 内容 |
| --- | --- |
| 症状 | `3 (Moderate)`、`4 (Severe)`、`12 (SD 3.4)` 原样留英文 |
| 先查 | `is_preserve_cell("3 (Moderate)")`；译文缓存里是否**根本没有**该格（没送翻译） |
| 修法 | `_PRESERVE_CELL` 括号内只允许数值/符号：`[\d\s.,;:%–—\-+±/≥≤<>=]*` |
| 判据 | `46.1 (18.3)`、`8 (26.7%)` 保留；含字母的括号送翻译，译后 `3（中度）` |

### R5 单位角标

| 项 | 内容 |
| --- | --- |
| 症状 | `kg/m²` 显示成 `kg/m2`；或译文 `kg/m²` 被判数字漂移而退回原文 |
| 先查 | 文本层只有压平的 `m2`；digit 比对是否认 `²` |
| 修法 | `restore_unit_superscripts`：`(?<![A-Za-z0-9])([kcmμµ]?m)([23])(?![A-Za-z0-9.\-])`→`² ³`；`translate_table_blocks` 出口统一应用 |
| 判据 | `kg/m2`→`kg/m²`；`IL-2`、`M2`、`EASI-75`、`COVID-19` 不动；`⁻¹` Noto 无字形，不转 |

### R6 字号

| 项 | 内容 |
| --- | --- |
| 症状 | 单元格字号 7.5–12.5 不等；下限从不生效 |
| 先查 | `RebuildResult.font_size` 是词框高度（含行距，约 1.25×）；`blocks_to_fit` 的 role 是 `"BlockRole.TABLE_CELL"` 而 fitter 按 `table_*` 取下限 |
| 修法 | 字号取 `page.get_text("dict")` span 中位数；`_fit_uniform` 先规整 role，再整表取最小值重排；数值格按单行测量；放不下的数值列左移不越过前列文字 |
| 判据 | 一张表一个字号（611 表1=8.5，表2=10）；不低于文献下限 7pt |

### R7 浏览器里中文消失

| 项 | 内容 |
| --- | --- |
| 症状 | 浏览器查看器里表格只剩 `TEAE`、`kg`、`%`，中文全无；pymupdf 渲染正常 |
| 先查 | `page.get_fonts()`：`Song`/`china-ss`、`Helvetica`（`n/a`）= 未内嵌 |
| 修法 | 按**实际用字**用 fontTools 生成 Noto Sans SC 子集并 `insert_font`（`prepare_embedded_font` / `_page_font(page, name, text)`）；子集缺字临时补小子集；Helvetica 没有的字形（`≥`）改走 CJK |
| 判据 | 输出无 `Song`；单文件增量 <1MB；`get_text()` 能提取「任何与研究药物相关的」；「不」不被映射成 U+F967（说明用了子集而非全字库） |

### R8 格框与白底

| 项 | 内容 |
| --- | --- |
| 症状 | 白底盖掉表头线/行线；译文末列被二次缩字 |
| 修法 | 格框左缘对齐原文列，右/下缘扩到下一列/下一行起点但**不越过行线**；测量用扣掉 inset 的净宽高 |
| 判据 | 三线表三条线完整；末列同字号 |

### R9 表内标点紧凑化与表头换行

| 项 | 内容 |
| --- | --- |
| 症状 | 表头 `（ n = 30 ）` 括号偏宽；窄列 `总计（n = 93）` 在括号里折成 `总计（n` / `= 93）` |
| 先查 | 译文是否全角括号；`(n=…)` 前有没有空格（排版器只在空格处换行）；整表字号是否被表头拖低 |
| 修法 | `compact_table_punctuation`（仅 `translate_table_blocks(compact_punct=True)`，即文献重建路径）：全角括号/百分号/等号/字母数字→半角；`(n = 30)`→`(n=30)`；汉字与 `(n=…)` 之间**恰好一个空格** |
| 判据 | `总计 (n=93)` 单行；`安慰剂组` / `(n=32)` 在组名后换行（与原文 `Placebo group` / `(n = 32)` 两行一致）；表 2 保持 10pt；中文逗号、句号不动；监管表默认不启用 |
| 反例 | 把组名与 `(n=…)` 之间的空格删掉：该词无换行点，排版器只能整表缩字（实测表 2 10pt→8pt） |

### R10 表内下角标/上角标（Tmax、AUC0-τ、t1/2z、150 mg^a）

| 项 | 内容 |
| --- | --- |
| 症状 | 药代表 `Tmax, 小时`、`Cmax`、`AUC0–τ`、`t1/2z`、`Vz/F`、`Rac_Cmax` 的角标被压平成同号普通字；`150 mga` 被模型译成 `150 mg/kg` |
| 先查 | 文本层把 span 压平；`rebuild_from_page().script_pairs` 是否取到原文真实角标（小字号 + 基线偏移）；`set_script_pairs` 是否在落笔期间开启 |
| 修法 | `script_pairs_from_page`（原文真实 span）∪ 内置 PK/统计常用写法（`_DEFAULT_SCRIPT_PAIRS`）→ `split_script_runs` → `_paint_mixed` 按 0.7 倍字号、基线下移/上移绘制；**文本内容不变**（数字比对、缓存不受影响）。脚注上标（`mga`）翻译前 `strip_footnote_markers` 拿掉、译后 `restore_footnote_markers` 接回基名之后 |
| 判据 | `Cmax`→C+下标 max；`AUC0–τ`、`t1/2z`、`Vz/F`、`Rac_Cmax` 同；`Quiz`、`Hz`、`maximum` 不动；监管路径与非重建路径**默认关闭**（`set_script_pairs(None)`），`_paint_literature_rebuild` 的 `finally` 一律关 |

### R11 分组表头、深色表头底与重叠

| 项 | 内容 |
| --- | --- |
| 症状 | 带深色/灰色表头的期刊表：`SAD phase` 被拆成 `SAD` `阶段` 两格；列表头 `Pooled / placebo / (n = 8)` 被拆成三行分别翻译（`合并`、`安慰剂`）；白底盖掉深色底，文字叠在一起、被上一行遮住 |
| 先查 | `rebuild_from_page().n_header_rows`；`_dark_cell_rects`（原文深色填充格）能否推出表头下缘；表头里最上面的行是否横跨多列 |
| 修法 | 深色填充格 → `_header_bottom` 作为表头下缘；`_split_group_header`：横跨 ≥2 列的最上行是**分组行**（格框按原文词宽放宽，不挤在单列），其余各行按列合并为一格；落笔前 `snapshot_fills` 取格子下的填充色，用**同色**底，深色底配**白字**（`_ink_for`） |
| 判据 | `SAD阶段`、`MAD阶段` 各一格居于组上；`合并安慰剂组(n=8)` 一格；深色表头保留，字白、不重叠；普通白底表仍黑字白底 |

### R12 脚注不进表

| 项 | 内容 |
| --- | --- |
| 症状 | 无底线的期刊表，脚注行被当表体行拆进各列（`n (%), number and percentage` 被切成十一段），或脚注被整区擦除 |
| 先查 | `RebuildResult.table_bottom`；最后一条数值行之后有没有整宽文字行 |
| 修法 | `_cut_footnote_lines`：最后一条数据行之后的整宽行或以 `*†‡§`、`Abbreviations`、`Note` 起头的行及其后各行都切掉；`_paint_literature_rebuild` 的擦除区只到 `table_bottom`，脚注**保留 BabelDOC 自己译好的版本**，不擦不重画 |
| 判据 | 重建行里没有脚注行；脚注在输出里是完整的中文句子 |

### R13 Helvetica 字形边界

| 项 | 内容 |
| --- | --- |
| 症状 | `CM512–150 mg` 里的 en dash 显示成 `?`；`≥` 显示成 `·` |
| 修法 | `_helv_has` 只认 Latin-1（`ord<256`），en dash、弯引号、`≥` 等一律走内嵌 CJK 子集 |
| 判据 | `µ ± ² ×` 仍走 Helvetica；`– ≥ ’` 走 CJK |

### R14 表头某格整格消失（`insert_textbox` rc<0）

| 项 | 内容 |
| --- | --- |
| 症状 | 表 3 / 表 1 表头第 3 列（`MG-K10 300 mg Q4W(n=41)`）空白，其余列正常 |
| 先查 | `paint_cell` 的 `insert_textbox` 返回值；字号是否已压到下限 6pt 仍 rc<0 |
| 根因 | `insert_textbox` 放不下时**静默不画**，不抛错，也不报 `painted=False` |
| 修法 | 最后一级回退 `_draw_lines_anyway(page, inset, lines, fontname=, font_size=)`：按行 `insert_text` 硬画（宁可略溢出格框也不丢表头） |
| 判据 | 表头每列都有字；数值格 `±` 全在 |

### R15 表题（`表 1. 基线特征`）被擦掉

| 项 | 内容 |
| --- | --- |
| 症状 | 表区擦除后上方的题注文字消失 |
| 根因 | `redact_table_region` 的 pad 把 rect 上沿推进题注；PyMuPDF `apply_redactions` 对**任何与 rect 相交的字形**都删，**不看中心点**。而 `get_text("words", clip=rect)` 只返回中心在 rect 内的词——题注词不在返回里，保护逻辑形同虚设 |
| 修法 | 探测要用**向上扩大的 clip**（`rect.y0-24 … rect.y0+4`），再用词中心 `< y0` 且 `w[3] > rect.y0` 判定；rect 上沿下移到该词底边 +0.05 |
| 判据 | 擦除后 `get_text("dict")` 仍能读到 `表 1.` / `基线特征` |

### R16 深色标签条里「表 1.」变黑看不见

| 项 | 内容 |
| --- | --- |
| 症状 | 原文题注是「深色条 + 白字 `Table 1.` + 深色题名」；译文条是空的，或字黑在黑条上 |
| 根因 | BabelDOC 把整句题注按一种颜色（黑）落笔，白字标签丢色 |
| 修法 | `table_caption_fix.repair_dark_caption_label(page, origin_page, box, x_min_frac=)`：在原文页找条（`_dark_label_rect`）和标签/题名（`_source_label_and_caption`），把译文页对应的 `表 N.` 改成白字，题名保持深色。`pdf_table_translate.py` 在 `_paint_literature_rebuild` 之后调用，异常时 fail-open |
| 判据 | 条内白字 `表 1.`，右侧深色 `基线特征`；dual 右半同样 |

**R14–R16 验证**：`/tmp/qy/offline.py`（MG-K10，页 5/9，mono+dual），先用 `set -a; . ./.env; set +a` 加载环境。

## 验收（必须真实）

```bash
# 取线上一次 run 的 pre-tablebak 原件 + 真实译文缓存离线重跑
.venv/bin/python /tmp/plan083c_offline.py   # 模式见 tests/structure/test_plan083b_real_tables.py
```

- 带深色表头的样张：`/tmp/plan083d_offline.py`（CM512，第 5/6/7 页，mono+dual）；同样用真实缓存/LLM。
- 离线要用**真实译文缓存/LLM**（`/tmp/plan033m-table-zh-cache.json`），假译员会漏掉 R1/R4/R5。
- 看 mono 与 dual 第 6/8 页；在**浏览器**里打开确认中文。
- 回归：`tests/structure/test_plan083*_*.py`、`tests/structure/test_plan049_literature_leave.py`。

## 相关文件

`qyunslation/structure/table_rebuild.py` · `table_cell_policy.py` · `table_translate.py` · `table_writeback.py` · `scripts/pdf_table_translate.py` · `scripts/pdf_table_column_center.py`
