# PLAN-061a：保存链路与错误可诊断

> 父计划：[PLAN-061](./README.md)

- `WorkbenchTermBridgeUnavailable` 携带 `status_code` / `detail`；`_bridge_request` 区分 `HTTPStatusError`。
- `_qy060_table_confirmation` 空值与占位返回 `None`；`chosen_target` 表格与输入框谁有值谁生效。
- Timer 输出去掉 `qy060_target`，轮询保留当前选中项。
- 403/409/400/503 分文案；批准成功且筛选为「待确认」时提示已移出列表。
