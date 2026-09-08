# PLAN-032：归档卫生（文件名清洗与编号收口）

> 状态：**已完成**
> 批准记录：用户于 2026-09-08 批准
> 日期：2026-09-08
> 关联：[PLAN-031](../PLAN-031-repo-governance/PLAN-031-repo-governance.md)（品牌收口，本计划补其漏项）
> 与 PLAN-030 关系：独立小项，可与 [PLAN-030h](../PLAN-030-semantic-layout-translation/PLAN-030h-cross-format-fidelity.md) 并行
> 验收门：`bash scripts/verify-plan-032.sh`

## 一、背景

全量测试当前为 379 passed / **3 failed**，失败全部在 `tests/test_pdf2zh_archive.py`。这 3 条从 PLAN-030a 起被历次验收门以「archive 3 个既有失败精确不变」的方式锁定为基线，从未被判定为真缺陷。

实施阶段实测修正了立项时的判断，如实记录：

- `normalize_group_stem()` 已经会剥 `.no_watermark.<lang>` 与 `.hpd-ocr`，`output_group_key("page1.no_watermark.zh.mono.pdf")` 实际返回 `page1`。三个红灯中 `test_output_group_key` 属于**测试过期**，实现是对的。
- `pdf2zh` 侧真正的缺口只有 `.imgtr` 未登记，以及 `infer_original_filename()` 对未规范化入参不设防。
- **主缺陷在 office 侧**（立项时未发现）：`scripts/office-archive-watch.py` 把译文产物名直接写成 `original_filename=path.name`，这是生产库里 `_translated.docx` 与 `.zh.jpg` 的来源。

生产库 `/home/dev/pdf2zh/archive/index.db` 已有污染记录：

| archive_id | original_filename | 污染来源 |
| --- | --- | --- |
| DT-2026-0027 | `41467_2024_Article_53384.imgtr.pdf` | `.imgtr` |
| DT-2026-0013 | `FDA responses on PIND.hpd-ocr.pdf` | `.hpd-ocr` |
| DT-2026-0023 | `方案设计图-20260728.zh.jpg` | `.zh` |
| DT-2026-0025 等 | `..._translated.docx` | `_translated` |

同时 `archive_id` 前缀仍是 `DT-`（DocuTranslate 缩写），直接显示在归档界面上——PLAN-031 品牌收口未覆盖到编号体系。

## 二、目标

1. 归档记录的「原文件名」还原为用户实际上传的文件名，不含任何中间产物后缀。
2. 归档编号前缀收口为内部品牌，且不破坏既有记录的可检索性。
3. 测试基线回到全绿，消灭「3 个既有失败精确不变」这一挡箭牌。

## 三、任务

### T1：原文件名清洗

1. 新增 `qyunslation/archive/filenames.py`，集中定义标记链并只从 stem 尾部反复剥离到稳定；未知后缀一律保留。两条归档路径共用。
2. `pdf2zh_ingest.normalize_group_stem()` 改为委托该模块（补上 `.imgtr`）；`infer_original_filename()` 入口再规范化一次，对未规范化入参幂等。
3. `office-archive-watch.py` 用 `original_filename_from_product()` 从产物名还原上传名，扩展名保留产物扩展名（`.doc` 规范化为 `.docx` 后无法反推，不猜测）。
4. `tests/test_pdf2zh_archive.py` 修正过期期望并补多层叠加、中文文件名、版本号误伤（`annual_report.v2` 不得被剥）用例。

**完成定义**：`pytest tests/test_pdf2zh_archive.py` 全绿；`output_group_key()` 分组语义不变。

### T2：编号前缀收口

1. 新记录使用 `QY-` 前缀。
2. 既有 `DT-` 记录**不做数据迁移**，检索与展示同时兼容两种前缀，避免破坏历史链接与 Vault 笔记引用。
3. 计数器逻辑不受前缀变更影响，不得出现编号重用。

**完成定义**：新归档为 `QY-2026-XXXX`；旧 `DT-` 记录仍可正常打开与检索。

### T3：存量记录处理

对生产库中已污染的 `original_filename` 提供一次性修正脚本，**默认 dry-run**，输出将要变更的记录清单供人工确认后再执行。不自动改写。

### T4：验收门

`scripts/verify-plan-032.sh`：覆盖 T1 测试、T2 前缀兼容断言、T3 脚本 dry-run 可执行；断言全量测试从 3 failed 变为 0 failed。

## 四、验证

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | `pytest tests/test_pdf2zh_archive.py -q` | 全绿 |
| V2 | `pytest tests/ -q --no-cov` | **0 failed**（原为 3 failed） |
| V3 | 上传一份文档走完整链路 | 归档编号为 `QY-`，原文件名无中间后缀 |
| V4 | 打开一条既有 `DT-` 记录 | 正常显示与下载 |
| V5 | `bash scripts/verify-plan-032.sh` | PASS |

## 五、Out of Scope

- 归档存储后端与索引 schema 变更
- Vault 导出链路（PLAN-013）与 Hermes `vault_indexer` 跨仓依赖
- 历史 `DT-` 记录的编号迁移

## 六、风险与回滚

| 风险 | 缓解 |
| --- | --- |
| 后缀剥离过度，误伤含 `.zh` 的真实文件名 | 只在 group_key 尾部按已知链剥离，保守匹配；补中文与含点文件名用例 |
| 前缀变更破坏既有 Vault 笔记引用 | 不迁移历史记录，双前缀兼容 |
| 存量修正脚本误改 | 默认 dry-run，人工确认后执行；执行前备份 `index.db` |

纯仓内改动，`git revert` 即可回滚；T3 未执行前生产数据不受影响。
