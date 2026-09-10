# PLAN-030i：UI、可观测、兼容与交付收口

> 状态：**已完成**
> 日期：2026-09-10
> 批准记录：用户于 2026-09-10 批准 PLAN-030i 并一次性交付 030ia–030id
> 父计划：[PLAN-030](./PLAN-030-semantic-layout-translation.md)（已批准）
> 前置：[PLAN-030j](./PLAN-030j-layout-debt.md)（**已完成**）
> 验收门：`bash scripts/verify-plan-030i.sh`
> 验收记录：[WT-030i](../../walkthroughs/WT-030i-delivery-closure.md)

## 一、背景与缺口

030a–030j 已在仓内建立 `DocumentStructureManifest` SSOT、跨格式扫描、栏式判定与 `content_profile` 语义推断（030jd）。但用户可见层与发布层仍停留在 PLAN-008/021 时代的「文档类型模板」与分散补丁，未对齐父纲领 Checkpoint D：

| 缺口 | 现状 | 030i 目标 |
| --- | --- | --- |
| 画像选择 | GUI `doc_profile_dropdown`（书信/文献/IND）与 `content_profile` 枚举脱节 | 统一暴露 `ContentProfile` + `profile_source` + 置信度/证据摘要 |
| 处理模式 | PPTX 原生/图片化仅在 API/capabilities 层；GUI 无显式选择 | 按格式展示 `requested_mode` / `selected_mode`，不可选时解释原因 |
| 可编辑性 | manifest 有 `output_editability`，UI 未提示 | 预扫与下载区明示「可编辑 DOCX/PPTX」vs「图片化/栅格化」 |
| 可观测 | manifest 落盘于 cache，无下载入口；Tier-3 error 未进 UI | 提供 manifest JSON 下载；扫描/执行状态与 manifest 字段对账 |
| 依赖契约 | BabelDOC 补丁靠 24 条 `ExecStartPre`；033l 有部署前签名门但未纳入 030 总门 | 版本钉扎 + 启动探针 + 单命令 verify（**零 skip 假绿**） |
| 补丁供应链 | `apply-pdf2zh-*.py` 幂等但未制度化顺序/回滚 | Checkpoint D：升级后有失败门禁；回滚 playbook 可执行 |

父纲领 §Checkpoint D 四项在本计划中映射为 **030ic（依赖/verify）** 与 **030id（补丁/发布）**；**030ia/030ib** 覆盖用户可见交付。

## 二、目标

关闭 PLAN-030 最后阶段，使统一入口上的预扫描、模式选择、产物说明与部署门禁与 manifest 契约一致。

硬验收：

1. **UI 契约**：上传后展示语义摘要（Figure/Table 数、layout_mode、content_profile、profile_source）；PPTX 可选原生/图片化；图片化产物带 `output_editability=RASTERIZED` 提示。
2. **Manifest 可观测**：同一 `document.source_sha256` 的预扫 manifest 可 JSON 下载；字段与 `tests/structure` 金样断言一致。
3. **依赖 fail-fast**：Office/soffice、sidecar、核心图片解码、BabelDOC 能力在上传或任务启动前探针；缺失时 UI/API 返回可解释错误，不 silent 降级为 0。
4. **Checkpoint D 总门**：`verify-plan-030i.sh` 在空 `SAMPLE_ROOT` 下仍 PASS（blocked=0）；含 BabelDOC 补丁签名、GUI 扩展名与 capabilities 一致、versions 契约测试。
5. **发布可回滚**：补丁应用顺序文档化；`check-babeldoc-fidelity-033l.py`（或后继）失败则部署停止。

## 三、子计划矩阵

| 编号 | 名称 | 交付概要 | 关键路径（预估） |
| --- | --- | --- | --- |
| [030ia](./PLAN-030ia-ui-profile-mode.md) | UI 画像与模式 | Gradio 接入 `content_profile` 覆盖、PPTX `ProcessingMode`、可编辑性提示；与旧 `doc_profile` 桥接或 deprecate | `apply-pdf2zh-docprofile.py`、`apply-pdf2zh-prescan.py`、`qyunslation/structure/profiles.py` |
| [030ib](./PLAN-030ib-manifest-observability.md) | Manifest 可观测 | 预扫结果 JSON 下载、Tier 状态/error 展示、execution manifest 链接 | `manifest_store.py`、`doc_image_prescan.py`、`apply-pdf2zh-prescan.py`、`server/core.py` |
| [030ic](./PLAN-030ic-dependency-gates.md) | 依赖与版本契约 | `versions.lock`（或等价）、启动探针 API、verify 无 skip | `capabilities.py`、`qyunslation/structure/plan033_final.py`、新 `scripts/verify-runtime-deps.py` |
| [030id](./PLAN-030id-supply-chain-release.md) | 补丁供应链与发布 | 补丁顺序/签名总表、部署前自检串进 030i、回滚 WT、视觉金样批准清单（文档门，非全自动像素 diff） | `scripts/pdf2zh.service`、`scripts/check-babeldoc-fidelity-033l.py`、`docs/walkthroughs/WT-030i-*.md` |

