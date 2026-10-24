# PLAN-088：文献跨仓统筹对齐（只协调）

> 状态：**文档阶段；未改代码、未读生产配置、未部署** · 父纲要：QyunsApps PLAN-004（004c） · 日期：2026-10-24 · 走查 [WT-088](../../walkthroughs/WT-088-literature-hub-alignment.md)

## 1. 目标

QyunsApps PLAN-004 统筹 QyunsWatch、WeKnora、Qyunslation 的文献与翻译链路。本仓已有三份相关计划，本计划**不新建实施项**，只把总纲需求逐条映射到它们，并写清「本仓哪件事落地，才能解锁对端哪一步」，避免重复规划和编号占用。

## 2. 映射

| 总纲需求 | 本仓现有计划 | 当前状态 | 解锁对端 |
| --- | --- | --- | --- |
| 译文提交带 WeKnora 的 `request_id`、`artifact_id` 并回传 | PLAN-082 T2（`origin`、`external_ref`、源文件 SHA-256） | 规划中 | WeKnora 019e 的完整追溯 |
| 自动翻译不挤占人工任务、满载排队 | PLAN-081b（全站 2 路准入与持久队列）、`/capacity` | 规划中 | **WeKnora 019d 自动翻译** |
| 服务令牌按调用方分离、带 scope | PLAN-081d（机器身份） | 规划中 | 令牌拆分 |
| 术语单一事实源，译文记录术语版本 | PLAN-086（`/api/v1/language-assets/*`） | 接口已实现；上线前待专家盲评与灰度 | **QyunsWatch 026d 术语对齐** |
| WeKnora 文献目录与预览代理 | 分支 `codex/literature-preview-catalog` | **生产工作目录正在运行该分支，且有未提交修改** | 先由责任人合并并清理 |

## 3. 停手条件

生产服务 `qyunslation-office` 的工作目录 `/home/dev/qyunslation` 当前停在 `codex/literature-preview-catalog`，比 `main` 多若干提交，并有未提交修改（`custom_api.py`、`glossary/ssot.py`、`pipeline/term_snapshot.py`、`server/core.py` 等）。在其责任人合并、提交并清理之前，本仓不做任何会改变运行代码的发布，否则可能覆盖线上在跑的版本。

## 4. Out of Scope

不改任何 Qyunslation 代码；不改生产配置；不占用 PLAN-081/082/086 的范围。

## 5. 跟踪

081b、082 T2、086 每上线一项，就在本表更新状态，并通知 WeKnora PLAN-019d、QyunsWatch PLAN-026d 的负责人。

## 6. 回滚

纯文档，无需回滚。
