# PLAN-030e-fix 子计划：多节 DOCX canvas 归因

**状态**：已完成  
**类型**：030e 遗留修复（R2）  
**依赖**：PLAN-030e  
**验收门**：`bash scripts/verify-plan-030e.sh`（含本节断言）

## 一、问题

[`canvases.py`](../../../qyunslation/structure/canvases.py) 已按 `w:sectPr` 产出 `section:1`、`section:2` 等 SECTION 画布。[`scan_docx.py`](../../../qyunslation/structure/scan_docx.py) 却固定 `canvas = prepared.canvases[0]`，所有 BODY/TABLE/TEXT_BOX 都挂第一节。

页眉页脚 walk 已带 `section:{n}/header.*`；正文 walk 的 `container_ref` 一直是 `document.body`，没有节序号。

## 二、交付

| 任务 | 交付 |
| --- | --- |
| walk | `DocxWalkSegment.section_index`（1-based）；正文 `container_ref` 形如 `section:2/body`；遇含 `w:sectPr` 的段落后升到下一节 |
| scan | 按 `section_index` 取 `prepared.canvases[i-1]`；越界记 `DOCX_SECTION_CANVAS_MISSING`，不伪造 canvas |
| reading_order | 各 SECTION 画布独立填充 |
| 测试 | `review.docx` 第二节 BODY 断言 `canvas_id == "section:2"` |
| 文档 | 本计划 + [WT-030e §030e-fix](../../walkthroughs/WT-030e-docx-vertical-closure.md) |

## 三、非目标

- PDF 表格单元格重建
- schema major 变更
- 翻译写回逻辑变更
- DrawingML occurrence 按节归因（仍默认第一节；030g 前可接受）

## 四、验收

```bash
.venv/bin/python -m pytest tests/structure/test_scan_docx.py -q --no-cov
bash scripts/verify-plan-030e.sh
```

028 / 029 / 030c / 030d / 030e 门不退化；`QY030-PPT-001` 仍为唯一 xfail。