**建议实施顺序**：030ic → 030ia → 030ib → 030id（先 fail-fast 与 verify 骨架，再改 UI，最后发布文档与视觉门）。

## 四、验证清单（编码后）

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | `compileall` 030i 触及的 Python 模块 | 通过 |
| V2 | `pytest tests/structure/test_gui_extension_manifest.py` | 全绿；补丁脚本扩展名仍等于 capabilities |
| V3 | 新增 `tests/structure/test_plan030i_*.py`（UI 契约、manifest 下载、探针 fail-closed） | 全绿，0 xfail |
| V4 | `bash scripts/verify-plan-030i.sh` | PASS；`SAMPLE_ROOT=/tmp/empty` 时 blocked=0 |
| V5 | `bash scripts/verify-plan-030h.sh` | 回归 PASS |
| V6 | `python scripts/check-babeldoc-fidelity-033l.py` | exit 0（生产 venv） |
| V7 | 手工：上传 ljae439.pdf → 预扫显示 5 Figure / 3 Table；下载 manifest 可对账 | 与 030c 金样一致 |

## 五、Out of Scope

- [PLAN-030-table](./PLAN-030-table-pdf-cell-reconstruction.md) Camelot 选型（Task 0 未过）
- PLAN-034（暂停至 030i 收口策略明确）
- 全自动像素级视觉 diff 全集（Checkpoint D 保留**人工批准**视觉金样清单；可记录路径/hash，不做 CI 全量渲染对比）
- `CONDITIONAL` 格式（SVG/GIF/HEIF/AVIF）进 GUI 文件选择器（仍由运行时探针决定，见 030h Out of Scope）
- 033 父纲领新功能（033 已关闭；030i 只**制度化**既有 BabelDOC 补丁，不扩 033 范围）
- 新文件格式或新 content_profile 枚举值

## 六、风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 旧 `doc_profile` 与 `content_profile` 双轨 | 030ia 明确映射表；manifest 只认 `content_profile`；旧下拉过渡期写 ADR |
| Gradio 补丁 fragile | 延续 marker 幂等 + `test_gui_extension_manifest`；030i verify 含 patch marker 检查 |
| verify 依赖本机 GUI 路径 | 探针测试 mock 或使用 `QYUNSLATION_*` 覆盖；文档写清 dev/prod 差异 |
| 视觉金样阻塞发布 | 030id 只要求清单与批准记录；未批准项列 INFO 不 block merge |

## 七、回滚

1. 代码：`git revert` 030i merge commit；`verify-plan-030h.sh` 仍为回归门。
2. GUI 补丁：各 `apply-pdf2zh-*.py` 支持重复执行；回滚版本后重跑 service `ExecStartPre` 链。
3. BabelDOC：保留 033l 签名检查；不匹配则停止部署而非半补丁状态上线。

## 八、批准门

用户于对话中明确「批准 PLAN-030i」或「开 030ia」后，方可：

1. 创建 `scripts/verify-plan-030i.sh` 骨架（允许首版部分步骤 `SKIP` 仅存在于骨架 PR，**合并前须清零 SKIP**）；
2. 开 feature 分支并按 030ia→030id 顺序编码；
3. 每完成一子计划更新对应 WT 片段，030i 全部完成后写 [WT-030i](../../walkthroughs/WT-030i-delivery-closure.md)。

---

**子计划索引**

- [PLAN-030ia UI 画像与模式](./PLAN-030ia-ui-profile-mode.md)
- [PLAN-030ib Manifest 可观测](./PLAN-030ib-manifest-observability.md)
- [PLAN-030ic 依赖与版本契约](./PLAN-030ic-dependency-gates.md)
- [PLAN-030id 补丁供应链与发布](./PLAN-030id-supply-chain-release.md)
