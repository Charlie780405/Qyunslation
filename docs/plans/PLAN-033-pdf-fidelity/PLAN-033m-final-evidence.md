# PLAN-033m：终态证据与未关缺口收口

> 状态：**已验收（未合 main）**
> 父计划：[PLAN-033](./PLAN-033-pdf-fidelity.md)
> 验收门：`bash scripts/verify-plan-033m.sh`；样本终态 `inspect_final()`
> 分支：`feat/PLAN-033m-final-evidence`
> 产物目录：`/tmp/plan033m-<HEAD>/`（禁止旧 `/tmp/plan033-staging` 冒充）

## 目标

1. 用当前 HEAD 重跑 11 页样本全管线，对照原始失败项。
2. 诚实总门：查输出 PDF，不只查源计数/Manifest 元数据。
3. tbltr/imgtr 失败不得吞异常；execution 必须 `terminal=true`；GUI 绑定 `model_trace`；Appendix 复位参考文献区。

## 不做什么

- 改术语 CSV、样本入库、Camelot、030h D1–D5
- 用旧 staging 或单元绿代替样本终态

## 验收

| # | 预期 |
| --- | --- |
| V1 | `verify-plan-033m.sh` PASS |
| V2 | HEAD 绑定 mono/dual 存在，否则 BLOCKED |
| V3 | `inspect_final` 对输出 PDF 做表题/CJK/参考文献/粗体/双语左侧探针；Table 1–4 网格不得塌缩，表区须有可搜索中文 |
| V4 | GUI 无「表格写出跳过」软吞；有 `bind_task_model_trace` |
