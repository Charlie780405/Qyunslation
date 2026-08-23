# WT-004b 跳过 + 术语表 + 缓存

**日期：** 2026-08-23  
**状态：** 已部署

## 变更

| 项 | 内容 |
| --- | --- |
| skip 补丁 | `il_translator_llm_only.py`：已是目标语段不送 LLM，journal 打 `skip already-target-lang count=` |
| 术语表 | `DT-2026-0002` glossary → `/home/dev/pdf2zh/glossaries/qx027n.csv` |
| config | `glossaries = "/home/dev/pdf2zh/glossaries/qx027n.csv"`；`no_auto_extract_glossary = true` 保持 |
| 缓存日志 | `gui.py` 翻译结束 `PLAN-004b cache: hit_prompt=... ratio=...` |

## 验收

- `verify-plan-004.sh after-b`：全通过
- 热缓存 &lt;2 min、QX027 混排 skip 计数：需在 GUI 连译 `page1.pdf` / QX027 QnA 时观察 journal（本 WT 未跑长文档墙钟）

## 回滚

`glossaries = "null"`；重跑 throughput 补丁前备份并去掉 skip 块。
