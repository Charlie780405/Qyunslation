# PLAN-078d：服务端检索、分页与单条管理（P1）

> 状态：未实施 · 依赖：078a · 工作量：5–7 人日 · 对应问题：T1–T3、T5–T7、O4（列表部分）

## 目标

超过 100 条历史任务时仍能准确检索和管理。列表区分加载中、没有任务、筛选无结果、加载失败四种状态。改名可靠且支持多标签页。按版本归组。权限按动作在服务端执行。

## 任务

### d1 列表接口

- **内容**：`GET /translation-runs` 新增以下参数：
  - `q`：匹配显示名、原文件名、任务 ID 前缀，不区分大小写；
  - `lifecycle`（可多选）、`format`、`direction`、`domain`、`created_from/to`、`archived=active|archived|all`；
  - `sort=created|updated|name`，`order`；
  - `cursor` 与 `page_size`（不超过 100）。
  
  返回 `items`、`next_cursor`、`total`（筛选后总数）和 `facets`（各 lifecycle 计数，供待办条使用）。旧参数 `status/include_archived` 兼容一个版本周期。
- **性能**：列表投影改为只读的轻量版本，不调用 `_refresh_translation_run`，不逐行算门禁；门禁计数由 078b 持久化在 run 上。按 `(created_at, id)` 做 keyset 分页；新增索引 `(tenant_id, archived_at, created_at)`；PG 对 `display_name/source_filename` 建 `pg_trgm` 索引，SQLite 回退到 LIKE。
- **数据**：迁移 `078d0001`，`translation_run_record.source_filename` 冗余列并从预检回填，使检索不依赖预检是否还存在。
- **验收**：A5；250 条任务下列表 P95 小于 300ms（本地 PG 测量并记录）。
- **工作量**：2 人日

### d2 版本归组

- **内容**：列表默认每条版本链只显示最新版本（链由 `revision_of_run_id`/同一预检的 generation 构成），行内显示“v2 / 共 2 版”；详情页提供版本切换。被取代的版本只读，可以下载已批准的旧正式稿，并标明“已被 v2 取代”。
- **工作量**：1 人日

### d3 改名

- **内容**：行内编辑（Enter 保存、Esc 取消），替换 `window.prompt`。去除首尾空白，长度 1–120，禁止控制字符；“恢复为原文件名”是一个显式操作（空名不再静默变成 null）。允许重名，用原文件名和日期区分。`PATCH` 要求 `If-Match: <row_version>`，过期返回 409，前端提示“该任务已在其他页面修改”并显示最新名称。
- **验收**：A9 的改名冲突；保存中、成功、失败都有反馈。
- **工作量**：0.5 人日

### d4 按动作授权（部分完成：破坏性操作已限制为提交人或管理员，见总纲 §12）

- **内容**：新增 `_authorize_run_action(session, identity, run, action)`，实现主计划 §5.2 矩阵，替代 `_run_owned` 中“审核人等于全权”的逻辑（`v1.py:1727-1740`）。`_run_owned` 只负责可见性。重试和修订版的 `actor_sub` 保持原提交人，另记 `requested_by`（`v1.py:3074`）。
- **验收**：A11；参数化测试覆盖矩阵中的每个单元格。
- **工作量**：1 人日

### d5 前端列表

- **内容**：新增 `stores/runs.js`（筛选、分页、选择状态与 URL query 同步）和 `RunListToolbar.vue`（搜索框 300ms 防抖、筛选、排序）。四种状态分别呈现：加载失败时保留上次数据并显示“可能已过期 · 重试”；筛选无结果时提供“清除筛选”。从详情返回时恢复滚动位置和焦点。行内显示状态徽章、下一步按钮和“⋯”菜单（由 `allowed_actions` 驱动）。
- **验收**：T2；vitest 覆盖四种状态与 URL 同步。
- **工作量**：1.5 人日

### d6 备注与标签评估

本期不做标签（理由见主计划 §9）。“备注”列入后续增强：如果用户反馈需要记录交付对象或批次，再加 `note` 字段（≤500 字）并纳入检索。
