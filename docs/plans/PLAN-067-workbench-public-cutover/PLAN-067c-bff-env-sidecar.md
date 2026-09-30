# PLAN-067c：BFF 密钥注入与 sidecar 配置

状态：**待 DNS 门禁解除**

## 目标

在公网 Authentik issuer 可解析且 067b 门禁通过后，将 client ID、confidential client secret、BFF session key 和正式回调注入 sidecar，并重启服务验证配置生效。

## 实施

1. 先执行 `scripts/verify-plan-067b.sh`；存在 BLOCKED/FAIL 时停止。
2. 默认只读执行 `scripts/inject-plan-067c-bff-env.py`；仅在 DNS 通过后使用 `--apply`。
3. 注入器只读取受保护 Authentik env，生成高熵 session key；已有 session key 不自动轮换。
4. 更新采用 0600 备份、临时文件、fsync 和原子替换；不打印任何 secret。
5. 重启 `qyunslation-office.service`，确认其加载 `office.env` 且无敏感日志。
6. 验证 `/auth/login` 不再返回配置缺失错误，且 sidecar 健康、已有 Bearer API 兼容。

## 安全门禁

- 无公网 DNS 不得 `--apply`。
- 不把真实 env、备份、session key 或 client secret 纳入 Git。
- session key 变更必须单独批准；默认保留现有 key，避免立即使旧会话失效。

## 验证

- `uv run pytest -q tests/scripts/test_plan067c_bff_env.py -o addopts=''`
- `python scripts/inject-plan-067c-bff-env.py --env-file <temp> --authentik-env <temp> --apply --skip-dns` 仅用于隔离测试。
- 生产执行后检查服务状态、`/api/v1/health`、`/auth/login?format=json` 和日志脱敏。
