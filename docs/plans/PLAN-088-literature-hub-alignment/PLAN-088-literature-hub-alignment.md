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
| WeKnora 文献目录与预览代理 | 分支 `codex/literature-preview-catalog`（7 个提交） | 未合并；**线上进程未加载它**（2026-10-24 核实）；功能非必需 | 不合并、不部署 |

## 3. 停手条件

生产服务 `qyunslation-office` 的工作目录 `/home/dev/qyunslation` 当前停在 `codex/literature-preview-catalog`，比 `main` 多 7 个提交，并有未提交修改（`custom_api.py`、`glossary/ssot.py`、`pipeline/term_snapshot.py`、`server/core.py` 等，含一个未提交的 `POST /terms/resolve`）。2026-10-24 实测：Qyunslation 进程（`qyunslation -i … --port 8010`）启动于 2026-10-21 16:35，早于该分支的 7 个提交（2026-10-22）；线上 `/api/v1/literature-preview` 返回 404，`QYUNSLATION_WEKNORA_CATALOG_URL` 未设置。**线上并没有在跑这个分支的代码**，只是检出目录被切到了该分支并带着未提交修改。这些未提交修改属于另一个代理的进行中工作，本仓不碰；本仓也不做任何会重启服务或改变运行代码的发布，否则会把检出目录里的未审代码带上线。

## 4. Out of Scope

不改任何 Qyunslation 代码；不改生产配置；不占用 PLAN-081/082/086 的范围。

## 5. 跟踪

081b、082 T2、086 每上线一项，就在本表更新状态，并通知 WeKnora PLAN-019d、QyunsWatch PLAN-026d 的负责人。

## 6. 回滚

纯文档，无需回滚。
