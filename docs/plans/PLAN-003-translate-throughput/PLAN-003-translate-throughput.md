# PLAN-003：翻译吞吐加速（保质量）

> 状态：进行中 | 日期：2026-08-23
> 工作区：`/home/dev/qyunslation`（Vultr）

## 目标

在保住 BabelDOC 排版 + 泰州 `qwen3.6:35b-a3b` 译文质量的前提下，消除「双倍 LLM（术语+翻译）」、刷新堵车、归档漏扫，并按泰州双 5090 实测把并发调到最优。

## 父纲领进度

| 编号 | 名称 | 状态 | 备注 |
| --- | --- | --- | --- |
| 003a | 管线快赢 | 进行中 | Vultr，不改泰州 |
| 003b | Ollama 调度 | 待做 | 泰州 GPU0 |
| 003c | 任务取消 | 待做 | Gradio unload |

基线（2026-08-23）：`QX027N QnA-2026.08.19-临床.pdf` 术语 831 + 翻译 831 ≈ 26 min；`qps=2`。

## 上一子计划缺口分析（来自 PLAN-002 / 今晚运维）

| 缺口 | 归并 |
| --- | --- |
| 自动抽术语默认开，双倍 LLM | →003a |
| GUI 产物在 `pdf2zh_files/`，watcher 只扫 `out/` | →003a（已补扫，需 flock） |
| 刷新后旧任务占 GPU，新任务 queue 空转 | →003c |
| AUDIT-001 为 27b 短 prompt，不适用于 35b-a3b | →003b |
| 荃信白牌 UI | 后续独立 PLAN |

## 依赖 / 前置条件

- PLAN-002 已切流：`translate.qyunsgen.com` → `:7860`
- PLAN-002e/f：MinIO + Vault + 向量检索
- 泰州 Ollama：`http://100.67.66.123:11434`，模型 `qwen3.6:35b-a3b`
- HPD 仍在 GPU1 `:8120`，本期不动

## Out of Scope

- 换模型、双模式快速/精译、BabelDOC 嵌进 Qyunslation（AGPL）
- 改域名 / homepage href
- 动 GPU1 HPD
- vLLM 替换 Ollama（003b 未证伪前不开）

## 关键决策

| # | 决策 | 理由 |
| --- | --- | --- |
| D1 | 质量锚：35b-a3b + BabelDOC + `/no_think` | 用户确认 |
| D2 | 默认 `no_auto_extract_glossary=true` | 少一轮 831 段 LLM |
| D3 | 并发以 35b-a3b 翻译段重测为准 | AUDIT-001 不适用 |
| D4 | 最小补丁 `site-packages/gui.py`（unload），升级后重跑 apply 脚本 | 避免大 fork |
| D5 | 归档扫 `out/` + `pdf2zh_files/`，`flock` 防双写 | 今晚 DT-0002/0003 撞车 |

## 子计划

| 编号 | 文件 | 交付物 |
| --- | --- | --- |
| 003a | `PLAN-003a-pipeline-fastwin.md` | config 生效、归档 flock、烟测无 Term Extraction |
| 003b | `PLAN-003b-ollama-scheduling.md` | `baseline-003b.json`、泰州 KEEP_ALIVE/NUM_PARALLEL |
| 003c | `PLAN-003c-job-cancel.md` | `demo.unload` 取消任务 |

## SLO

- 关术语轮后同等段数墙钟降 **≥40%**
- QnA 量级（~800 段、无术语）：≤15 min（qps=2）或 ≤10 min（qps=4 若成立）
- 刷新后新任务 30s 内开始 Parse

## 验证清单

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | `bash scripts/verify-plan-003.sh` | 全部 PASS |
| V2 | 文字 PDF 翻译日志 | 无 Automatic Term Extraction |
| V3 | 译完 ≤1 min | Vault 新 `DT-*` |
| V4 | `docs/perf/baseline-003b.json` | 存在且含 concurrent 曲线 |
| V5 | 刷新后第二份 PDF | 30s 内 Parse |

## 回滚

1. Vultr：`no_auto_extract_glossary=false`，`qps=2`，去掉 unload 补丁，重启 pdf2zh
2. 泰州：去掉 `OLLAMA_NUM_PARALLEL` / `KEEP_ALIVE`，重启 ollama
3. 不回滚 Caddy

## 累积缺口登记表

| 缺口 | 状态 | 归并 |
| --- | --- | --- |
| 荃信白牌 | 未开 | 后续 |
| 手动术语表 `--glossaries` | 可选 | WT-002 遗留 |
| `--auth-file` 登录墙 | 可选 | 后续 |
