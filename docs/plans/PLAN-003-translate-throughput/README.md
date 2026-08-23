# PLAN-003 翻译吞吐加速（保质量）

纲领与子计划全部在本目录。WT 在 `docs/walkthroughs/`。verify 在 `scripts/verify-plan-003.sh`。

| 文件 | 作用 |
| --- | --- |
| `PLAN-003-translate-throughput.md` | 纲领 |
| `PLAN-003a-pipeline-fastwin.md` | 关术语轮、归档会话目录、flock |
| `PLAN-003b-ollama-scheduling.md` | 泰州 GPU0 Ollama 重测与调度 |
| `PLAN-003c-job-cancel.md` | 刷新/断开即取消服务端任务 |

父纲领：PLAN-002（BabelDOC 已切流）。依赖 PLAN-002e/f（归档 + Vault 向量）。
