# WT-067i：OIDC 登录回到初始界面修复

## 现象

用户在 `/next/login` 点击公司账号登录，Authentik 登录成功后又回到登录页，看起来像会话没有建立。

## 根因

前端 `beginLogin()` 无条件把当前 URL 作为 `return_to`。登录页本身是 public route，回调返回 `/next/login` 后不会触发受保护路由守卫读取会话，因此页面停留在初始登录界面；再次点击登录即可形成循环感。

## 修复

- 当前路径为 `/next/login` 时，默认回调目标改为 `/next/workbench`。
- 若登录页由受保护路由守卫带入合法 `return_to`，优先回到该目标。
- 服务端原有 `_safe_return_to()` 继续执行同源路径校验，未放宽开放重定向防护。

## 验证

- `tests/ui`：`49 passed`。
- `npm --prefix frontend run type-check`：通过。
- `npm --prefix frontend run build`：通过。
- 生产 asset `index-DEQ4vWis.js`：`200`，包含 `next/login`、`next/workbench` 和 `return_to` 逻辑。
- sidecar：`active/running`，`NRestarts=0`。
- `/auth/login?format=json&return_to=/next/workbench`：返回 Authentik authorize URL，回调 URI 仍为 `/auth/callback`。
- 提交：`2abda20 fix: return OIDC login to workbench`，已推送 `origin/main` 并重启生产 sidecar。

## 用户侧操作

请刷新登录页后重新点击“使用公司账号登录”。如果浏览器保留了旧静态 chunk，可执行一次强制刷新或使用无痕窗口；不需要清除服务端会话。
