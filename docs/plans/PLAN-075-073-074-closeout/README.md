# PLAN-075：073/074 收口与生产对齐

> 状态：**实施中**
> 依赖：PLAN-073（已上线）、PLAN-074（074a0001 已迁移）

## 目标

消除前后端/迁移错位；补部署门禁；收束 074 文档与真件回归；完成 073 遗留（DeepSeek、外发审计、浏览器证据）；领域评测真实化。

## 子计划

| 子计划 | 目标 |
| --- | --- |
| [075a](./PLAN-075a-production-align.md) | 074 合并、备份、迁移、部署、API 冒烟 |
| [075b](./PLAN-075b-deploy-gates.md) | deploy_gate.py 三道门禁 |
| [075c](./PLAN-075c-074-closeout.md) | PLAN-074 文档、live regression、WT-074 |
| [075d](./PLAN-075d-073-leftovers.md) | DeepSeek、外发审计 API、浏览器证据 |
| [075e](./PLAN-075e-domain-eval-real.md) | 机器译文评测、词包扩充与导入 |

## 验收

`bash scripts/verify-plan-075.sh` — PASS/FAIL/BLOCKED 三态。
