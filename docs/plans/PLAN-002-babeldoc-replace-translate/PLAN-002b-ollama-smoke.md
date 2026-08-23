# PLAN-002b：原生 Ollama + warmup + 样张烟测

> 父纲领：`PLAN-002-babeldoc-replace-translate.md`
> 状态：已完成 | 2026-08-23

## 目标

让旁路 WebUI 用泰州 Ollama **原生 API** 译 1 页 PDF，证明 BabelDOC 排版链路通，再允许进入切流。

## 上一子计划缺口分析

002a 完成后填写：安装版本、磁盘占用、unit 路径。未完成项不得开本计划。

## 依赖 / 前置条件

- pdf2zh-next 原生 `Ollama` 引擎：`ollama_host` + `ollama_model`（**不要** `/v1`）
  - 源码：[OllamaSettings](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next/blob/a3efffec/pdf2zh_next/config/translate_engine_model.py)
- 现网：`http://100.67.66.123:11434`，模型 `qwen3.6:35b-a3b`
- 官方 warmup：`pdf2zh_next --warmup`
- 官方公网 GUI：`enabled_services` + `disable_gui_sensitive_input` + `disable_config_auto_save`
- 官方 Qwen：`custom_system_prompt` 含 `/no_think`
- OpenAI 兼容层 `.../v1` **仅作 B3 失败回退**，不默默切外网

## Out of Scope

- Caddy 切流、停 8010
- 全量论文、术语表 CSV 迁入

## 关键决策

| # | 决策 | 理由 |
| --- | --- | --- |
| B1 | config.toml 为 SSOT | 官方优先级 cli > env > user config |
| B2 | `qps=2`，`watermark_output_mode=no_watermark` | 对齐现网并发；内网无水印 |
| B3 | `translate_engine_type = "Ollama"` | 原生客户端，非 OpenAI 兼容层 |

## Task B1 — 探活泰州

```bash
curl -sS --max-time 8 http://100.67.66.123:11434/api/tags
```

**Acceptance：** 模型列表含 `qwen3.6:35b-a3b`。不通则停。

## Task B2 — 写 `/home/dev/pdf2zh/config.toml`

以 `~/.config/pdf2zh/default` 为底，只改：

```toml
[basic]
gui = true

[gui_settings]
enabled_services = "Ollama"
disable_gui_sensitive_input = true
disable_config_auto_save = true

[translate_engine_settings]
translate_engine_type = "Ollama"
ollama_host = "http://100.67.66.123:11434"
ollama_model = "qwen3.6:35b-a3b"

[translation]
lang_in = "en"
lang_out = "zh-CN"
qps = 2
custom_system_prompt = "/no_think You are a professional, authentic machine translation engine."

[pdf]
watermark_output_mode = "no_watermark"
```

字段名以本机默认文件为准。回退（仅 B3 失败）：`translate_engine_type = "OpenAI"` + `openai_base_url = "http://100.67.66.123:11434/v1"` + 占位 key。

## Task B3 — warmup

```bash
pdf2zh_next --warmup --config-file /home/dev/pdf2zh/config.toml
```

**Acceptance：** 退出 0。

## Task B4 — 短启 WebUI

```bash
sudo systemctl start pdf2zh.service   # 仍不 enable
curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:7860/
journalctl -u pdf2zh.service -n 30 --no-pager
```

**Acceptance：** HTTP 200；日志无连 `127.0.0.1:11434`。

## Task B5 — 1 页 CLI 烟测

```bash
pdf2zh_next /home/dev/pdf2zh/sample/page1.pdf \
  --config-file /home/dev/pdf2zh/config.toml \
  --pages 1 --ollama --output /home/dev/pdf2zh/out
```

**Acceptance：**
- [ ] `*-mono.pdf` 与 `*-dual.pdf` 非空
- [ ] 目视中文叠在原版式上
- [ ] 公网仍是 Qyunslation

**Checkpoint：** 样张路径记入附录；用户确认后再开 002c。

## 验证清单

| # | 步骤 | 预期 |
| --- | --- | --- |
| B-V1 | `bash scripts/verify-plan-002.sh after-b` | 全 PASS |
| B-V2 | 样张 PDF | mono+dual 存在且非空 |
| B-V3 | 8010 / 公网 | 未变 |

## 回滚

`systemctl stop pdf2zh.service`。保留安装与 config。

## 附录（执行记录）

| 项 | 值 |
| --- | --- |
| 样张路径 | `/home/dev/pdf2zh/sample/page1.pdf` |
| mono 输出 | `/home/dev/pdf2zh/out/page1.no_watermark.zh.mono.pdf` |
| dual 输出 | `/home/dev/pdf2zh/out/page1.no_watermark.zh.dual.pdf` |
| 引擎路径 | Ollama 原生（100.67.66.123:11434） |
