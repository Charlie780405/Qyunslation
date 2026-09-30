# WT-067c：BFF 配置注入器与 sidecar 门禁证据

对应计划：[PLAN-067c](../plans/PLAN-067-workbench-public-cutover/PLAN-067c-bff-env-sidecar.md)

## 已完成

- 新增受保护配置注入器 `scripts/inject-plan-067c-bff-env.py`。
- 默认只读；生产写入必须显式 `--apply`，且公网 Authentik 主机必须 DNS 可解析。
- 注入使用 0600 备份、临时文件、fsync 和原子替换；已有 session key 不自动轮换。
- 测试覆盖 client ID/secret 注入、回调、session key 生成、文件权限、备份和 secret 不打印。

## 验证

```text
uv run pytest -q tests/scripts/test_plan067c_bff_env.py -o addopts=''
2 passed
```

生产预检结果（截至最近一次复核）：

```text
BLOCKED: public Authentik host does not resolve: auth.qyunsgen.com

补充证据：Cloudflare 权威服务器及 `1.1.1.1`、`8.8.8.8` 已返回 A 记录；该门禁使用生产主机的系统解析路径，而其上游 `108.61.10.10` 仍返回 NXDOMAIN。因此这不是跳过门禁的理由，sidecar 实际回调路径仍可能无法解析 issuer。
```

因此本切片没有写入 `/home/dev/pdf2zh/office.env`，没有重启 `qyunslation-office.service`，没有伪造 sidecar 登录闭环完成。

## 下一步输入

DNS 恢复后依次执行：

1. `scripts/verify-plan-067b.sh`。
2. `python scripts/inject-plan-067c-bff-env.py --apply`。
3. 重启 sidecar 并执行 067d 登录、回调、`/api/v1/me`、登出和 CSRF 验收。
