# PLAN-007d：译文回退治理（think=False / 转义 / 批量）

## Task D1 — 保留原生 Ollama（修正）

页 1 夹具证明：`OpenAICompatible` → `/v1` 时 qwen3.6 把答案放进 `message.reasoning`，`content` 为空 → `Expecting value: line 1 column 1` → 全量 fallback。

原生 Ollama API + `think=False` 返回正常 JSON 正文。

生产保持：

- `ollama = true`，`enabled_services = "Ollama"`
- `apply-pdf2zh-throughput.py` 给 `client.chat(..., think=False)`

## Task D2 — 不做 json_object mode

Ollama `response_format=json_object` 与 BabelDOC「JSON 数组」不兼容（V4 Successful:0）。

## Task D3 — 转义净化 + 缩小批量

- `hpd_ocr._clean_ocr_text` 剥离 `\`（避免 `Invalid \escape`）
- `pdf2zh.service`：`PDF2ZH_LLM_BATCH_PARAS=3`、`PDF2ZH_LLM_BATCH_TOKENS=120`

## 验收

- V5（pdf2zh_next --ollama + think=False）fallback 下降、中文覆盖率上升
- `grep think=False ollama.py`

## 回滚

去掉 `think=False` 补丁；恢复默认批量。
