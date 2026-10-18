# Authentik 蓝图归属说明（PLAN-077 T5）

`qyunslation-oidc.yaml` 是**迁移基线**，不再是活动 SSOT。

- 活动 SSOT：QyunsApps 仓 `authentik/blueprints/qyunslation-oidc.yaml`（QyunsApps PLAN-002d）。与本文件的唯一语义差异是不含 `client_secret`：这里的 `!Env [QYUNSLATION_OIDC_CLIENT_SECRET, change-me-…]` 带占位默认值，Authentik 容器里没有该环境变量时，apply 会把 secret 改成占位值。
- 本目录保留为恢复副本，观察期（2–4 周）内不删除；不要在这里改 provider / application / scope mapping，改动请在 QyunsApps 开计划。
- `scripts/plan054-apply-blueprint.sh` 不要再作为日常流程使用；apply 只由用户按 QyunsApps `authentik/scripts` 的流程执行。
- 本仓 `deploy/authentik/docker-compose.yml`（Authentik 运行栈）仍在这里，迁出归 QyunsApps PLAN-002e，需另行批准。
