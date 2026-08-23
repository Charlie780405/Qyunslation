# PLAN-004c：上调 LLM 批阈值（有门禁）

## 背景

`il_translator_llm_only.process_page` 原逻辑：

```python
if total_token_count > 200 or len(paragraphs) > 5:
    executor.submit(self.translate_paragraph, ...)
```

## Task C1 — 补丁旋钮

- `total_token_count > 400`（原 200）
- `len(paragraphs) > 8`（原 5）
- 环境变量：`PDF2ZH_LLM_BATCH_TOKENS` / `PDF2ZH_LLM_BATCH_PARAS`，默认 400/8

## Task C2 — fallback 门禁

同一份 10+ 页 PDF：400/8 的 fallback 率不得 ≥ 2× 基线（200/5）。触发则回滚。

## Task C3 — QnA SLO

QX027N QnA 量级（~800 段）墙钟 **≤10 min**（门通过时）。

## 回滚

阈值改回 `200` / `5`。
