# WT-050c：上传 / 预扫描 / 任务状态

对应 [PLAN-050c](../plans/PLAN-050-qyunslation-ui-ux/PLAN-050c-upload-preflight-task.md)

- 上传与主操作仍为左栏「翻译」（单一主操作）
- Manifest 摘要：`qyunslation.ui.manifest_view`；截断计数为 `—` 不是 0
- 预扫描 hook：`# _qy_050_prescan_card` 在有 `manifest_json` 时改写 `qy-prescan-bar`
- 状态机：`normalize_task_state`；应用栏 `#qy050-status` 映射预扫/翻译/失败
- ljae439 语义真值 5 Figure / 3 Table 由单测锁定（`test_ljae439_semantic_counts`）
