# 对象存储归属与解耦决策包（PLAN-077 T4）

> 日期：2026-10-18 · 状态：**决策输入，不是决定** · 上游：QyunsApps `docs/assessments/qyunslation-object-storage.md`（PLAN-002f F4）

## 结论

先采用**方案 B**：保持现有 `qyunsgen-minio` 实例，为 qyunslation 单独设 bucket 与最小权限 service account，补备份与隔离恢复演练；暂不迁移数据，不新建 MinIO。理由与三方案对比见 QyunsApps 侧评估，本文只补本仓能给出的事实与门禁。

## 本仓代码事实（只读）

- `qyunslation/archive/storage.py` 的 `MinioStorageBackend` 使用配置的 endpoint 与 bucket，对象名前缀默认 `pdf2zh/`；bucket 不存在时自行创建（方案 B 落地时应改为只使用已建 bucket）。
- 消费者：qyunslation 服务、`office-archive-watch.service`、`pdf2zh-archive-watch.service`（均为 systemd user 单元，当前运行中）。
- 归档写入 `index.db` + MinIO + Vault 三处，需要一致；`LocalStorageBackend` 存在，是否可作为降级未核实。

## 没有做、也不会在本计划做

读取 access key / `.env`、列出或下载对象、改 bucket、删除任何数据。下面五项**必须由用户或 qyunslation 的后续计划在授权下补证**：

| # | 待补证据 | 谁补 | 补完写到 |
| --- | --- | --- | --- |
| 1 | 实际 bucket / prefix，用 root 账号还是专用账号 | 用户读取自己的 qyunslation 环境配置 | 本文件 + QyunsApps `registry/stateful.yaml` |
| 2 | 容量级别（数量级即可）与增长速度 | 用户（MinIO 控制台或 `mc du`） | 同上 |
| 3 | 是否有备份、是否与 `index.db` 同一时间点、有无隔离恢复演练 | 后续计划（参照 QyunsWatch 的 `minio-backup.sh` 方式） | WT |
| 4 | bucket 是否启用 SSE，KMS 主密钥归属与备份（密钥丢失则对象不可读） | 用户 | 本文件 |
| 5 | 归档写入失败时能否降级到本地存储 | 后续计划（代码核实 + 演练） | WT |

## 迁移门禁（任何迁移动手前必须全部满足）

1. 上表 1–5 项有证据。
2. 一次隔离恢复演练通过（恢复到无网络的临时 MinIO，校验对象数与抽样校验和，以及与 `index.db` 的对应）。
3. 独立回滚边界：迁移只搬一个 bucket，旧 bucket 保留到观察期结束。
4. 用户另行批准，并独立开 PLAN；不与 PG 绑定变更、Caddy、Authentik 同窗。

## 遗留

本计划结束时，`registry/stateful.yaml` 里 `qyunslation-object-storage` 的三个 `unknown` owner 仍是 unknown；补证后由 QyunsApps 更新。
