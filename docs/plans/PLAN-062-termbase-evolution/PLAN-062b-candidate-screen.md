# PLAN-062b：词典优先 + LLM 裁定

> 父计划：[PLAN-062](./README.md)

- 规则升 `062-v1`：删除裸 abbreviation / organization include，修 drug 碎片。
- `qyunslation/glossary/term_screen.py` 三级短路：词库 → 裁决 CSV → LLM。
- 提示词：`glossaries/prompts/term-screen.zh.md`。
