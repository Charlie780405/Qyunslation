# PLAN-013b Markdown / DOCX 导出

## 通道一（扫描件）

`scripts/debug2md.py`：读 `*.hpd-debug.json` → `{stem}.zh.md` / `.zh.docx`

## 通道二（普通 PDF）

`ConverterHpd`：原文 PDF → 英文 markdown（HPD → pypdf 降级）→ LLM 翻译 → md/docx。仅用户勾选格式时触发。

## 产物命名

`{stem}.zh.md` / `{stem}.zh.docx`，写入 session 目录，由 watcher 捕获。
