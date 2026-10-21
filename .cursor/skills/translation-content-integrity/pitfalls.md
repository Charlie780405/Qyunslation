# 踩坑（SK-Q007）

1. **Fallback 12 段产出「发现gs」「特罗金单抗」「每周两次（Q2W）」（PLAN-047）** — 简单翻译路径不走 glossary。正解：sanitize 强制口径 + 药名伪译表 + gs 碎片清除；verify 断言计数为 0。
2. **`_NESTED_DOSE` 只覆盖阿拉伯数字形** — 漏掉「每四周一次（每 4 周一次（Q4W））」。正解：补中文数词嵌套形。
3. **禁止把 Q2W 再展成「每2周一次（每 2 周一次（Q2W））」** — 见 SK-Q002 铁律 3b；sanitize 只塌缩不展开。
4. **「乱码阻断」但译文里肉眼没有乱码（MG-K10 文献）** — `TEXT_ENCODING_ARTIFACT` 查的是**文本层**（C0 控制符/U+FFFD），不是画面。页眉 ■、列表符号来自符号字体，ToUnicode 指向 U+0001，源 PDF 同样如此，译文原样继承。双语 PDF 同时带原文和译文两份，标记数约 2 倍。正解：`QYUNSLATION_ENCODING_INHERITANCE` 默认 `auto`——只在「仅 C0/U+FFFD、译文标记数 ≤ 源文×份数（dual 为 2）」时降为 `TEXT_ENCODING_INHERITED` 警告；mojibake、C1、新增标记仍阻断；`1` 为旧的整族重叠，`0` 关闭。**判据**：先对源 PDF 同页跑一遍同样的检测，再决定是不是我们造成的。
5. **`±` 被译成 `-`、`≥` 丢失、`©` 乱码（单位/统计符号）** — 源 PDF 的 Type1/CFF 子集符号字体（`AdvPSSymbol`、`AdvPSSym`、`AdvMathpi6`）用 WinAnsi 码位（±=150、≥=135、©=170）且 ToUnicode 映射错，字形名在子集里也不可信。BabelDOC 取 pdfminer 的 ToUnicode，于是把 `±` 当成 `-` 送去翻译。正解：翻译前 `pdf_symbol_cmap.prepare_source_pdf` 按**字体族**改写 ToUnicode（`SYMBOL_FONT_FIXES`），工作台 `start()` 在 BabelDOC 前调用；开关 `QYUNSLATION_FIX_SYMBOL_CMAP=0` 关闭。新增符号字体时只改 `SYMBOL_FONT_FIXES`，用 `--pages N` 单页验证 `≥3，以及≥1` 之类原文。**禁止**事后在译文里把 `-` 全局替回 `±`。
6. **单位校验要看符号，不只看数字** — 数值格 `45.76 ± 17.257` 若只剩 `45.76 - 17.257`，数字检查全通过却改了含义。验收时抽查表里所有 `±`、`≥`、`≤`、`×`。
7. **项目符号、页眉分隔符被报成乱码阻断（MG-K10 第 2 页）** — 符号字体里的 ■、• 没有 ToUnicode，提取出来是 `\x01` / U+FFFD，而且**独占一个词位**（前后都是空白或行首行尾，如 `\x01 MG-K10`、`第00\n\x01 卷`）。这类标记只影响复制文本，页面显示正常，不应阻断。正解：`symbol_glyph_evidence`——页上**所有** C0/U+FFFD 标记都是独占词位、且没有 C1/mojibake 时，降为警告 `TEXT_LAYER_SYMBOL_GLYPH`（已在 `registry.py` 登记，可确认已阅）。字中间的乱码（`坏\ufffd字`、`a\x07b`）一个都不放过，仍然阻断。这一条与「继承源文」（坑 4）互补：继承按「原文同页也有」判断，符号字形按「标记的形状」判断，双语页标记数翻倍也不受影响。
