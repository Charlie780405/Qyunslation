# WT-071b：统一 DocumentPipeline 与 Manifest 2.0

状态：**契约与骨架已落地**（默认 `QYUNSLATION_PIPELINE=legacy`；v2 灰度）

父计划：[PLAN-071](../plans/PLAN-071-translation-quality-pipeline/README.md)  
子计划：[PLAN-071b](../plans/PLAN-071-translation-quality-pipeline/PLAN-071b-document-pipeline-manifest.md)

## 本轮交付

| 产物 | 路径 |
| --- | --- |
| DocumentPipeline | `qyunslation/pipeline/document_pipeline.py` |
| Workspace 只读原件 | `qyunslation/pipeline/workspace.py` |
| 阶段钩子 | `qyunslation/pipeline/stages/`、`events.py` |
| PDF/Office/Image 执行器 | `qyunslation/pipeline/executors/` |
| Manifest 2.0 | `structure/models.py`：`CURRENT_SCHEMA_VERSION=2.0.0`、`PreserveKind`、`reverse_index`；兼容读 1.x |
| JSON Schema | `docs/contracts/document-structure-manifest-v1.schema.json`（内容已跟模型重生） |
| API 接线 | `api/v1.py` `_launch_translation_run` / `_refresh_translation_run` |
| Runner | `workbench/runner.py`：v2 下 CLI 成功 → `layout_complete`，非 `succeeded` |

## 行为开关

| `QYUNSLATION_PIPELINE` | 行为 |
| --- | --- |
| `legacy`（默认） | 原 PDF CLI / Office 分叉；CLI 成功仍可 `succeeded`（兼容 066e 测试） |
| `v2` | 四格式进 DocumentPipeline；CLI/执行器完成 → stage=`layout`，**不**正式导出 |

## 验证

```bash
QYUNSLATION_PIPELINE=v2 python3 -m pytest -q -o addopts= \
  tests/pipeline/ \
  tests/structure/test_manifest_v2_schema.py \
  tests/api/test_plan071b_launch_formats.py \
  tests/workbench/test_plan066e_runner.py \
  tests/persist/test_plan066e_pdf_runner.py \
  tests/structure/test_manifest_contract.py
```

本环境结果：上述套件 **65 passed**（`test_manifest_store` 需 PDF_ENGINE，本机缺 pymupdf 未跑）。

## 手机续做（下一刀）

1. 分支：`cursor/plan-071-docs-b2dc`
2. 优先并行：**071c**（表格/图片/Logo 迁 stage）或 **071d**（`translation_stage_event` 持久化）
3. 071e 前不要把 `layout_complete` 再改回正式 `succeeded`
4. 有 PDF 引擎的机器补跑 `tests/structure/test_manifest_store.py`

## 不做（本轮）

- 完整 QA / 人工审核 / 水印 formal（071e）
- letter/imgtr/tbltr 细节迁移（071c）
- 前端阶段条（071d/071f）
