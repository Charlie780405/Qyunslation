# WT-038：缺口总纲收口

日期：2026-09-10  
纲领：[PLAN-038](../plans/PLAN-038-gap-closure/PLAN-038-gap-closure.md)  
登记表：[registry.md](../plans/PLAN-038-gap-closure/registry.md)

## 子计划

| 子计划 | WT | 结果 |
| --- | --- | --- |
| 038a | [WT-038a](./WT-038a-doc-status-sync.md) | 文档头对齐 |
| 038b | [WT-037](./WT-037-table-observability.md) | 037 补档 |
| 038c | [WT-038c](./WT-038c-ops-hygiene.md) | 运维卫生 |
| 038d | [WT-038d](./WT-038d-picture-tables.md) | 纯图片表 |
| 038e | [WT-038e](./WT-038e-ppt-picture-ocr.md) | PPT 嵌图 OCR |
| 038f | [WT-038f](./WT-038f-layout-weak-items.md) | 弱项/wontfix |
| 038g | [WT-038g](./WT-038g-product-polish.md) | 产品抛光收口 |

## 仍 open（允许）

- 无（能力线 G-CAP-005…009 已随 038g 关闭；PPTX 跨页续表记为 009 内 wontfix）

## 验收

```bash
bash scripts/verify-plan-038.sh
```

## 部署

| 项 | 值 |
| --- | --- |
| merge | `5d8f6dc`（038a–g → origin/main） |
| 服务 | `pdf2zh.service`、`qyunslation-office.service` |
| verify-plan-038 | PASS（含 nested 038d–g） |
