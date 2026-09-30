# WT-067b：Authentik provider、DNS 与回调契约证据

对应计划：[PLAN-067b](../plans/PLAN-067-workbench-public-cutover/PLAN-067b-authentik-dns-callback.md)

## 已执行

- 将 `scripts/plan054-apply-blueprint.sh` 的 provider 回调默认值改为 BFF 正式回调 `/auth/callback`。
- 保留受保护环境变量 `QYUNSLATION_OIDC_REDIRECT_URI` 作为显式覆盖，不打印任何 secret。
- 已核对本地 Authentik server ready endpoint 可用。

## 现场结果

| 检查 | 结果 | 说明 |
|---|---|---|
| 本地 Authentik health | PASS | `127.0.0.1:9000` ready/live 可达 |
| Authentik provider/application 校正 | PASS | 精确提交 `a78dac6` 后执行幂等脚本，provider/application 均更新 |
| provider 正式回调 | PASS | API 返回 strict URI `https://translate.qyunsgen.com/auth/callback` |
| `auth.qyunsgen.com` DNS | BLOCKED | 当前主机解析为空，curl 返回 DNS error |
| 公网 discovery/JWKS | BLOCKED | DNS 未就绪，不能验证公网 issuer |
| Caddy Authentik 站点 | PASS（本机 resolve） | qyunsgen `main` 已推送 `fd26ce62`；Caddy reload、`--resolve` health 200、discovery issuer/JWKS 通过 |
| client ID/session key | DEFERRED | PLAN-067c 受保护配置注入 |

## 不得推进的缺口

在 DNS 与 Caddy 站点完成前，不得重启 sidecar 进行公网登录验收，也不得将 `/next`、`/auth` 或 `/api/v1` 接入公网 Caddy。067b 保持局部完成状态，不推进 067c。
