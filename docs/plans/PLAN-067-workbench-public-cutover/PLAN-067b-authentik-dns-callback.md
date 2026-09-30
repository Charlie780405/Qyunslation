# PLAN-067b：Authentik 应用、DNS 与回调契约

状态：**局部完成 · provider 已校正；公网 DNS/Caddy 仍阻断**

## 目标

确认 `qyunslation` OIDC provider/application 与 Qyunslation BFF 的真实回调一致，并为公网 issuer、JWKS 和试点组灰度建立可验证前置条件。

## 实施内容

1. 将 `scripts/plan054-apply-blueprint.sh` 的默认回调从旧的 `/oauth2/callback` 改为 `/auth/callback`。
2. 支持受保护环境通过 `QYUNSLATION_OIDC_REDIRECT_URI` 显式覆盖回调，默认值仍是生产 BFF 回调。
3. 运行幂等 provider/application 校正脚本；client secret 只从受保护 `deploy/authentik/.env` 读取，不打印。
4. 确认 provider 的 client ID、issuer、audience、scope、tenant claim、签名和 strict redirect URI。
5. 建立 Authentik 试点组 `qyunslation-vue-beta`，后续由 BFF 映射 `workbench_v2` capability；不在浏览器信任组名。
6. 在 qyunsgen Caddy 中准备 `auth.qyunsgen.com` → `127.0.0.1:9000`，保留 `X-Forwarded-Proto=https`，不暴露 9000。
7. 在 DNS 控制面增加 `auth.qyunsgen.com`，并验证公网 discovery/JWKS/TLS。

## 安全边界

- 不把 client secret、bootstrap token、session key、数据库 URL 或 Authentik 管理凭据写入 Git。
- 不把旧 `/oauth2/callback` 继续作为正式回调；若发现历史客户端依赖，必须单独登记临时兼容期限。
- DNS 未解析、Caddy 未加载或公网 JWKS 未返回 `keys` 时，067b 不得标记完成，也不得进入 067c/067d 的公网登录验收。

## 验证门槛

- 本地 Authentik live/ready、provider/application 查询和本地 JWKS 通过。
- provider 的唯一正式 redirect URI 为 `https://translate.qyunsgen.com/auth/callback`。
- `auth.qyunsgen.com/.well-known/openid-configuration`、JWKS 和 TLS 通过公网验证。
- qyunslation 与 Authentik 的 issuer、audience、tenant claim 完全一致。
- 试点组外账号没有 `workbench_v2` capability。

## 当前缺口

- 当前 `auth.qyunsgen.com` 无 DNS 解析。
- 当前 qyunsgen Caddy 文件尚无 Authentik 站点块。
- 当前 `office.env` 尚无 BFF client ID/session key；这属于 067c，不在本子计划中提前注入。

因此本地 provider 契约已满足，但整个子计划尚不能关闭；公网 DNS/Caddy 完成后必须重新执行 discovery、JWKS 和 TLS 验证。
