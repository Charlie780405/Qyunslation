# PLAN-034g：人工审校工作台

> 状态：**已编码**（句段表 + API 闭环 + 最小静态页）
> 父计划：[PLAN-034](./PLAN-034-pharma-rd-mvp.md)
> 依赖：[034c](./PLAN-034c-saas-persistence.md)、[034f](./PLAN-034f-model-gateway-qa.md)（及 034d/034e 批准回流）
> 验收门：`bash scripts/verify-plan-034g.sh`
> Walkthrough：[WT-034g](../../walkthroughs/WT-034g-human-review-bench.md)

## 目标

逐段审校、批注、批准、版本比较；把修订回流到术语候选与 TM 批准闭环（「只有已批准句段进正式 TM」的执行面）。

## 交付（已落地）

1. 审校视图：`/static/review.html` + `GET /api/v1/review/queue`（pending / approved / rejected）。
2. 批准动作：审计 `review.segment.approve`；TM 入库；可选 `promote_term` → concept staging。
3. 版本比较：`GET /api/v1/review/diff`（difflib hunks）。
4. 候选面板：`GET /api/v1/review/suggestions`（确认前不入库）。
5. `HUMAN_REVIEW` 入队；`PRESERVE` 不入队。

## API

| 方法 | 路径 |
| --- | --- |
| POST | `/api/v1/review/enqueue` |
| GET | `/api/v1/review/queue` |
| POST | `/api/v1/review/segments/{id}/note` |
| POST | `/api/v1/review/segments/{id}/decide` |
| GET | `/api/v1/review/diff` |
| GET | `/api/v1/review/suggestions` |

## 判据

- 未批准不得进正式 TM。
- 批准事件可审计（谁/何时/哪一段）。
- 原始文件哈希不变；审校只改派生译文对象。

## Out of Scope

- 移动端 App / 小程序
- 复杂工作流引擎（BPMN）
- OIDC 生产适配（→ 034h）
- Vue 主站重构

## 完成定义

- [x] Web 审校最小闭环可用
- [x] 批准 → TM / 术语候选 集成测试
- [x] WT-034g 截图与权限说明（页面路径）
