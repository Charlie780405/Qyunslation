# PLAN-045c：IL span 消毒与叠印检测

> 状态：已完成
> 父计划：[PLAN-045](./PLAN-045-literature-pdf-fidelity.md)

## 交付

1. `qyunslation/structure/text_sanitize.py`：剥 `<span>` / `style=id:N`；`IL_MARKUP_LEAK` / `SOURCE_OVERLAY`。
2. `scripts/apply-pdf2zh-045c-sanitize.py` 钩入 `post_translate_paragraph`；`pdf2zh.service` ExecStartPre。
3. 叠印默认 WARN；`QYUNSLATION_PLAN045_STRICT=1` 硬失败。

## 验收

- `tests/structure/test_plan045_sanitize.py`
- 补丁二次运行幂等
