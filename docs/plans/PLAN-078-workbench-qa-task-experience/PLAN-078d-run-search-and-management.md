# PLAN-078d：服务端检索、分页与单条管理（P1）

> 状态：已合并并部署（`75bf54d`，见文末上线记录） · 依赖：078a · 工作量：5–7 人日 · 对应问题：T1–T3、T5–T7、O4（列表部分）

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

## 实施记录（2026-10-19）

| 任务 | 状态 | 与计划的差异 / 备注 |
| --- | --- | --- |
| d1 列表接口 | 完成 | 参数 `q`（显示名/原文件名/任务 ID 前缀，`%` `_` 已转义）、`lifecycle`（多选，逗号或重复参数）、`format`、`direction`、`domain`、`created_from/to`、`archived`、`sort`、`order`、`cursor`、`page_size`（≤100，前端用 25）、`group_versions`；返回 `items/next_cursor/total/facets/page_size`，每行带 `version_count`。生命周期用 SQL 的 CASE 表达式（与 `_run_lifecycle` 一一对应）实现筛选与计数，版本归组用 `row_number() over (partition by preflight_id order by generation desc)`，游标是 `(排序键, id)` 的 keyset，排序键相同也不会漏行或重复。列表投影不再逐行刷新：只刷新仍可能变化的行（`_needs_refresh`），门禁、QA 轮次、替代关系、版本链改为按页批量预取。旧参数 `status/include_archived` 保留兼容。**与计划不同**：没有加 `source_filename` 冗余列和 `pg_trgm` 索引——检索在预检表上做 LIKE，250 条规模下 P95 远低于目标，现有 `ix_translation_run_tenant_created` 足够；数据量到数千条再评估（届时是纯增量迁移）。 |
| d2 版本归组 | 完成 | 默认每个任务只显示最新版本，行内“v2/共 N 版”；筛选条件对所有版本匹配，再取最新的匹配版本。新增 `GET /translation-runs/{id}/versions` 返回整条版本链（含 `superseded_by`、`current`）。**未做**：详情页的版本切换控件（接口已就绪）。 |
| d3 改名 | 完成 | 行内编辑（Enter 保存、Esc 取消并回到该行）；去除首尾空白，1–120 字符，禁止控制/格式字符；空名返回 422 `NAME_REQUIRED`，超长或含控制字符 422 `NAME_INVALID`；“恢复为原文件名”是显式的 `reset_display_name`。并发保护：`name_version`（迁移 `078d0001`，`NOT NULL DEFAULT 0`），`PATCH` 带 `If-Match`（接受带引号/`W/` 形式，非法值 400），版本不符返回 409 `NAME_CONFLICT` 并带 `current_name/current_version`；前端保留用户输入、提示最新名称，需要再次保存才会覆盖。没传 `If-Match` 的旧客户端仍可改名。名称未变化不递增版本。 |
| d4 按动作授权 | 完成 | `_authorize_run_action` 复用 `allowed_actions` 的同一套规则：非提交人/管理员对写操作返回 403 `RUN_OWNER_REQUIRED`，状态不允许返回 409 `ACTION_NOT_ALLOWED_IN_STATE`。已应用到改名、归档、恢复、删除、取消/放弃；运行中的任务不能归档或删除。归档/恢复在已处于目标状态时幂等。重试和修订版的 `actor_sub` 保持原提交人，操作人记入 `settings.requested_by`（审核人重试后，任务仍归提交人，提交人看得到）。参数化测试覆盖 7 种状态 × 3 种角色 × 3 个动作。 |
| d5 前端列表 | 完成 | `stores/runs.js`（筛选、游标分页、轮询时保留已加载页、请求序号丢弃过期响应）、`RunListToolbar.vue`（300ms 防抖搜索、阶段徽章带计数、格式/归档范围/排序）。筛选写入 URL（只写与默认值不同的项），刷新、分享、后退都回到同一列表。四种状态：加载中、没有任务、筛选无结果（带“清除筛选”）、加载失败（有旧数据时保留并提示“刷新失败，下面是上次加载的内容 · 重试”）。从详情返回恢复滚动位置并聚焦原任务行。待办条在未筛选时用服务端 `facets` 计数，不再只数当前页。**未做**：独立的“⋯”菜单——行内按钮仍由 `allowed_actions` 驱动，等 078e 加入批量/回收站入口时一起整理。 |
| d6 备注与标签 | 不做 | 同计划。 |

### 验证结果

- 后端：`tests/` 全量 1504 通过、6 跳过、13 失败。13 个失败里：9 个与 078c 记录的基线一致（7 个 SQLite 迁移往返、`test_plan060_evidence`、`test_plan066_next_surface`）；3 个是 `tests/structure` 的清单 schema 版本不一致（`test_manifest_contract`、`test_manifest_store`、`test_plan059_fidelity`），这些文件和代码未改动、也不经过 API；另 1 个（`test_plan066e` 重试）是预期的行为变化——默认列表按任务归组后只显示最新版本——已把断言改为默认 1 行、`group_versions=false` 时 2 行，现已通过。新增 51 个用例（列表 15 + 改名/授权 36）。
- 前端：`vitest run` 131/131（新增 15：URL 往返、防抖、芯片筛选、无结果与空状态区分、分页追加去重、刷新失败保留数据、首次加载失败重试、版本标记、行内改名四种路径、返回时记录位置）。
- PostgreSQL（一次性容器，已销毁）：迁移 `078b0001 → 078d0001` 升级、降级、再升级通过，`name_version` 为 `integer not null default 0`。
- 性能（本地 PG，250 条任务、每个接口 40 次）：每页 25 条中位数 37ms、P95 52ms；每页 100 条 P95 65ms；搜索 P95 41ms；阶段筛选 P95 50ms；按名称排序 P95 49ms。对照：旧列表返回 100 条 P95 约 770ms。
- 未验证：真实浏览器走查（滚动恢复、焦点环）；上千条数据下的 LIKE 搜索（见 d1）。

### 上线注意

迁移 `078d0001` 只加一列（`DEFAULT 0`，无需回填），先迁移再重启服务。回滚：降级到 `078b0001` 会丢掉 `name_version`，旧代码不读该列，无副作用。新前端依赖新后端的列表响应（`next_cursor/total/facets`）；旧前端读 `items`，不受影响，但默认列表会按任务归组。

### 上线记录（2026-10-19）

发布前确认没有进行中的任务（37 个任务：30 成功、4 个此前已确认不处理的中断任务、其余为失败/取消/阻断）；备份 `/home/dev/backups/qyunslation/qyunslation-pre078de-2026-10-19.dump`（1.9MB）；合并 `75bf54d`；库从 `078b0001` 升到 `078e0001`（`078d0001`、`078e0001` 在同一次升级里依次执行，无报错）；发布脚本前后检查（迁移对齐、前端构建新鲜、代码指纹一致、路由注册）全部通过；服务 10:33 重启，页面引用的前端资源与构建产物一致，新增的列表（含回收站）、选择、批量接口未登录时返回 401（路由已注册），库中 37 个任务无变化、无任务在回收站，启动日志无错误。
