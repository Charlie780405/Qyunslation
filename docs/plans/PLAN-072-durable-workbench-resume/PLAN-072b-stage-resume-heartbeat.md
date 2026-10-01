# PLAN-072b：阶段事件落库与任务续跑

> 状态：**实施中**
> 父计划：[README](./README.md)
> 依赖：[072a](./PLAN-072a-preflight-form-restore.md)

## 目标

运行中写入 `translation_stage_event`；服务重启后 legacy/PDF 任务可识别 `interrupted` 并阶段级续跑。

## 任务

1. runner / legacy service 周期性 `persist_buffer`。
2. `translation_run_record` 增 `heartbeat_at`、`lease_owner`。
3. `_refresh_translation_run` 心跳超时标 `interrupted`。
4. 接入 `pending_stages` / `should_skip_stage`。

## 验收

- 运行中 events 表有行。
- 重启后 translating 不永久卡住；续跑跳过已完成阶段。
