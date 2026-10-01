# PLAN-071i：历史迁移、灰度和正式切换

> 状态：**待实施**
> 父计划：[PLAN-071](./README.md)
> 依赖：[071a](./PLAN-071a-baseline-inventory.md)–[071h](./PLAN-071h-termbase-recommendation.md)

## 目标

Alembic 收口阶段事件、模型配置、质量状态、审核决定与产物类别；历史成功任务标记 `legacy_unverified`；按租户灰度启用统一流水线；用真实样本与 Chrome DevTools 证据完成切换；缺少浏览器证据则发布状态为 BLOCKED。

## 现状

- Alembic head（计划编写时）：`068f0001`；本计划预期中间迁移：`071d0001`、`071e0001`、`071g0001`。
- 历史成功任务：`status=succeeded`，但无真实 QA/审核；产物可能 `formal_export=true`。
- 灰度开关设计：`QYUNSLATION_PIPELINE=v2|legacy`（071b）；租户级策略在 admin policies（071g）。
- verify 脚本模式：`scripts/verify-plan-*.sh`（尚无 071）。
- WT 模式：`docs/walkthroughs/WT-0xx-*.md`。

## 任务

### Task 1：迁移收口与历史回填

迁移 `071i0001`（或拆分为 data migration）：

- 已有 `status=succeeded`（及等价「已交付」）任务：`quality_state=legacy_unverified`
- 原文件与产物继续可下载；UI 显示明显「旧版未验证」标识；不再称为正式审核稿
- 已有产物 `kind` 标为 `legacy`（或保留原 kind + 增加 `legacy_unverified` 标志位，二选一写进迁移注释并锁死）
- **不**批量重翻、**不**删除旧数据
- 数据库迁移保持向后兼容；降级迁移不删阶段事件/新任务（只撤销可逆 schema，数据保留策略写明）

**验收：** 升级后抽样历史行均为 `legacy_unverified`；下载仍可用；降级后再升级数据不丢。

### Task 2：新版重试入口

- `POST /api/v1/translation-runs/{runId}/retry` 扩展 `pipeline=v2`（或 query）；基于原文件创建 **新 generation** 或新 run（契约：优先同 run 新 generation，与现有 `generation` 字段对齐）
- UI：「使用新版流水线重试」仅在 `legacy_unverified` 或失败任务显示

**验收：** 重试不修改旧 generation 产物与快照；新 generation 走 DocumentPipeline。

### Task 3：灰度开关

顺序：

1. 测试租户启用统一流水线
2. 生产管理员开放
3. PDF、DOCX、PPTX、图片全部通过真实样本后，再向普通用户开放

- 回滚：只切换执行器与入口开关（`QYUNSLATION_PIPELINE=legacy` / 租户 policy），不删除阶段事件或新任务
- Gradio `:7860` **仍不退役**（另立计划）

**验收：** 策略文档 + 开关切换演练记录写入 WT；普通用户在未开放前创建仍走 legacy 或明确拒绝 v2。

### Task 4：`scripts/verify-plan-071.sh` 与 WT-071

脚本汇总：

- pytest（pipeline/persist/api/glossary/ui 契约）
- alembic upgrade/downgrade
- 真实产物跑批（七类金标子集）
- 前端 `npm test`
- Chrome DevTools 证据清单检查（登录、上传、阶段进度、预览、设置、审核、下载）——缺项则 exit non-zero 并标 BLOCKED

文档：

- `docs/walkthroughs/WT-071-translation-quality-pipeline.md`（总册）
- 可按需拆 `WT-071a`… 或在总册分节引用各子计划证据目录 `artifacts/plan071/`

DeepSeek：与 Qwen 同一金标集盲测；未达门槛只显示试验配置。

**验收：** verify 脚本在文档所述环境可运行；发布检查表全部勾选或显式 BLOCKED。

### Task 5：发布门槛最终签字

对照纲领「全局发布门槛」10 条逐条附证据链接（日志、事件行、QA 快照、审核记录、产物 sha、浏览器录屏/DevTools HAR）。

**验收：** 任一条缺真实浏览器证据 → 状态 **BLOCKED**，不得标完成。

## 数据库 / 接口变更

- `071i0001` 数据回填
- retry 接口扩展
- admin/tenant feature flag 字段（若 071g policies 已覆盖则复用）

## 测试文件

- `tests/persist/test_plan071i_legacy_backfill.py`
- `tests/api/test_plan071i_retry_v2.py`
- `tests/scripts/test_verify_plan071_smoke.py`（可只测脚本 --dry-run）

## 完成门槛

- 历史任务可见「旧版未验证」且可新版重试。
- 四类格式真实样本通过后才对普通用户开放。
- verify + WT 证据齐全；否则 BLOCKED。

## 验证命令

```bash
alembic upgrade head
pytest -q tests/persist/test_plan071i_legacy_backfill.py tests/api/test_plan071i_retry_v2.py
bash scripts/verify-plan-071.sh
```

## 不做

- 不删除历史任务/产物。
- 不批量自动重翻。
- 不退役 Gradio、不关 `:8010` sidecar。
- 不把试验 DeepSeek 配置自动升为默认。
