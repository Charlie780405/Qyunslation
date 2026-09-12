---
name: babeldoc-patch-safety
description: >-
  BabelDOC 补丁安全边界：fit=False 会整段不落笔、min_scale 抬高等于删字、
  跳过结构化通道不等于保留原文。
  触发：min_scale、line_skip、_layout_typesetting_units、Unable to export、
  译文整段消失、摘要丢了、apply-pdf2zh、monkey patch、pdf_creater、不落笔、
  保留英文、门禁拦下、.tbltr.pdf 没生成、PLAN-047c、PLAN-046。
---

# BabelDOC 补丁安全（SK-Q005）

## 诊断三问

1. 补丁失败时失败模式是「难看」还是「消失」？
2. BabelDOC 是否已经先于我们落笔？
3. 「跳过」之后交付的是什么——上游译文还是原文？

## 铁律

1. **`fit=False` 的失败模式是整段不落笔**（`scale=None` + `composition=[]` + `Unable to export`），不是「排得难看」。**禁止把 overflow 折进 fit 返回。**
2. **`min_scale` 只能降不能抬**——抬高等于删字。文献默认 `0.12`；最终 scale < 0.5 记 `QC_SCALE_STARVED` 但仍落笔。
3. **改 `typesetting` 模块全局（`_QY_MIN_SCALE`）必须在非 literature 作业重置**（`reset_min_scale`），否则污染下一篇。
4. **任何引擎补丁必须配 never-drop 兜底**（`apply-pdf2zh-047c-no-drop.py`），并把 `Unable to export` 计数纳入 verify。
5. **BabelDOC 先于我们落笔；我们「跳过」只是交付上游更差的版本**——要真保留原文必须阻止上游翻译该区域，否则必须做后处理归一（见 SK-Q003 / `pdf_table_normalize.py`）。

| 症状 | 先查 | 修法 | 判据 |
| --- | --- | --- | --- |
| 摘要/目的整段消失 | journalctl `Unable to export`；`optimal_scale==min_scale` | 不折 fit；min_scale=0.12；047c 兜底 | 输出含「摘要」「目的」；Unable=0 |
| overflow 数百条误判 | unit y 与 box.y 差是否 < 0.5×字号 | 容差 `max(0.5*fs, 1.0)` | overflow 警告个位数 |
| 表被门禁拦下但中文乱 | 有无 `.tbltr.pdf` | 走 `pdf_table_normalize` | 字号种类≤3 |

## 相关文件

- `scripts/doc_profile.py`（`patch_literature_typesetting` / `patch_min_scale` / `reset_min_scale`）
- `scripts/apply-pdf2zh-047c-no-drop.py`
- `scripts/doc_profiles.toml`（`[literature] min_scale`）
