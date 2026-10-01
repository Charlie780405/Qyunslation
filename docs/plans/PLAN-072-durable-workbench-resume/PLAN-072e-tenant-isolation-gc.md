# PLAN-072e：租户隔离加固与孤儿清理

> 状态：**实施中**
> 父计划：[README](./README.md)

## 目标

runner state 带 tenant_id；跨租户 glob 移除；孤儿磁盘目录可 dry-run 清理。

## 任务

1. `state.json` 写入 `tenant_id`；`_state_path_for_task` 按租户目录查找。
2. upload_session / review_draft 查询带 tenant 断言 + 越权测试。
3. `scripts/plan072-gc-orphans.py` dry-run / `--apply`。

## 验收

- 跨租户 preflight/run/draft 读写 404。
- GC 脚本列出无 DB 记录的 run/preflight 目录。
