# WT-030e：DOCX 纵向闭环与前序缺口收拢

## 一、实现概要

### 组 A：缺口与环境

1. **LibreOffice**：新增 [`scripts/install-libreoffice.sh`](../../scripts/install-libreoffice.sh)。本机无 sudo 时尚未安装；`test_office_normalization.py::test_real_libreoffice_converts_doc_fixture_to_docx` 在缺少 `soffice` 时 skip。
2. **仓外样本**：[`tests/structure/sample_paths.py`](../../tests/structure/sample_paths.py) 统一 `QYUNSLATION_SAMPLE_ROOT` 寻址；`verify-plan-030d.sh` / `verify-plan-030e.sh` 对缺失样本报 `BLOCKED`。
3. **030d 文档**：Tasks 1–5 与 Checkpoint A/B 验收项已勾选；契约字段空置登记见下文 §四。

### 组 B：契约债

1. **schema 1.1.0**：`SemanticObjectBase.bbox` 改为 `BoundingBox | None`；SECTION 画布对象禁止携带 bbox，PAGE/SLIDE/POSTER 仍必填。JSON Schema 已重生成。
2. **`translatable_blocks`**：DOCX 自 `docx_walk` 片段构造；PDF BODY/CAPTION/FIGURE 补建文本块。
3. **`output_evidence`**：[`execution_evidence.py`](../../qyunslation/structure/execution_evidence.py) 供 `pdf_image_translate` 与 `DocxTranslator` 共用。

### 组 C：DOCX 闭环

1. **扫描器**：`DocxStructureScanner` 产出 BODY/TABLE/TEXT_BOX/CAPTION/FIGURE/IMAGE，`SourceRefKind.DOCX_PART` / `DOCX_RELATIONSHIP`。
2. **共用遍历**：`docx_walk.py` 与 `DocxTranslator._pre_translate` 同源，消除预扫描/执行分歧。
3. **执行对账**：`DocxWorkflow._structure_manifest()` 缓存 manifest；译后写 execution 审计快照。
4. **夹具**：`review.docx` 扩展页眉/页脚/文本框/第二节；catalog SHA 已更新。

## 二、验证

```bash
bash scripts/verify-plan-030e.sh
```

聚焦：

```bash
.venv/bin/python -m pytest tests/structure/test_scan_docx.py -q --no-cov
```

## 三、结构断言（非像素 diff）

译后 DOCX 与原文逐项相等：

- 节数、表格行列数、DrawingML occurrence 数、media 字节 hash
- python-docx 可重新解析

## 四、契约字段空置登记（030d 延续至 030e 后）

| 字段 | 030e 后状态 | 归属 |
| --- | --- | --- |
| `fast_fingerprint` | 仍为空 | 预留 |
| 对象级 `source_geometry` / `confidence` | 仍为空 | 预留 |
| `SourceRef.occurrence_index` | DOCX 图片已填；PDF 仍多为空 | 030f+ |
| PDF `TableObject.row_count/column_count` | 仍为空（三线表） | 另立项 |
| DOCX `TableObject.row_count/column_count` | **已填** | 030e |
| `translatable_blocks` | DOCX/PDF 已部分贯通 | 030f+ 深化 |
| `output_evidence` | 执行侧已写 checks | 030i 可观测 |

## 五、遗留

- ~~生产机运行 `bash scripts/install-libreoffice.sh`~~ → 本机已装 nogui 栈 26.2.5.2；`OFFICE_CONVERTER` / `SLIDE_RENDERER` 探针绿。
- ~~多节 DOCX 正文全挂 `section:1`~~ → **030e-fix 已关闭**：`docx_walk` 按 `sectPr` 切段；`scan_docx` 按节分配 `canvas_id`；`test_second_section_body_maps_to_section_two_canvas` 绿。
- `QY030-PPT-001` 仍为唯一 xfail（030g）。

## 六、030e-fix 短记

| 项 | 说明 |
| --- | --- |
| walk | `section_index` + `section:N/body`；页眉页脚沿用 `section:N/header.*` |
| scan | `reading_order` 按画布；缺失 canvas 记 `DOCX_SECTION_CANVAS_MISSING` |
| 计划 | [PLAN-030e-fix-section-canvas](../plans/PLAN-030-semantic-layout-translation/PLAN-030e-fix-section-canvas.md) |
