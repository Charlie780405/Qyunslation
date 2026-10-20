# PLAN-080h：Manifest 2.0 遗留的 3 个测试失败与 schema 合同收口

> 状态：**已完成**（2026-10-20；D1 选 a 修复兼容，D2 选 a 改名 `-v2`）。结果：`tests/structure tests/pipeline tests/scripts tests/ui` 共 956 passed、6 skipped、0 failed；`scripts/verify-plan-034b.sh` PASS。
> 父计划：[PLAN-080](./PLAN-080-pdf-translation-completeness-and-typography.md)
> 来源：WT-080 §5 的全量 `tests/structure tests/pipeline` 运行：846 passed、6 skipped、3 failed。撤回 PLAN-080 的两处源码改动后，这 3 个用例仍然失败，说明它们**不是 PLAN-080 引入的**，而是更早的提交遗留。
> 为什么放在 080 下：PLAN-079 F5 清零测试基线时没有包含 `tests/structure`（慢，单独运行），所以这些失败一直没被登记。PLAN-080 的验证需要一个干净的基线，否则无法区分新旧失败。

## 1. 三个失败与根因

| # | 用例 | 现象 | 根因 | 性质 |
| --- | --- | --- | --- | --- |
| 1 | `tests/structure/test_manifest_contract.py::test_committed_json_schema_matches_model` | 已提交的 `docs/contracts/document-structure-manifest-v1.schema.json` 与 `DocumentStructureManifest.model_json_schema()` 不一致，差异在 `BlockRole` 枚举（新增 `author`、`affiliation`）与 `TranslatableBlock.review_required` 字段 | `6ce64ec`（PLAN-074，保护作者与文字伪影）给 `BlockRole` 增加了 `author`、`affiliation`，但没有重新生成已提交的 schema。另外，该文件名仍是 `-v1`，而模型的 `CURRENT_SCHEMA_VERSION` 已是 `2.0.0` | 合同文件漂移 |
| 2 | `tests/structure/test_manifest_store.py::test_schema_major_mismatch_is_treated_as_miss` | 期望 major 不符的 manifest 被视为未命中，实际命中了 | 用例把 `schema_version` 改成 `"2.0.0"` 来模拟"不符"，但 `dc2d094`（PLAN-071b，Manifest 2.0）已把 `CURRENT_SCHEMA_VERSION` 升到 `2.0.0`，于是这个值恰好是当前版本。`ManifestStore.get` 的逻辑本身是对的 | 用例过期 |
| 3 | `tests/structure/test_plan059_fidelity.py::test_ljae_semantic_counts_are_not_physical_image_counts` | `summarize_for_ui` 抛 `MANIFEST_VERSION_UNSUPPORTED` | `qyunslation/ui/manifest_view.py:58` 要求 schema major 必须等于 1，而生产里的 manifest 都是 2.0.0 | **产品缺陷**，不只是测试问题 |

### 失败 3 的实际影响

`scripts/apply-pdf2zh-050-workbench.py` 向旧 Gradio 界面注入的预扫描卡片调用 `render_prescan_card`。遇到 2.0.0 的 manifest 时，卡片降级显示"结构清单不可用（MANIFEST_VERSION_UNSUPPORTED），未用 0 填充计数"，页数、Figure、Table 等摘要全部丢失。降级是有意的（不会崩溃，也不会用 0 冒充），但 Manifest 2.0 上线后旧界面这张卡片一直是不可用状态。是否仍有用户使用旧界面不清楚，需要确认（见 §4 D1）。

## 2. 工作内容

