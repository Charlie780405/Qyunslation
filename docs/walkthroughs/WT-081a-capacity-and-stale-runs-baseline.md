# WT-081a：容量基线与陈旧运行记录核对

> 日期：2026-10-21 · 计划：[PLAN-081](../plans/PLAN-081-translation-admission-and-service-api/PLAN-081-translation-admission-and-service-api.md) §081a
> 范围：只读核查，加上一次经批准的两条陈旧记录终结。未改服务配置、未读取 `.env`、未触发翻译任务。
> 更正：本文件初版读取的是旧表 `workbench_translation_run`，误判为“近 14 天无新记录”。真实运行记录在 `translation_run_record`，以下为更正后的数据。

## 1. 运行记录基线

### 1.1 新表 `translation_run_record`（真实运行）

| 状态 | 条数 | 最近更新（UTC） |
| --- | --- | --- |
| `succeeded` | 35 | 2026-10-21 01:04 |
| `gated`（等待复核） | 8 | 2026-10-21 00:55 |
| `cancelled` | 3 | 2026-10-21 00:03 |
| `interrupted` | 4 | 2026-10-19 03:44 |
| `degraded` | 1 | 2026-10-20 14:33 |
| `failed` | 1 | 2026-10-19 03:44 |
| `blocked` | 1 | 2026-10-19 03:44 |

- 合计 53 条，近期有活动。
- 非终态运行（`queued`、`scanning`、`translating`、`rendering`）为 **0 条**，当前没有执行中的任务。
- 任务 `eb7e4876` 状态为 `gated`，与 WT-079 §13–§16 一致。

### 1.2 旧表 `workbench_translation_run`（仅剩历史数据）

该表没有心跳与执行器字段，`heartbeat.py` 中的恢复逻辑不作用于它。`quality/ledger.py` 仍读取它。

| 状态 | 条数 |
| --- | --- |
| `review_ready` | 18 |
| `translating` | 2（已终结，见第 2 节） |
| `extraction_degraded` | 1 |

## 2. 两条陈旧记录的终结

| 项 | 内容 |
| --- | --- |
| 记录 | `3807783c-…`、`5b77a450-…`（测试运行：`actor_sub=test`，`external_task_id=plan060-live-reuse`） |
| 陈旧依据 | 最后更新于 2026-09-15；此后服务启动约 222 次，执行器不存在；`var/` 下无对应产物 |
| 终结方式 | 按 `heartbeat.py` 的 `mark_interrupted` 语义：`status=interrupted`，`degradation_reason` 写明原因，更新 `updated_at` |
| 执行 | 单个事务，只更新这两行；`RETURNING` 校验两行均已更新 |
| 校验 | 旧表剩余 `translating` 为 **0** |
| 备份 | `var/plan081a/stale-legacy-runs-before-20261021.jsonl`（终结前的完整行，不入库） |

注意：`interrupted` 在新表的语义中是可恢复状态。旧表没有恢复路径，因此这两条记录实际上仍然不会再执行。

## 3. 本机容量基线

| 项 | 数值 |
| --- | --- |
| CPU | 12 核 |
| 内存 | 22 GiB，可用约 15 GiB |
| 根分区 | 469 GB，已用 346 GB（78%），可用 103 GB |

本机资源未显示瓶颈，但未做并发压测。

## 4. 远端模型主机（只读采样，2026-10-21）

端点：`100.67.66.123:11434`（Ollama，tailscale 内网）。采样仅使用 `GET /api/version`、`/api/tags`、`/api/ps`，未触发推理。

| 项 | 数值 |
| --- | --- |
| Ollama 版本 | 0.34.4 |
| 已安装模型 | `qwen3.6:35b-a3b`（23.9 GB）、`bge-m3:latest`（1.2 GB） |
| 当前加载 | `qwen3.6:35b-a3b`：显存 23.5 GB，上下文 65536；`bge-m3`：显存 0.7 GB，上下文 8192 |

`OLLAMA_NUM_PARALLEL` 无法通过 API 读取，按 PLAN-081 文档记录为 1。两路并发仍需压测验证。

## 5. 081a 未完成项

- 每任务 chunk 并发与上传/代理边界的记录。
- 两路并发下的竞争压测（磁盘、PDF 引擎、模型端）。
- `OLLAMA_NUM_PARALLEL` 的实际值（需在远端主机上查看服务配置，不经 API）。

## 6. 相关核对

- PostgreSQL 容器只监听 `127.0.0.1:5433`，PLAN-077 T3 记录的公网暴露已解除。剩余事项是口令是否仍为默认值（PLAN-079 F0，需用户核对）。
