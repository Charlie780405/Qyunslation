# WT-088：文献跨仓统筹对齐（只协调）

> 对应计划：[PLAN-088](../plans/PLAN-088-literature-hub-alignment/PLAN-088-literature-hub-alignment.md) · 日期：2026-10-24 · 分支：`docs/PLAN-088-literature-hub-alignment`

## 执行摘要

按 QyunsApps PLAN-004 的要求，在本仓建立协调计划。**只新增文档，没有改任何代码、配置，也没有部署或重启服务。**

## 变更

- 新增 `docs/plans/PLAN-088-literature-hub-alignment/`（README、纲要）。
- 更新 `docs/plans/README.md`：增加 PLAN-088 一行，下一个可用编号改为 PLAN-089。

## 验证

- 编号核查：检查了本仓全部 worktree 与分支，PLAN-088 未被占用（已占用 081–087，其中 082、083、085 仅有分支）。
- 只读核实：生产服务 `qyunslation-office`、`pdf2zh` 为 active；工作目录 `/home/dev/qyunslation` 停在 `codex/literature-preview-catalog`，且有未提交修改；2026-10-24 复核：线上进程启动于 2026-10-21，早于该分支提交，预览接口 404，**线上没有加载这个分支**。

## 已知限制

本计划不解决检出目录停在未合并分支、带未提交修改的问题；该问题已记入 QyunsApps PLAN-004 缺口 G-004-2，需其责任人处理。该分支的功能非必需，不合并、不部署。

## 遗留

- 081b、082 T2、086 上线后更新 PLAN-088 映射表，并通知 WeKnora PLAN-019d、QyunsWatch PLAN-026d。
