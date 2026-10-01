# PLAN-072：工作台持久化、断点续传与租户隔离

> 状态：**实施中**
> 依赖：PLAN-068（预检与任务生命周期）、PLAN-071d（阶段事件表）、PLAN-071i（灰度与 legacy 标记）

## 目标

把新工作台（`/next` Vue + `translation_run_record`）的上传、翻译、审核三条链路的断点从浏览器内存搬到服务端，实现刷新/重启后的状态恢复与阶段级续跑，并加固多租户隔离。

## 诊断摘要

| 断点 | 现状 | 072 修复 |
| --- | --- | --- |
| 预检/表单 | 前端 ref 内存，刷新清空 | 072a：GET preflights + web_preference |
| 上传 | 一次性 multipart | 072c：分片 upload_session |
| 翻译进程 | legacy 内存清空；事件表 0 行 | 072b：heartbeat + 阶段事件 + resume |
| 审核草稿 | 无 comment UI | 072d：review_draft |
| 租户 | state.json 无 tenant_id；全局 glob | 072e：定向查找 + GC |

## 不做

- 不迁移 `workbench_translation_run` 旧 Gradio 任务。
- 不改 PLAN-071 QA/审核门禁语义。
- 不动 Caddy / Gradio 退役状态。

## 子计划

| 子计划 | 目标 |
| --- | --- |
| [072a](./PLAN-072a-preflight-form-restore.md) | 预检列表恢复 + 表单偏好 |
| [072b](./PLAN-072b-stage-resume-heartbeat.md) | 阶段事件落库 + 续跑 + 心跳 |
| [072c](./PLAN-072c-chunked-upload.md) | 分片上传断点续传 |
| [072d](./PLAN-072d-review-draft.md) | 审核草稿持久化 |
| [072e](./PLAN-072e-tenant-isolation-gc.md) | 租户隔离 + 孤儿清理 |

## 数据库

迁移 `072a0001`（revises `071g0002`）：`upload_session`、`review_draft`、`heartbeat_at`/`lease_owner`。

## 验收

`bash scripts/verify-plan-072.sh` — PASS/FAIL/BLOCKED 三态；浏览器证据缺失标 BLOCKED。
