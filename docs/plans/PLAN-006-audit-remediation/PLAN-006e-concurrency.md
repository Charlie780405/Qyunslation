# PLAN-006e：并发缺陷与资源治理

- `image_overlay` → `asyncio.to_thread`
- `tasks_state` TTL 清理 + `_lock`；cacher `threading.Lock`
- 修复 `custom_api` / extensions 包导入；finally UnboundLocalError
- 裸 `except` 改为记日志
