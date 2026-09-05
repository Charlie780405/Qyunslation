# WT-007：扫描件一对一译文渲染

**日期：** 2026-09-05  
**状态：** 已部署（页 1 达标；全量按需）

## 背景

`FDA responses on PIND.pdf` 纯扫描件（0 文字层）。旧链路 HPD 隐形层字号塌到 5pt + 未开 `ocr_workaround` + qwen3.6 思考链弄坏 JSON → 英文栅格上叠微米级中文。

## 反转 PLAN-005a

005a 禁止 `ocr_workaround`（目标「dual 可选中」）。实测不遮盖则不可读。007c **有意反转**：扫描件目标升级为「一对一可读」。

## 变更

| 项 | 说明 |
| --- | --- |
| `scripts/hpd_ocr.py` | `_fit_fontsize`、盒高扩展、按轴缩放、剥离 `\`、debug 转储 |
| `scripts/apply-pdf2zh-hpd.py` | HPD 分支设 `ocr_workaround` + `disable_rich_text_translate` |
| `scripts/apply-pdf2zh-ocr-base.py` | ocr_workaround 时恢复 `base_operations` |
| `scripts/apply-pdf2zh-throughput.py` | Ollama `think=False`（qwen3.6 否则 content 为空） |
| `pdf2zh.service` | `PDF2ZH_LLM_BATCH_PARAS=3`、`TOKENS=120`；ExecStartPre 含 ocr-base |
| 夹具 | `scripts/bench-scanned-page1.sh` + `docs/perf/baseline-007a.json` |

## 页 1 验收（V5）

- OCR 字号中位数 ~10.8pt（原 ~5.7）
- `Successful: 14 / Fallback: 0`（原生 Ollama + think=False）
- dual 左页中文覆盖率 ~0.78（专有名词/邮箱保留英文）
- 目视：白底 + 原位中文，无英文叠字

## 已知取舍

- `ocr_workaround` 用白底盖栅格，信头 Logo 等扫描底图可能被盖住（上游设计取舍）
- babeldoc 在此模式下偶发 `Mono PDF: None`；译文在 **dual 左页**。GUI `all_mono_translations.zip` 空包同源；下载 dual 即可

## 回滚

`git revert` 相关提交；`config.toml` 保持 Ollama；去掉 `think=False` 补丁后 restart `pdf2zh.service`。
