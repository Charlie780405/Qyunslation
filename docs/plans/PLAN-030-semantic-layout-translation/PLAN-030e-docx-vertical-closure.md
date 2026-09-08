# PLAN-030e 子计划：DOCX 纵向闭环与前序缺口收拢

**状态**：已完成  
**依赖**：PLAN-030c（语义扫描）、PLAN-030d（PDF 纵向闭环）  
**验收门**：`bash scripts/verify-plan-030e.sh`

## 一、目标

1. 收拢 030a–030d 执行缺口：LibreOffice 环境、仓外样本可配置与 BLOCKED 上报、契约字段贯通、030d 文档同步。
2. 打通 DOCX 纵向闭环：`DocxStructureScanner` → `ManifestStore` → `DocxWorkflow`/`DocxTranslator` 执行对账与状态回写。
3. 单元格级表格建模、结构校验门（非像素 diff）。

## 二、交付摘要

| 组 | 任务 | 状态 |
| --- | --- | --- |
| A | Task 1 LibreOffice 安装脚本 + 真实 `.doc` 集成测试（skip 若未安装） | 完成 |
| A | Task 2 `QYUNSLATION_SAMPLE_ROOT` + verify 门 BLOCKED | 完成 |
| A | Task 3 PLAN-030d 验收勾选同步 + WT-030d 契约字段登记 | 完成 |
| B | Task 4 schema 1.1.0：`bbox` 对流式 SECTION 可选 | 完成 |
| B | Task 5 `translatable_blocks` 贯通（DOCX + PDF） | 完成 |
| B | Task 6 `output_evidence` 贯通（PDF + DOCX 执行侧） | 完成 |
| C | Task 7 `scan_docx.py` + `docx_walk.py` | 完成 |
| C | Task 8 表格单元格级 `row_count`/`column_count`/blocks | 完成 |
| C | Task 9 `DocxWorkflow` 消费 manifest 并回写 | 完成 |
| C | Task 10 扩展 `review.docx` 夹具 | 完成 |
| C | Task 11 `verify-plan-030e.sh` + WT-030e | 完成 |

## 三、关键文件

- [`qyunslation/structure/scan_docx.py`](../../qyunslation/structure/scan_docx.py)
- [`qyunslation/structure/docx_walk.py`](../../qyunslation/structure/docx_walk.py)
- [`qyunslation/structure/execution_evidence.py`](../../qyunslation/structure/execution_evidence.py)
- [`qyunslation/workflow/docx_workflow.py`](../../qyunslation/workflow/docx_workflow.py)
- [`tests/structure/sample_paths.py`](../../tests/structure/sample_paths.py)
- [`scripts/verify-plan-030e.sh`](../../scripts/verify-plan-030e.sh)
- [`scripts/install-libreoffice.sh`](../../scripts/install-libreoffice.sh)

## 四、验收

```bash
bash scripts/verify-plan-030e.sh
```

- 结构套件：275 passed，1 skipped（LibreOffice），1 xfail（`QY030-PPT-001`）。
- 028 / 029 / 030c / 030d 门回归 PASS。

## 五、非目标（仍归属后续阶段）

- PDF 表格单元格级重建（另立项）
- PPTX 嵌图对象（030g）
- 跨格式语义对账（030g 之后）
- 像素级视觉 diff（本阶段采用结构断言）

## 六、环境说明

生产机若未安装 LibreOffice，legacy `.doc`/`.ppt` 规范化仍 fail-closed（HTTP 503）。服务器请装 **nogui 栈**（勿混装 GUI 与 nogui，会 apt 冲突）：

```bash
bash scripts/install-libreoffice.sh
# 等价：sudo apt-get install libreoffice-core-nogui libreoffice-writer-nogui libreoffice-impress-nogui
```

Walkthrough：[`WT-030e-docx-vertical-closure.md`](../../walkthroughs/WT-030e-docx-vertical-closure.md)
