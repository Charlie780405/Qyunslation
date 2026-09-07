# WT-029 表格译文结构化交付记录

## 问题

Hermes 文献入库要求表格以 Markdown 管道表注入正文；幻灯片类因 `find_tables` 不可靠只能截图。PLAN-028 仅计数表格为「文字层翻译」，未做结构化注入。

## 范围

- **期刊类**（NEJM/Springer）：Markdown 管道表注入 `.zh.md`
- **幻灯片类**（16:9/4:3）：OCR 嵌字破例
- **其余类型**：静默降级，保持文字层翻译

## 实现

| 组件 | 变更 |
|---|---|
| `md_tables.py` | 跨仓复用 `lit_tables` 抽表；ok 门控；非数值单元格翻译；Springer `\|` 题注回退 |
| `export_md_docx.py` | debug / HPD 两条路径写盘前注入 |
| `pdf_figure_crop.py` | 幻灯 profile 参数 + `is_slide_page` |
| `pdf_image_translate.py` | 策略 B 按页判型应用 profile |

## 标定

17 页 16:9 幻灯样本：`SLIDE_TEXT_OVERLAP=0.50`，`SLIDE_MIN_DRAWINGS=6`，表格避让关闭。矢量区域 8→12；期刊矢量仍为 12。

期刊样本 `extract_tables_pdf`：3 表仅 1 张 `ok` 可注入（符合严格门控预期）。

## 验证

```bash
bash scripts/verify-plan-029.sh
```

## 预期行为

- 期刊 `.zh.md`：ok 表题注后出现 `| col |` 管道表，数值原样保留
- 幻灯 `.imgtr.pdf`：表格区域随矢量图 OCR 嵌字覆盖
- pending/unstructured 表：不产生注入，也不报错
