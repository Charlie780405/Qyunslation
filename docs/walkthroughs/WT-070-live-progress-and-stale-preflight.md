# WT-070：翻译实时进度与过期预检状态修复

## 范围

本切片解决两个工作台问题：

1. 翻译任务只显示“翻译中”，用户无法看到当前动作。
2. 删除最后一个任务后，页面仍保留旧预检卡片，再次点击开始会收到 `preflight not found`。

## 实现

- PDF runner 从受控 CLI/Rich 输出提取安全的阶段文案，例如“正在解析 PDF 结构”“正在翻译段落”“正在处理版式”，无法可靠计算总百分比时保持不确定进度，不伪造百分比。
- `/api/v1/translation-runs` 增加 `progress_message` 投影；已有 `progress`、`stage` 和轮询机制保持兼容。
- Vue 工作台在上传区和任务卡显示实时动作、确定/不确定进度条、五阶段状态和 `aria-live` 更新。
- 删除当前预检对应的最后一个任务后清空本地预检卡片；创建任务遇到 `preflight not found` 时要求重新预检。

## 证据

- Commits：`bce4fdb feat: surface live translation progress`、`ea49614 fix: prevent duplicate active translation starts`
- 推送：`origin/main` 成功。
- 前端：`npm --prefix frontend run type-check` 通过；`npm --prefix frontend run build` 通过。
- 重点测试：17 passed。
- PLAN-066 相关回归：176 passed，8 个既有 Alembic deprecation warnings。
- 部署后：`qyunslation-office.service` active；本地 `/api/v1/health` 返回 `db: ok`；公网 `/next/workbench` 和 `/api/v1/health` 返回 200；未认证 `/api/v1/me` 返回 401。
- 公网静态资源已包含 `翻译实时进度`、`progress_message`、`is-indeterminate` 和 `预检记录已失效`。
- 追加部署后，当前预检对应的活动任务按钮显示“翻译进行中”并禁用，防止重复创建。

## 验收边界

- 浏览器视觉、控制台和 axe 全流程仍为 BLOCKED：当前环境没有可用的隔离 Chrome DevTools MCP，不能把 HTTP/构建证据冒充浏览器验收。
- 本切片未直接替用户启动完整 PDF 重试；真实执行仍由任务卡轮询，扫描 PDF 会沿用已部署的 OCR fallback。

## 回滚

回滚入口只需恢复 sidecar 到 `21041ca` 并重新构建静态资源；本切片无数据库迁移，任务和预检数据无需回滚。
