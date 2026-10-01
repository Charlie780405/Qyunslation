# PLAN-074d：乱码与 IL 标签门禁

## 交付

- [qyunslation/structure/text_sanitize.py](../../../qyunslation/structure/text_sanitize.py)：C0/C1 控制字符、`<stytle>`/`<span>` 残留、U+FFFD、mojibake 检测。
- 写回前消毒 + 成稿后 `TEXT_ENCODING_ARTIFACT` / `IL_MARKUP_LEAK` blocker（单语/双语 PDF）。
- BabelDOC 钩子 `_QY_074_POSTPROCESS`（经 apply-pdf2zh-045c-sanitize.py）。

## 验收

`tests/structure/test_plan045_sanitize.py`；`tests/pipeline/test_plan071e_pdf_inspect.py`；真件 PDF 无乱码残留。
