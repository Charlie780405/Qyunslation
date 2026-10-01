# PLAN-071a：质量基线、旧能力盘点与验收样本

> 状态：**待实施**
> 父计划：[PLAN-071](./README.md)
> 依赖：无

## 目标

在改流水线之前，固化当前错误基线、盘点 Gradio/补丁能力、建立七类金标样本与对象级期望，并定义禁止「仅以 CLI 退出码 0 判定成功」的验收矩阵。本子计划以文档与只读脚本为主，不改变用户行为。

## 现状

- FDA 扫描信样本登记于 `docs/gold/plan034/catalog.json`（`C-fda-pind` / `C-fda-pind-ocr`）；运行时会话副本常见于 `/home/dev/pdf2zh/pdf2zh_files/.../FDA responses on PIND.pdf`；测试寻址 `tests/structure/sample_paths.py`。
- 旧能力注入顺序：`docs/contracts/pdf2zh-patch-order.md`；`scripts/pdf2zh.service` ExecStartPre。
- 新 runner 成功即正式：`qyunslation/workbench/runner.py` 672–683。
- 金标后处理样板：`qyunslation/gold/plan051_run.py` `_run_postprocess` 319–354。
- BabelDOC monkey patch 打在 uv tools site-packages，CLI 是否命中未登记。

## 任务

### Task 1：固化 FDA 20 页扫描基线

- 将源文件 sha256、当前错误产物、`runner.log`、对应 `translation_run_record` 行与 artifact 元数据固化到 `artifacts/plan071/baseline/`（gitignore 大二进制；清单与哈希入库）。
- 对齐 `catalog.json` 中 `C-fda-pind` 条目；记录页数、Logo 缺失、`^{th}`、邮箱断行、地址错位等缺陷截图索引。
- 导出 DB 快照字段：`status/stage/progress/manifest_version/qa_summary/term_summary/settings_snapshot`。

**验收：** `artifacts/plan071/baseline/MANIFEST.md` 可复现定位源文件与缺陷；哈希与 catalog 一致。

### Task 2：旧能力四类盘点

产出 `docs/contracts/plan071-legacy-capability-inventory.md`，对每个钩子/补丁标注：

| 分类 | 含义 | 迁移目标示例 |
| --- | --- | --- |
| A 可迁移 | 纯应用逻辑 | `qyunslation/pipeline/stages/*` |
| B 仅界面 | Gradio DOM/事件 | 不迁；Vue 重做 |
| C 上游已覆盖 | pdf2zh_next/BabelDOC 已具备 | 验证后标记 covered |
| D 待废弃 monkey patch | 改第三方内部 | 指纹登记；071i 前评估去留 |

至少覆盖：

- `doc_profile` / letter / literature / regulatory typesetting patches（`scripts/doc_profile.py`、`apply-pdf2zh-docprofile.py`）
- HPD OCR 前置（`scripts/hpd_ocr.py`、`apply-pdf2zh-hpd.py`）
- letter 旁路重绘（`scripts/letter_pipeline.py`）
- graphic_reinsert / graphic_regions
- imgtr（`pdf_image_translate.py` → `extensions/image_translate.py`）
- tbltr（`pdf_table_translate.py` → `structure/table_*`）
- proper_nouns harvest
- office sidecar 路由（`apply-pdf2zh-office-route.py`）
- BabelDOC 补丁：042b / 046b / 047c / 047d / 033h / 045c / ocr-base / fidelity / throughput
- UI 类：brand、downloads、dual-preview、050/060 workbench chrome 等（归 B）

**验收：** 每项有源路径、分类、迁移目标模块或废弃理由；无「未知」空行。

### Task 3：CLI 补丁指纹脚本

- 新增 `scripts/plan071_patch_fingerprint.py`：探测当前 `pdf2zh_next`/BabelDOC 安装路径，检测已知补丁标记或函数钩子是否存在，输出 JSON 指纹。
- 约定指纹字段进入任务 `settings_snapshot`（由后续 071b/071d 写入）。

**验收：** 在生产同构环境跑一次，输出写入 `artifacts/plan071/baseline/patch-fingerprint.json`；单元测试覆盖标记检测逻辑。

### Task 4：七类金标与对象级期望

在 `docs/gold/plan034/catalog.json` 或新建 `docs/gold/plan071/catalog.json` 登记：

1. 文本 PDF
2. 扫描 PDF（含 FDA PIND）
3. 表格密集 PDF
4. 图片密集 PDF
5. DOCX
6. PPTX
7. 独立 PNG/JPEG

每类配套 `docs/gold/plan071/expectations/<id>.json`，至少包含：

- 页码/幻灯片数
- 段落/文本对象期望
- 表格结构（行列、合并）
- 图片、Logo、印章、签名数量与 `preserve_kind`
- 邮箱、URL、剂量、数字、监管引用（PIND/Reference ID）等原子 span 清单
- 布局基线哈希或关键 bbox 容差

二进制仍不入库；用 sha256 + `QYUNSLATION_PLAN034_GOLD_ROOT` / plan071 gold root 寻址。

**验收：** 七类均有输入登记、期望 JSON、布局基线说明。

### Task 5：验收矩阵

新增 `docs/contracts/plan071-acceptance-matrix.md`：

- 行：格式 × 场景（OCR/无 OCR、letter、表格、图片、Office、权限、模型等级）
- 列：阶段事件、Manifest 反查、QA blocker/warning、审核、正式下载、UI 进度真实性
- 明确禁止：仅以命令退出码 0 / runner `succeeded` 判定翻译成功

**验收：** 矩阵覆盖纲领「全局发布门槛」全部条目；与 WT-071 证据清单字段对齐。

## 数据库 / 接口变更

无（只读固化与文档）。

## 测试文件

- `tests/scripts/test_plan071_patch_fingerprint.py`
- 可选：`tests/gold/test_plan071_expectations_schema.py`（校验 expectation JSON schema）

## 完成门槛

- 每种格式都有输入、预期对象、布局基线和质量判定规则。
- 盘点矩阵无遗漏核心钩子；补丁指纹可复现。
- `artifacts/plan071/baseline/MANIFEST.md` 与验收矩阵已提交（大文件仅哈希）。

## 验证命令

```bash
python scripts/plan071_patch_fingerprint.py --out artifacts/plan071/baseline/patch-fingerprint.json
pytest -q tests/scripts/test_plan071_patch_fingerprint.py tests/gold/test_plan071_expectations_schema.py
```

## 不做

- 不修改 runner/API/前端行为。
- 不删除历史任务或 Gradio 补丁。
- 不把金标 PDF 二进制提交进 Git。
