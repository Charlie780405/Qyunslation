# WT-011：正式书信重绘接入生产

**日期：** 2026-09-05  
**状态：** 实现完成；部署结果见文末

## 做了什么

- `letter_pipeline.translate_scanned_letter`：整本跨页翻译 + 空白页重绘
- letter profile 必写 HPD debug
- GUI：letter + debug 存在则跳过 BabelDOC 终稿
- 修复 `gui.py` HPD 后错误缩进（重启前不可解析）

## 验证

见 `scripts/verify-plan-011.sh`。

## 使用

https://translate.qyunsgen.com → 上传扫描 PDF → 文档类型选「正式书信」或「自动」→ 下载 mono。

## 已知限制

- 无文字层才会走 HPD；纯文字书信仍 BabelDOC
- 译文仍依赖 `qwen3.6:35b-a3b`（`QYUNSLATION_OLLAMA_HOST`）
- 20 页书信墙钟明显长于 BabelDOC 单次（逐页 Ollama）
