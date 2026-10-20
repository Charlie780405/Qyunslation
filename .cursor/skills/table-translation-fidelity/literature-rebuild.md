# 文献表行线重建（PLAN-082 S5 / 083 / 083b / 083c）

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

## 验收（必须真实）

```bash
# 取线上一次 run 的 pre-tablebak 原件 + 真实译文缓存离线重跑
.venv/bin/python /tmp/plan083c_offline.py   # 模式见 tests/structure/test_plan083b_real_tables.py
```

- 离线要用**真实译文缓存/LLM**（`/tmp/plan033m-table-zh-cache.json`），假译员会漏掉 R1/R4/R5。
- 看 mono 与 dual 第 6/8 页；在**浏览器**里打开确认中文。
- 回归：`tests/structure/test_plan083*_*.py`、`tests/structure/test_plan049_literature_leave.py`。

## 相关文件

`qyunslation/structure/table_rebuild.py` · `table_cell_policy.py` · `table_translate.py` · `table_writeback.py` · `scripts/pdf_table_translate.py` · `scripts/pdf_table_column_center.py`
