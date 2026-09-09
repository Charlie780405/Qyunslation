# PLAN-033g：执行契约与模型溯源

> 状态：**已实现，门禁待总验收**
> 父计划：[PLAN-033](./PLAN-033-pdf-fidelity.md)
> 验收门：`bash scripts/verify-plan-033g.sh`
> 前置：无

## 目标

把“检测正确”和“执行完成”拆开。Manifest 必须能表达块级角色、翻译策略、源样式和终态证据；成功结果不得残留 `PENDING`。每个翻译任务记录最终解析后的 `model_id` 与去凭据 endpoint。

## 实现边界

改：

- `qyunslation/structure/models.py`
- `docs/contracts/document-structure-manifest-v1.schema.json`
- `qyunslation/structure/scan_pdf.py`（producer `1.5.0`）
- `qyunslation/structure/execution_evidence.py`
- 任务配置解析与 Manifest `extensions.model_trace`
- 历史门禁里写死的扫描器 `1.4.0` 断言（改为 `1.5.0`，否则 033a/033b 假红）

不改：

- BabelDOC 参考文献消费（033h）
- 表格单元格提取与翻译（033i/033j）
- 图片 fitter（033k）
- `glossaries/auto-proper-nouns.csv`

## 接口 / Manifest 变化

- `CURRENT_SCHEMA_VERSION`：`1.1.0` → `1.2.0`。`SUPPORTED_SCHEMA_MAJOR` 仍为 `1`，旧 1.x 缓存可读；扫描器版本变化由 `ManifestStore.get_current` 失效。
- `PDF_STRUCTURE_SCANNER_VERSION`：`1.4.0` → `1.5.0`。
- `TranslatableBlock` 增加：
  - `role`：`heading | body | caption | table_title | table_header | table_group | table_cell | table_footnote | figure_title | figure_label | figure_body | figure_footnote | reference`
  - `translation_policy`：`TRANSLATE | PRESERVE | PROTECT_TOKENS`
  - `source_style`：字体、字号、字重、斜体、对齐、旋转、书写方向
  - 表格：`row_index`、`column_index`、`row_span`、`column_span`
- `OutputEvidence` 增加块级执行证据：`detection`、`queued`、`translated`、`laid_out`、`validated`、`qc`、`final_font_size`、`final_font_weight`、`output_bbox`
- 成功结果禁止 `PENDING`：`DocumentStructureManifest` 在 `extensions.terminal=true` 或执行快照 `kind=execution` 时，任一对象仍为 `PENDING` 则校验失败。
- `extensions.model_trace`：`{model_id, endpoint}`，endpoint 去 query/userinfo/Authorization；禁止写 API Key。

## 失败策略

| 情况 | 动作 |
| --- | --- |
| 旧 1.x Manifest 缺新字段 | 读取兼容，字段默认 `None` / 空 |
| 执行快照含 PENDING | 校验失败，不得标 TRANSLATED |
| model_trace 含 key/token | 校验失败 |
| 前端 localStorage 覆盖默认模型 | 以最终解析值为准并写入 model_trace |

## 验收

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | schema / scanner 版本 | `1.2.0` / `1.5.0` |
| V2 | 1.1.0 最小 Manifest 仍能 `model_validate` | 通过 |
| V3 | 块字段与 source_style 契约测试 | 通过 |
| V4 | 执行快照含 PENDING 被拒绝 | 通过 |
| V5 | model_trace 记录去凭据 endpoint，拒绝 API Key | 通过 |
| V6 | `verify-plan-033g.sh` | `SUMMARY: PASS fail=0` |
