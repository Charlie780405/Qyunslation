# WT-067b：Authentik provider、DNS 与回调契约证据

对应计划：[PLAN-067b](../plans/PLAN-067-workbench-public-cutover/PLAN-067b-authentik-dns-callback.md)

## 已执行

- 将 `scripts/plan054-apply-blueprint.sh` 的 provider 回调默认值改为 BFF 正式回调 `/auth/callback`。
- 保留受保护环境变量 `QYUNSLATION_OIDC_REDIRECT_URI` 作为显式覆盖，不打印任何 secret。
- 已核对本地 Authentik server ready endpoint 可用。
- 新增 `scripts/verify-plan-067b.sh`，可在 DNS 修复后重复执行并区分 FAIL/BLOCKED。

## 现场结果

| 检查 | 结果 | 说明 |
|---|---|---|
| 本地 Authentik health | PASS | `127.0.0.1:9000` ready/live 可达 |
| Authentik provider/application 校正 | PASS | 精确提交 `a78dac6` 后执行幂等脚本，provider/application 均更新 |
| provider 正式回调 | PASS | API 返回 strict URI `https://translate.qyunsgen.com/auth/callback` |
| Authentik 试点组 | PASS | 已创建 `qyunslation-vue-beta`，非 superuser；成员与 capability 映射留待 067d |
| `auth.qyunsgen.com` DNS | PARTIAL/BLOCKED | Cloudflare 权威、1.1.1.1、8.8.8.8 已返回 A 记录；生产主机配置的 `108.61.10.10` 仍返回 NXDOMAIN，本机 `getent/curl` 仍无法解析 |
| 公网 discovery/JWKS | BLOCKED | 公网权威链路已具备记录，但生产主机 resolver 尚未更新，不能从 sidecar 网络路径验证 issuer |
| Caddy Authentik 站点 | PASS（本机 resolve） | qyunsgen `main` 已推送 `fd26ce62`；Caddy reload、`--resolve` health 200、discovery issuer/JWKS 通过 |
| client ID/session key | DEFERRED | PLAN-067c 受保护配置注入 |

最近一次公网复核显示：Cloudflare 权威链路、`1.1.1.1`、`8.8.8.8` 和 `9.9.9.9` 均返回 Cloudflare A 记录（`104.21.15.47`、`172.67.205.136`）；但本机 systemd-resolved 的上游 `108.61.10.10` 仍返回带 SOA 的 NXDOMAIN，导致 `getent`、`curl` 和 067b 脚本的本机 DNS 门禁仍失败。不能把“公共递归已看到记录”误判为 sidecar 已具备可用的 issuer 解析。

恢复条件：等待 `108.61.10.10` 的负缓存过期，或由主机运维将生产解析路径切换/刷新到能看到该记录的受控 resolver；随后必须重新执行 067b，并从本机成功访问公网 JWKS 后才能推进 067c。

## 不得推进的缺口

在生产主机 resolver 可用前，不得重启 sidecar 进行公网登录验收，也不得将 `/next`、`/auth` 或 `/api/v1` 接入公网 Caddy。067b 保持局部完成状态，不推进 067c。
