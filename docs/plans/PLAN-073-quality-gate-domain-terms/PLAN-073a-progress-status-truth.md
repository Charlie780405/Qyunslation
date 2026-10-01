# PLAN-073a：进度展示去重与状态真实化

## 交付

- 主列仅保留进度条 + 当前阶段一行摘要；完整 9 阶段时间线只在右侧 TASK FLOW。
- `displayStatus(run)`：`quality_state=qa_blocked` →「QA 拦截 N 项」；`review_ready` →「待人工复核」。
- `StageTimeline` 事件文案中文映射（`launched:pdf_cli` 等）。
- vitest 覆盖。

## 验收

- 页面仅一个完整 `StageTimeline`。
- qa_blocked 任务不显示「正在保存 PDF」为主标题。
