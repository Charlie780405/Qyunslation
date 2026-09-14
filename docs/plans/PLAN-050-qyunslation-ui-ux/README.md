# PLAN-050：Qyunslation 中英医药翻译工作台 UI/UX

> 状态：**完成**
> 类型：产品界面与交互纵向改造
> 目标分支：`feat/PLAN-050-qyunslation-ui-ux`
> 依据：`SK-Q010 qyunslation-ui-ux`

## 文件索引

| 类型 | 文件 | 说明 |
| --- | --- | --- |
| 纲领 | [PLAN-050-qyunslation-ui-ux.md](./PLAN-050-qyunslation-ui-ux.md) | 目标、架构、阶段、总验收 |
| 050a | [PLAN-050a-runtime-baseline.md](./PLAN-050a-runtime-baseline.md) | 真实运行时与 UI 契约基线 |
| 050b | [PLAN-050b-workbench-shell.md](./PLAN-050b-workbench-shell.md) | 工作台壳层与设计系统 |
| 050c | [PLAN-050c-upload-preflight-task.md](./PLAN-050c-upload-preflight-task.md) | 上传、预扫描、任务状态 |
| 050d | [PLAN-050d-bilingual-canvas.md](./PLAN-050d-bilingual-canvas.md) | 原译文双画布与对象锚点 |
| 050e | [PLAN-050e-review-inspector-qa.md](./PLAN-050e-review-inspector-qa.md) | 表图对象、术语、QA 审校 |
| 050f | [PLAN-050f-responsive-accessibility.md](./PLAN-050f-responsive-accessibility.md) | 响应式、无障碍与性能 |
| 050g | [PLAN-050g-verify-delivery.md](./PLAN-050g-verify-delivery.md) | 真实运行时验收与交付 |

## 执行规则

1. 先批准 PLAN-050 纲领，再按依赖顺序批准/执行 050a–050g。
2. 每个子计划完成一个可验证的纵向切片；未通过本子计划门禁不得进入下一阶段。
3. 所有计划、WT 和证据留在本仓库 `docs/plans`、`docs/walkthroughs`；不得写入全局 Cursor 计划目录。
4. 业务代码、生产补丁和部署在计划批准前不改、不发、不重启。
