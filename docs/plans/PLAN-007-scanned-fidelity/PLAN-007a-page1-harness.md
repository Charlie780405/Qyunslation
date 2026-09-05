# PLAN-007a：第 1 页快速夹具

## Task A1 — 抽页与 OCR 缓存

- `scripts/bench-scanned-page1.sh`
- 工作目录 `/home/dev/pdf2zh/bench/007/`（不入 git）
- 默认源：`FDA responses on PIND.pdf` 第 1 页
- `page1.hpd-ocr.pdf` 缓存：存在且比 `hpd_ocr.py` 新则跳过

## Task A2 — 变体矩阵

| 变体 | flags |
| --- | --- |
| V0 | `--skip-scanned-detection` |
| V1 | + `--ocr-workaround --disable-rich-text-translate` |
| V2 | V1 + `--primary-font-family serif` |
| V3 | V2 + 007b 字号修复（重跑 OCR） |
| V4 | V3 + `--enable-json-mode-if-requested` |

必须 `--ignore-cache`。Ollama 走 OpenAI 兼容端点。

## Task A3 — baseline

`docs/perf/baseline-007a.json`：OCR/渲染字号、中文覆盖率、fallback 次数、墙钟、PNG 路径。

## 验收

- V0 复现 bug（字号 ~5–6pt，fallback > 0）
- 单变体端到端 < 3 min

## 回滚

删脚本与 `/home/dev/pdf2zh/bench/007/`。
