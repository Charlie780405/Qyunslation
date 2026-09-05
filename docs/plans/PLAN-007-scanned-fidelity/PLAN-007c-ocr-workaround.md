# PLAN-007c：启用上游扫描件配方

## Task C1 — 反转 PLAN-005a 禁令

005a 禁止 `ocr_workaround` 是为「dual 可选中」保住底图。实测不遮盖则不可读。本计划升级目标为「一对一可读」，有意反转。

## Task C2 — 补丁

`scripts/apply-pdf2zh-hpd.py` 两处 HPD 分支：

```python
settings.pdf.ocr_workaround = True
settings.pdf.skip_scanned_detection = True
settings.pdf.disable_rich_text_translate = True
```

marker 判定须同时检查 `ocr_workaround`；清理死代码 `apply()`。

## Task C3 — 文字 PDF 不回归

`config.toml` 的 `ocr_workaround` 必须仍为 `false`。

## 验收

- 补丁幂等；`gui.py` 两处含 `ocr_workaround = True`
- V1 无双层叠字；文字 PDF 不劣化

## 回滚

revert + 重跑 apply 或 restart pdf2zh（ExecStartPre 重放）。
