# PLAN-071e：QA、术语门禁与正式产物

> 状态：**待实施**
> 父计划：[PLAN-071](./README.md)
> 依赖：[071b](./PLAN-071b-document-pipeline-manifest.md)、[071d](./PLAN-071d-stage-events-progress.md)；版式类检查可弱依赖 [071c](./PLAN-071c-table-figure-logo-layout.md)

## 目标

落地确定性 QA、术语门禁与人工审核；自动 QA 后只生成带水印 `review_draft`；仅 reviewer 批准后才渲染无水印 `formal`；下载接口无法绕过。

## 现状

- 创建：`qa_summary={"blocker":0,"warning":0,"info":0}`，`term_summary={"status":"snapshot_pending"}`（`api/v1.py` ~881–882）。
- 下载门禁：`api/v1.py` ~1061 仅 `formal_export and run.status != "succeeded"`。
- runner 固定 `no_watermark`（`runner.py` 215）。
- 段级 QA：`POST /api/v1/qa/run` → `gateway.pipeline.run_segment_pipeline`；可置 job `qa_blocked`——未接到 TranslationRun。
- `quality/` 包是 PLAN-063 术语台账，非产物门禁。
- 角色：`reviewer` 已在 BFF 白名单（`auth/bff.py` 205–216）；`/me` capabilities 未暴露 `can_review`。

## 任务

### Task 1：QA 引擎六类检查

新建 `qyunslation/pipeline/qa/`：

| 类别 | 内容 | 默认严重级别 |
| --- | --- | --- |
| 内容完整性 | 遗漏、重复、空译文、未处理 fallback | 空译文/遗漏 → blocker；普通 fallback → warning |
| 临床与监管 | 药名、适应症、剂量、单位、日期、否定词、终点、法规引用 | 剂量/关键数字变化 → blocker |
| 术语 | 批准译名、禁用词、不得翻译、高风险冲突 | 高风险冲突 → blocker |
| 结构 | 表格行列、合并、图注、对象数量 | 关键结构破坏 → blocker |
| 布局 | 遮挡、越界、异常字号、页面漂移、Logo 缺失 | Logo/页面缺失 → blocker；轻微漂移 → warning |
| 产物一致性 | Manifest、修订版本、渲染版本、generation | 不一致 → blocker |

- 复用 `gateway.pipeline.run_segment_pipeline` 可复用规则，避免双轨。
- blocker **不允许**「接受例外」绕过，必须修复或重试。
- warning 必须由 reviewer 确认。

**验收：** 每类至少 2 个 fixture 测试；blocker 集无法标 approved。

### Task 2：表与质量状态

迁移 `071e0001`：

- `translation_run_record.quality_state`（默认 `draft`；历史回填在 071i）
- 表 `qa_item`：`run_id, generation, category, severity, code, message, object_id, evidence_json, reviewer_note, resolved`
- 表 `review_decision`：`run_id, generation, decision, user_id, created_at, qa_snapshot_id, term_snapshot, model_snapshot, comment`
- `translation_artifact.kind` 使用 `ArtifactKind`；`formal_export` 仅 `formal` 为 true

状态流转：

- QA 有 blocker → `qa_blocked`，禁止正式导出
- QA 无 blocker → `review_ready`（进度非 100%）
- approve → 触发无水印最终渲染 → 成功后 `quality_state=approved` 且 `status=succeeded/stage=export/progress=100`
- `request_changes` / `reject` 按契约回到 draft 或终止

**验收：** 迁移测试；状态机单测覆盖非法跳转。

### Task 3：水印审核稿与正式渲染

- QA 通过后：以 watermark 模式渲染 `review_draft` + 写 `qa_report` artifact。
- 批准后：重新执行无水印最终渲染生成 `formal`。
- 禁止在 text/layout 阶段就使用 `no_watermark` 作为唯一产物（修正 `runner.py` 215 行为：审核前强制水印或双产物策略写清）。

**验收：** 未批准任务存储中无（或不可下载）formal；批准后 formal sha 与 review_draft 不同（水印差异）。

### Task 4：API 与权限

- `GET /api/v1/translation-runs/{runId}/qa-items`
- `POST /api/v1/translation-runs/{runId}/review-decision` body: `{decision, comment?}`
- `/me` 增加 `can_review`（仅 reviewer/system_admin 映射策略按现有 `_identity_role` 扩展）
- 下载接口：除 `formal_export` 外，校验 `quality_state=approved`、generation/Manifest/QA 快照一致；review_draft 仅授权用户可下

**验收：** 非 reviewer 403；直接构造 download URL 无法拿到 formal。

## 数据库 / 接口变更

- 迁移 `071e0001`
- 新接口：qa-items、review-decision
- 能力：`can_review`

## 测试文件

- `tests/pipeline/qa/test_categories_*.py`
- `tests/persist/test_plan071e_quality_state.py`
- `tests/api/test_plan071e_review_gate.py`
- `tests/api/test_plan071e_download_bypass.py`

## 完成门槛

- 直接调用下载接口也无法绕过 QA 和人工批准。
- blocker 未解决不能进入 approved。
- 批准记录含用户、时间、QA/术语/模型快照。

## 验证命令

```bash
pytest -q tests/pipeline/qa/ tests/persist/test_plan071e_quality_state.py \
  tests/api/test_plan071e_review_gate.py tests/api/test_plan071e_download_bypass.py
```

## 不做

- 不实现双画布检查器 UI（071f 消费 qa-items）。
- 不实现资料等级/模型白名单（071g），但 QA 快照预留 model 字段。
- 不批量重翻历史任务（071i）。
