# PLAN-004b：少打模型（跳过 + 静态术语 + 缓存）

## Task B1 — 跳过已是目标语

`lang_out` 为 `zh*` 且汉字占比 ≥0.8、拉丁 ≤0.15 → 不调用 LLM，原文写回。

`lang_in=zh`、`lang_out=en`：拉丁占比高（英文段）跳过，汉字段才译。

补丁：`apply-pdf2zh-throughput.py` → `il_translator_llm_only.py`。

## Task B2 — QX027 静态术语表

- 源：`DT-2026-0002/*.glossary.csv`
- 目标：`/home/dev/pdf2zh/glossaries/qx027n.csv`
- `config.toml`：`glossaries = "/home/dev/pdf2zh/glossaries/qx027n.csv"`
- **禁止** `no_auto_extract_glossary = false`

## Task B3 — 缓存命中可观测

翻译结束 journal 打一行：`cache_hit_prompt / prompt`。

验收：同一 `page1.pdf` 连译两次，第二次墙钟 **< 2 min**。

## 回滚

去掉 skip 补丁；`glossaries = "null"`。
