# PLAN-029 表格译文结构化：期刊 Markdown 管道 + 幻灯 OCR 嵌字

## 问题

PLAN-028 把表格定为「文字层翻译，插图避让」。Hermes 文献入库却要求表格以 Markdown 管道表注入正文；幻灯片类则因 `find_tables` 误切条形图，只能走整页/区域截图。

本计划仅覆盖 **NEJM/Springer 期刊类** 与 **幻灯片类（16:9/4:3）**；FDA/Poster/扫描件/OUP 矢量刊能力驱动静默降级。

## 子计划

| 编号 | 文件 | 内容 |
|---|---|---|
| 029a | [PLAN-029a-journal-md-tables.md](PLAN-029a-journal-md-tables.md) | `md_tables.py` + `export_md_docx.py` 挂载 |
| 029b | [PLAN-029b-slide-ocr-profile.md](PLAN-029b-slide-ocr-profile.md) | 幻灯 profile + `pdf_image_translate` 判型 |
| 029c | [PLAN-029c-verify-delivery.md](PLAN-029c-verify-delivery.md) | `verify-plan-029.sh` + WT-029 |

## 质量红线

- 纯数值单元格不进 LLM，原样透传
- `table_status != "ok"` 一律不注入
- 幻灯 profile 严格按页门控，期刊矢量行为零变化
- 注入失败降级为原文落盘，不阻断 md/docx 导出

## 不做

- HPD 视觉解析降级（`use_hpd=True`）
- 译文 PDF 内嵌 Markdown 表
- 跨页续表合并
- FDA/MedR/Poster 结构化
