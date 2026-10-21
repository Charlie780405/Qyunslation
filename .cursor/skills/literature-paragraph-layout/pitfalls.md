# 踩坑（SK-Q006）

1. **绝对字号差 ≤0.3 合并失败（PLAN-046b）** — 摘要三段 4.0/8.0/7.6pt 合并不了。正解：相对差 ≤35% 或任一段 <5pt（047d）。
2. **只做纵向合并漏掉横向孤字** — `of` 在 x=540 同行外挂。正解：Pass 2 同行横向孤字合并。
3. **Lay summary「没左对齐」实为段间空洞** — 译文段 y 差 25/24/35pt，源为均匀 11pt；中文少一行空白留框底。正解：按译文行数收缩 + 段间距归一。
4. **项目符号段是好基准** — 「本研究增加了什么？」每段一框、行数相当，左边缘齐无空洞；用其 line_skip/align/indent 作 literature 默认。
5. **Introduction 首字下沉（大写 A）与正文叠字（MG-K10）** — 首字母 `A` 是独立大字号一行，后面 `topic` 等小字跟在它旁边；BabelDOC 把「大字 + 小字」当公式/下标，译文里留下未翻译碎片并与首字叠在一起。正解：翻译前 `pdf_dropcap.normalize_dropcaps` 用几何配对找到首字下沉，**改内容流 `Tm`**（不要 redact 再插回——会跑到阅读顺序末尾）把它规整成正文字号；翻译后 `finish_dropcaps` 把对应中文首字/词加粗放大（`QYUNSLATION_DROPCAP_ZH_SCALE`，默认 1.4），并在 dual 里还原左半原文。边车 `source/dropcaps.json` 记录每个首字位置。开关 `QYUNSLATION_FIX_DROPCAP=0`。**判据**：Introduction 无孤立 `topic`，中文首字更大更粗，dual 左半仍是原版大写 A。
6. **探测首字下沉不能靠「同一行」** — `A` 常自成一行；要用几何：大字号单字 + 右侧/下方紧邻的小字号行。
