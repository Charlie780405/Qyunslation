# PLAN-072a：预检与工作台表单的服务端恢复

> 状态：**实施中**
> 父计划：[README](./README.md)

## 目标

刷新后重建预检卡片与工作台表单，不再依赖 Vue 内存 ref。

## 任务

1. `GET /api/v1/preflights`：当前租户 + actor 未过期预检列表。
2. 工作台表单写入 `web_preference.workbench` 键，防抖保存。
3. `frontend/src/next/stores/workbench.js` 统一持有可恢复状态。

## 验收

- 预检完成后刷新，预检卡仍可见。
- 语言/模板/资料等级刷新后回填。