| ID | 内容 | 验收 |
| --- | --- | --- |
| 080h-1 | 失败 2：把用例里的"不符 major"改为从 `CURRENT_SCHEMA_VERSION` 推导（如当前 major + 1），不再写死数字，避免下次升版再失效 | 用例通过；升版后无需改用例 |
| 080h-2 | 失败 1：重新生成 schema 文件，并确认差异只有 `BlockRole` 的两个新值。文件名是否从 `-v1` 改为 `-v2` 见 D2 | `test_committed_json_schema_matches_model` 通过；`git diff` 中差异只含预期字段 |
| 080h-3 | 失败 3：让 `manifest_view` 支持 major 2（读取 `summary` 与 `extensions` 的字段与 v1 是否一致需要先核对），保留对未知 major 抛 `MANIFEST_VERSION_UNSUPPORTED` 的行为；新增 major 2 与未知 major 的单元测试 | `test_ljae_semantic_counts_are_not_physical_image_counts` 通过；major 3 仍然被拒绝；预扫描卡片在 2.0.0 manifest 上显示计数 |
| 080h-4 | 在 `scripts/verify-plan-080.sh` 中加入这三个用例的显式检查，并把全量 `tests/structure tests/pipeline` 的失败数写入 WT-080 | verify 输出 PASS；WT-080 记录失败数为 0 |

估算：0.5–1 人日。

## 3. 非目标

- 不改 Manifest 2.0 的字段设计，也不改 `ManifestStore` 的未命中逻辑（逻辑是对的）。
- 不处理 `tests/structure` 之外的失败（本次运行没有发现）。
- 不为旧界面新增功能；只修复它对 2.0.0 的兼容。

## 4. 决策（待确认）

| 编号 | 问题 | 选项 | 推荐 |
| --- | --- | --- | --- |
| D1 | 旧 Gradio 预扫描卡片是否还需要保留 | a. 保留并修复兼容（推荐，改动小）；b. 确认已无人使用，则移除注入，同时删除失败 3 的用例 | **a**：先修；是否下线旧界面属于 PLAN-067 的退役范围 |
| D2 | schema 文件名是否从 `-v1` 改为 `-v2` | a. 重命名，并同步引用它的文档和测试；b. 保持文件名，在文件头注明当前 major 为 2 | **a**：文件名与内容不一致会继续误导；引用点用 `grep` 全量核对后再改 |

## 5. 风险

| 风险 | 影响 | 控制 |
| --- | --- | --- |
| 重新生成 schema 时带入与 `BlockRole` 无关的差异 | 合同被无意改动 | 重新生成前后做 `diff`，差异只允许 `BlockRole`；有其他差异先查来源提交 |
| `manifest_view` 对 v2 字段的假设不成立 | 卡片显示错误计数 | 失败 3 的用例已断言 `figure_count`、`table_count` 等；先核对 v1/v2 字段对照，再放开 major 检查，保持"不确定时不填 0" |
| 重命名 schema 文件漏掉引用 | 文档或脚本找不到文件 | 改名前 `grep -rn "document-structure-manifest-v1"`，改名后重跑 `tests/structure` |

## 6. 实施记录（2026-10-20）

| ID | 结果 |
| --- | --- |
| 080h-1 | `test_manifest_store.py`：不符的 major 改为 `CURRENT_SCHEMA_VERSION` 的 major + 1 |
| 080h-2 | schema 重新生成并 `git mv` 为 `document-structure-manifest-v2.schema.json`；差异只有 `BlockRole` 两个值和 `review_required` 字段（均来自 PLAN-074）。可执行引用（`tests/structure/test_manifest_contract.py`、`scripts/verify-plan-034b.sh`）已更新；历史计划与走查文档里的旧文件名**未改**（它们记录当时的状态）。合同文档 `document-structure-manifest-v1.md` 补写了当前模型版本为 2.0.0，并说明文件名中的 v1 是合同族名称 |
| 080h-3 | `ui/manifest_view.py` 接受 major 1 与 2（与 `SUPPORTED_SCHEMA_MAJORS` 一致），未知 major 仍抛 `MANIFEST_VERSION_UNSUPPORTED`；v2 的 summary 字段与 1.x 同名。`tests/ui/test_plan050_state_manifest.py` 中原先用 `"2.0.0"` 断言"不支持"的用例也已过期，改为 `3.0.0` 等，并新增 major 2 用例 |
| 080h-4 | **额外发现并修复**：`scripts/verify-plan-034b.sh` 把版本写死为 `1.3.0`，在 2.0.0 之后本来就失败（且合同文字更新后另一条也会失败）。改为跟随 `CURRENT_SCHEMA_VERSION`，并保留"不低于 1.3.0"的检查。verify-plan-080.sh 尚未建立，纳入 080g |
