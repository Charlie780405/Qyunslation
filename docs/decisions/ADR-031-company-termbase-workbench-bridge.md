# ADR-031：Gradio 公司术语工作台采用本机签名桥接

> 日期：2026-09-14
> 状态：已接受
> 关联：[PLAN-060](../plans/PLAN-060-company-termbase-workbench/README.md)

## 决策

生产翻译 UI 是补丁式 pdf2zh Gradio，而公开 API 使用 OIDC；两者不能安全地让浏览器自行传递项目/租户或带服务密钥调用内部 API。因此采用 Gradio 服务器 callback 到 sidecar 的回环 HMAC 桥接。

签名覆盖 HTTP 方法、无 query 的路径、原始请求体 hash、时间戳和 nonce。sidecar 只信任 loopback、拒绝过期和重放；Caddy 不对外代理 `/internal/workbench`。用户由 Gradio 的已登录 `request.username` 得出；租户、公司共享项目和角色由 sidecar 派生。

## 后果

- 优点：密钥、项目和权限不进入浏览器；可在现有 UI 上渐进交付；翻译服务不可用时可安全降级。
- 代价：两个本机服务必须读取同一受保护部署密钥；部署须先验证服务绑定和 Caddy 负向路由。
- 未采纳：浏览器直连 `/api/v1`（会混合会话鉴权与 OIDC，且暴露策略边界）；把内部端点公开给 Caddy（扩大攻击面）。
