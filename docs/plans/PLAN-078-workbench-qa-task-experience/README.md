# PLAN-078：翻译工作台 QA 处理闭环、参数确认与任务管理

> 状态：规划完成；快速修复已合并部署（总纲 §12）；**078a 已合并并部署**（`327bdf8`，见 078a 文末上线记录）；**078b 已合并并部署**（`a74ff7b`，见 078b 文末上线记录）；**078c 已实现，待合并与部署**（分支 `feat/plan-078c-run-confirmation`，见 078c 文末实施记录）；D1–D4 已由用户确认，见总纲 §11
> 依赖：PLAN-071（质量流水线）、PLAN-072（持久化与续跑）、PLAN-073/074/076（门禁与术语）、PLAN-077（顶栏合同）

| 文件 | 内容 | 优先级 | 工作量（人日） |
| --- | --- | --- | --- |
| [PLAN-078-workbench-qa-task-experience.md](./PLAN-078-workbench-qa-task-experience.md) | 总纲：调查结论、问题清单、流程与线框、状态×权限矩阵、改动边界、验收、假设与决策 | — | — |
| [078a](./PLAN-078a-state-consistency-qa-diagnosis.md) | 状态一致与 QA 诊断基线（`gated`、后台检查轮次、检查未完成与质量阻断分离、泰州内网术语模型） | P0 | 6–8.5 |
| [078b](./PLAN-078b-qa-resolution-loop.md) | QA 处理闭环（规则注册表、定位、处置、复检对比、待办面板、正式门禁） | P0 | 9–13 |
| [078c](./PLAN-078c-run-parameter-confirmation.md) | 每次翻译前参数确认（dry-run 校验、确认抽屉、偏好解耦、幂等摘要、源文件生命周期） | P1 | 5–7 |
| [078d](./PLAN-078d-run-search-and-management.md) | 服务端检索与分页、版本归组、改名、按动作授权 | P1 | 5–7 |
| [078e](./PLAN-078e-batch-and-recycle-bin.md) | 回收站、安全清除、批量接口与多选 | P1 | 6–9 |
| [078f](./PLAN-078f-efficiency-reliability.md) | 拖放、预检限制、轮询、错误反馈、对话框、外发显式化 | P1/P2 | 3–5 |
| [PROMPT-078](./PROMPT-078-workbench-improvement.md) | 评估提示词与前序静态核对记录 | — | — |

执行顺序：078a → 078b；078c、078d 可与 078b 并行；078e 依赖 078d；078f 可以穿插。

本轮只做了调查和设计，没有修改业务代码，没有迁移数据库，没有清理任务或 QA 记录，也没有部署。运行证据包括：`tests/api` 中 1 个用例失败（`TERM_EXTRACTION_DEGRADED`），以及本机库的只读聚合（37 个任务）。实施时另建 `docs/walkthroughs/WT-078-*.md` 记录证据。
