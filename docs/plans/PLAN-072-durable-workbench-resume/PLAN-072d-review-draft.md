# PLAN-072d：审核草稿持久化

> 状态：**实施中**
> 父计划：[README](./README.md)

## 目标

审核意见与 QA 处置状态刷新后可恢复；提交后清理草稿。

## 任务

1. `review_draft` 表（run_id + generation + user_id 唯一）。
2. GET/PUT `/translation-runs/{id}/review-draft`。
3. RunDetailPage 审核意见输入 + 防抖自动保存。

## 验收

- 刷新后 comment 与 resolved QA 勾选恢复。
- approve/request_changes 后草稿删除。
