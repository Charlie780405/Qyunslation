# WT-072：工作台持久化、断点续传与租户隔离

> 状态：**工程闭环；浏览器证据 BLOCKED**

## 执行摘要

PLAN-072 将新工作台的上传、翻译、审核断点从浏览器内存迁到服务端：预检/表单可恢复、分片上传可续传、运行中阶段事件落库、中断任务可续跑、审核草稿持久化，并加固租户隔离。

## 变更明细

| 区域 | 交付 |
| --- | --- |
| 072a | `GET /api/v1/preflights`；`web_preference.workbench`；`stores/workbench.js` |
| 072b | `heartbeat_at`/`lease_owner`；`stage_persist`；`POST .../resume`；runner reconcile → `interrupted` |
| 072c | `upload_session` + 分片 PATCH；前端 `uploadPreflightResumable` |
| 072d | `review_draft` + GET/PUT；RunDetail 审核意见自动保存 |
| 072e | `state.json.tenant_id`；定向 state 查找；`plan072-gc-orphans.py` |

## 验证

```bash
bash scripts/verify-plan-072.sh
# 2026-10-01：SUMMARY: BLOCKED fail=0 blocked=1（无 Chrome 手测）
```

- 迁移：`tests/persist/test_plan072_migration.py` — PASS
- API：`tests/api/test_plan072_resume.py` — PASS（6/6）
- 前端 vitest — PASS（21/21）

## 发布门禁

| 项 | 结果 |
| --- | --- |
| Alembic 072a0001 | PASS（SQLite 回归） |
| 分片上传 sha256 | PASS（API 测试） |
| 续跑跳过已完成阶段 | PASS（resume + pending_stages 接线） |
| 刷新恢复预检/草稿 | BLOCKED（无 Chrome 手测） |
| 跨租户隔离 | PASS（upload session 404） |

## 已知限制

- Legacy Office/图片 executor 仍主要在进程内存；PDF CLI 与 v2 pipeline 优先获得续跑能力。
- 浏览器刷新后无法恢复 `<input type=file>` 本地路径；需重新选文件或走 upload_session 续传。

## 不做

- 不迁移 `workbench_translation_run` 旧 Gradio 任务。
- 不改 PLAN-071 QA/审核门禁语义。
