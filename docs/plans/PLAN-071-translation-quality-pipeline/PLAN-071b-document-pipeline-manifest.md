# PLAN-071b：统一文档处理服务与 Manifest

> 状态：**待实施**
> 父计划：[PLAN-071](./README.md)
> 依赖：[071a](./PLAN-071a-baseline-inventory.md)

## 目标

将 PDF、Office、图片处理统一到 `DocumentPipeline` 应用服务；执行器不再直接拼接完整业务流程。每个任务在翻译前生成版本化 Manifest，并能从产物反查到源对象。

## 现状

- Vue 台账：`qyunslation/persist/models.py` `TranslationRunRecord`（含 `manifest_version`，创建路径未赋值）。
- 新 runner 仅 PDF：`workbench/runner.py` 437；成功即 `succeeded`（672–683）。
- 非 PDF：`api/v1.py` `_launch_translation_run` 764–830 → legacy `TranslationService` / `:8010`。
- Office/图实现仍在：`workflow/docx_workflow.py`、`pptx_workflow.py`、`image_overlay_workflow.py`；`extensions/docx_image_overlay.py`、`image_translate.py`。
- Manifest：`structure/models.py` `DocumentStructureManifest` schema `1.3.0`；`structure/manifest_store.py`；扫描 `structure/scan_pdf.py`。
- 金标后处理样板：`gold/plan051_run.py` `_run_postprocess`。

## 任务

### Task 1：新建 `qyunslation/pipeline/` 包骨架

| 模块 | 职责 |
| --- | --- |
| `document_pipeline.py` | 阶段编排：validation→…→qa（本子计划先到 layout 入口；qa 由 071e） |
| `workspace.py` | 原文件只读保存；OCR/转换/翻译只操作任务工作副本 |
| `executors/pdf_cli.py` | 由 `Pdf2zhRunner` 降级为纯 CLI 执行器（无 success 终态裁定） |
| `executors/office.py` | 包装 DOCX/PPTX workflow |
| `executors/image.py` | 包装 image overlay workflow |
| `stages/` | 空骨架 + validation/structure 最小实现 |
| `__init__.py` | 导出 `DocumentPipeline` |

- `api/v1.py` `_launch_translation_run`：四种格式（pdf/docx/pptx/image）进入 `DocumentPipeline`。
- 保留 `QYUNSLATION_PIPELINE=legacy` 开关回退旧路径。
- `Pdf2zhRunner` 保留兼容壳，内部委托 `pdf_cli` 执行器；**禁止**在执行器内写 `succeeded/export/100`。

**验收：** 单元测试证明 CLI 成功只推进到 `layout`/`qa` 前一状态；legacy 开关可切回。

### Task 2：Manifest 2.0.0

在 `structure/models.py` 升级（向后兼容读 1.3.0）：

- 稳定对象 ID（跨 generation 可追溯策略写清）
- 页码或幻灯片编号
- 对象类型与边界框
- 原文、样式、层级、阅读顺序
- `preserve_kind`: `logo|seal|signature|agency_mark|none`
- 源对象哈希
- 图片/表格/Logo/印章/签名引用
- 反查索引：产物坐标/cell → 源对象 ID

格式差异：

- **PDF**：文本 PDF 结构提取 + pdf2zh_next；扫描 PDF 走 HPD OCR，启用文档画像与图形清单；letter profile；低置信度仍执行 Logo/印章/签名保护扫描。
- **DOCX/PPTX**：基于 OOXML 对象、表格单元格、文本框和 shape ID；克隆原始包后仅替换可翻译文本；媒体关系、主题、页眉页脚和 Logo 二进制不变。
- **图片**：原始图像为不可变底图；只处理已识别文字区域，保留坐标、字体和遮罩信息。

持久化沿用 `manifest_store.py`；任务记录写入 `manifest_version`。

**验收：** 四类格式都能产出一致 Manifest JSON；测试能从 mock 产物坐标反查源对象。

### Task 3：工作副本与只读原件

- 上传/preflight 路径：原件写入 content-addressed 只读存储（或 chmod/标志位）。
- 流水线每阶段读写 `workspace/run-{id}/gen-{n}/` 副本。
- 禁止执行器 `open(source, "wb")`。

**验收：** 测试断言原件 mtime/hash 在跑完后不变。

### Task 4：结构阶段与 OCR 接入点

- `structure` 阶段调用现有 scanner / OOXML 解析，写出 Manifest。
- `ocr` 阶段：复用 `scripts/hpd_ocr.py` 逻辑（先 import 薄封装，物理迁移可与 071c 合并）；不适用则 `skipped`。
- 文本 PDF 跳过 OCR 时必须写 `skipped` 事件（事件落库由 071d；本任务至少写内存/状态文件钩子）。

**验收：** 扫描样本走 OCR；文本样本 OCR=skipped；Manifest 含图形清单字段。

## 数据库 / 接口变更

- 无新表（`manifest_version` 列已存在）。
- `POST /translation-runs` 响应增加 `manifest_version`（有则返回）。
- 环境变量：`QYUNSLATION_PIPELINE=v2|legacy`（默认实施期 `legacy`，灰度见 071i）。

## 测试文件

- `tests/pipeline/test_document_pipeline_skeleton.py`
- `tests/pipeline/test_workspace_readonly_source.py`
- `tests/structure/test_manifest_v2_schema.py`
- `tests/api/test_plan071b_launch_formats.py`

## 完成门槛

- PDF、DOCX、PPTX、图片均进入同一 `DocumentPipeline` 入口。
- 四类格式都能产生一致 Manifest，并能从产物反查到源对象。
- CLI 成功不再直接 `succeeded`。

## 验证命令

```bash
QYUNSLATION_PIPELINE=v2 pytest -q tests/pipeline/ tests/structure/test_manifest_v2_schema.py tests/api/test_plan071b_launch_formats.py
```

## 不做

- 不实现完整 QA/审核（071e）。
- 不搬迁全部 letter/imgtr/tbltr 细节（071c）。
- 不改前端阶段条（071d/071f）。
- 不废弃 Gradio 服务。
