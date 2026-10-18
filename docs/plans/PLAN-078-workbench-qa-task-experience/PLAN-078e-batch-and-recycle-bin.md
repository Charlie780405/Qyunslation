# PLAN-078e：批量操作与回收站（P1）

> 状态：未实施 · 依赖：078d · 工作量：6–9 人日 · 对应问题：T4、T8

## 目标

删除可以恢复，共享的源文件和审计证据不被破坏。批量操作的范围对用户明确可见，逐项校验权限和最新状态，部分失败时如实报告，并可以重试失败项。

## 任务

### e1 回收站（软删除）

- **内容**：迁移 `078e0001`，`translation_run_record` 增加 `deleted_at, deleted_by, purge_after, purge_status(pending|done|failed), purge_error`。原 `DELETE /translation-runs/{id}` 改为移入回收站，不动文件；新增 `POST …/restore-from-trash`、`GET /translation-runs?trash=true`。回收站保留期按 D4 固定为 30 天（`QYUNSLATION_TRASH_RETENTION_DAYS`，默认 30），本期不做租户级配置界面；`purge_after = deleted_at + 30 天`，界面显示剩余天数。执行中的任务必须先由服务端确认取消成功，否则返回 409，原因为 `RUN_STILL_EXECUTING`。
- **工作量**：1.5 人日

### e2 清除任务（永久删除）（部分完成：先提交后删文件、审核决定写审计、预检引用保护已落地，见总纲 §12）

- **内容**：新增后台清除流程，管理员手动触发或到期自动执行；首个发布周期内自动清除默认关闭，只出报告。步骤：
  1. 在事务内锁定行，确认 `deleted_at` 已过期且未恢复；
  2. 计算引用：预检源文件只有在不被任何未清除的任务引用时才删；产物和运行目录（`var/translation-runs/<tenant>/<run>/<gen>`）按任务删除；
  3. 先提交数据库（行标记为 `purge_status=pending`，并写入墓碑审计：任务 ID、文件名摘要、审核决定摘要），**提交后**再删除文件；
  4. 文件删除失败时记 `purge_error`，下次重试；全部完成后删除数据库行。
  
  `ReviewDecision` 在删除行之前先以 JSON 形式写入审计日志。同时修复现有删除接口“先删文件后提交”的顺序问题（`v1.py:2296-2315`）。`plan072-gc-orphans.py` 继续作为兜底。
- **验收**：A7；在第 3、4 步之间注入异常，数据库与文件不会出现“库在文件没了”的情况。
- **工作量**：2 人日

### e3 批量接口

- **内容**：新增 `POST /translation-runs/batch`，请求体为 `{action: archive|unarchive|trash|restore_from_trash|purge, ids?: [...], selection_token?: "...", exclude_ids?: [...]}`，需带 `Idempotency-Key`。
  - `ids` 单次最多 200 个。
  - “全部筛选结果”先调用 `POST /translation-runs/selection`，按当前筛选在服务端生成快照，返回 `selection_token`、`count` 和 15 分钟有效期。这样筛选条件变化后不会误操作隐藏的任务；令牌过期返回 410，要求重新选择。
  - 每一项单独开保存点事务，按 `_authorize_run_action` 和最新状态校验（行锁），返回 `{id, outcome: succeeded|failed|skipped, reason_code, message}`。
  - 跨租户或不可见的 ID 一律报告为 `not_found`，不泄露是否存在。
  - 同一个 key 重放时返回首次结果。
- **验收**：A6、A11；并发场景下（另一个标签页正在改名或复检），批量操作逐项给出准确结果。
- **工作量**：2 人日

### e4 前端多选与操作栏

- **内容**：每行一个复选框；“全选本页”之后显示横幅“已选择本页 25 项 · [选择全部 248 条筛选结果]”；筛选、排序或页码变化时清空选择并提示。新增 `BatchActionBar.vue`（常驻底部，显示已选数量、范围和可用操作，按选中项的 `allowed_actions` 取交集，不可用的操作显示原因）。确认对话框按状态分组列出预计会被跳过的数量。结果摘要显示成功、失败、跳过的数量，可展开查看原因，并提供“重试失败项”。窄屏下操作栏固定在底部，触控目标不小于 44px。
- **验收**：A6；键盘可以完成多选和执行批量操作。
- **工作量**：1.5–2 人日

### e5 回收站视图

- **内容**：列表筛选中加入“回收站”，显示剩余保留天数，提供“恢复”和“永久清除”（仅管理员，需输入任务数量二次确认）。
- **工作量**：0.5 人日

## 兼容与回滚

旧前端调用 `DELETE` 时得到的是可恢复的删除，比原来更安全。回滚到旧版本时，`deleted_at` 非空的行在旧列表中会重新出现，这在可接受范围内；如需避免，可在回滚前把它们改为归档（提供 `scripts/plan078e-trash-to-archive.py`，带 dry-run）。
