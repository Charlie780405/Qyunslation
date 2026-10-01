# PLAN-074a：作者前置信息保护

## 交付

- [qyunslation/structure/frontmatter.py](../../../qyunslation/structure/frontmatter.py)：姓名/学位/ORCID/邮箱信号 → `AUTHOR + PRESERVE`。
- [qyunslation/structure/babeldoc_policy.py](../../../qyunslation/structure/babeldoc_policy.py)：作者块不进入 LLM/术语抽取。
- [qyunslation/pipeline/qa/pdf_inspect.py](../../../qyunslation/pipeline/qa/pdf_inspect.py)：`AUTHOR_METADATA_CHANGED` 阻断正式稿。

## 验收

`tests/structure/test_plan074_frontmatter.py`；真件作者区与源文逐字一致（见 plan074-live-regression）。
