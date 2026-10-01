# PLAN-071d：持久化阶段事件与真实进度

> 状态：**已实现（浏览器证据 BLOCKED）**
> 父计划：[PLAN-071](./README.md)
> 依赖：[071b](./PLAN-071b-document-pipeline-manifest.md)（可与 071b 同波次并行，接口先定契约）

## 目标

runner 在每个阶段开始、完成、跳过、失败时写入可恢复事件；进度按真实工作单元计算；UI 阶段条、任务列表与详情页全部读取同一事件接口，删除前端硬编码推断。

## 现状

- 进度解析：`workbench/runner.py` `_PROGRESS_RE` / `_parse_progress` / `_stage_for_label`（约 29–333）；把 CLI 文本映射为 `translating`/`rendering` 百分比。
- 成功强制 100%：672–683、822–830。
- 前端硬编码五阶段：`WorkbenchPage.vue` 114–124、171–177、199–236；`stageBucket` 把 structure/table_figure/layout 等折叠进 `text`。
- 轮询：`listRuns` 2s/10s；无 events API。
- Alembic head：`068f0001`。

## 任务

### Task 1：表 `translation_stage_event`

Alembic 迁移 `071d0001`（revises `068f0001` 或当时 head）：

| 字段 | 说明 |
| --- | --- |
| `id` | PK |
| `run_id` | FK → translation_run_record |
| `generation` | 与任务 generation 对齐 |
| `sequence` | 单调递增 |
| `stage` | Stage 枚举 |
| `state` | StageState 枚举 |
| `started_at` / `finished_at` | 可空 |
| `progress` | 0–100 或 null |
| `units_done` / `units_total` | 可空 |
| `message` | 用户可读 |
| `error_code` | 稳定错误码 |
| `trace_id` | 关联日志 |

唯一约束：`(run_id, generation, sequence)`。索引：`(run_id, generation, sequence)`。

SQLAlchemy 模型写入 `persist/models.py`。

**验收：** 升级/降级迁移测试通过；约束冲突测试。

### Task 2：`pipeline/events.py`

- API：`emit_stage_start/complete/skip/fail/progress`。
- 服务重启 reconcile：比对 DB 事件与原子状态文件（runner 现有 state 文件路径），已 `completed`/`skipped` 的阶段不得重复执行。
- `generation` 隔离：写入前校验当前 generation。

**验收：** 模拟崩溃后 resume 跳过已完成阶段；错 generation 事件被拒绝。

### Task 3：进度语义

按工作单元：

| 阶段 | 分母 |
| --- | --- |
| OCR | 页面 |
| text | Manifest 文本对象 |
| table_figure | 表格+图片对象 |
| layout | 页面或幻灯片 |
| QA | 检查项 |

- 无可靠分母 → `progress=null`，UI 显示不确定进度。
- `_parse_progress` 仅映射为 **text 阶段子进度**，不得把 CLI 行直接写成全局 100% 或伪造 qa/review/export。

**验收：** 单元测试覆盖有分母/无分母；CLI 完成不等于 export 完成。

### Task 4：Events API 与前端接线（最小）

- `GET /api/v1/translation-runs/{runId}/events?after_sequence=&generation=`
- 返回有序事件；鉴权与 run 租户隔离同现有 getRun。
- 抽出 `frontend/src/next/components/StageTimeline.vue`：只渲染 events；删除 `WorkbenchPage.vue` 硬编码列表与 `stageBucket` 伪造完成。
- 列表页摘要字段可由服务端聚合「当前 stage + state」，前端不再推断「已执行 QA」。

**验收：** 契约测试 + 前端组件测试（若 vitest 尚未引入，先 API/契约测试，UI 完整改动可与 071f 合并但本任务必须删除伪造 completed）。

## 数据库 / 接口变更

- 迁移 `071d0001`
- 新接口：`GET .../events`
- `TranslationRun` 序列化可增加 `current_stage`、`current_stage_state`、`progress`（progress 允许 null）

## 测试文件

- `tests/persist/test_plan071d_stage_events.py`
- `tests/pipeline/test_events_reconcile.py`
- `tests/pipeline/test_progress_units.py`
- `tests/api/test_plan071d_events_api.py`
- `tests/ui/test_plan071d_no_hardcoded_stages.py`（读源码断言不再硬编码五步理想流为「已完成」）

## 完成门槛

- 用户可以看到 OCR、正文、表格图片、版式、QA、人工复核和导出的真实先后顺序及耗时。
- 不适用阶段显示 `skipped`，非 `completed`。
- 重启不重复执行已完成阶段。

## 验证命令

```bash
alembic upgrade head
alembic downgrade -1 && alembic upgrade head
pytest -q tests/persist/test_plan071d_stage_events.py tests/pipeline/test_events_reconcile.py \
  tests/pipeline/test_progress_units.py tests/api/test_plan071d_events_api.py \
  tests/ui/test_plan071d_no_hardcoded_stages.py
```

## 不做

- 不实现 QA 检查项本身（071e）。
- 不实现双画布预览（071f）。
- 不在本任务引入 DeepSeek。
