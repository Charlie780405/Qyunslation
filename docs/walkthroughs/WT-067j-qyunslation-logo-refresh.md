# WT-067j：Qyunslation Logo refresh

## 目标

将用户确认的 Qyunslation 蓝绿标志整理为透明 PNG 资产，并替换正式 Vue 工作台、兼容页面和 PWA 图标引用。旧 `quanxin-logo.svg` 保留，不作为新页面依赖，以便回滚。

## 交付

| 资产 | 用途 | 线上地址 |
|---|---|---|
| `qyunslation-logo.png` | 完整标志（图形 + Qyunslation 字标），可下载 | `https://translate.qyunsgen.com/app-assets/qyunslation-logo.png` |
| `qyunslation-mark.png` | 导航栏、登录页和 favicon 图标版 | `https://translate.qyunsgen.com/app-assets/qyunslation-mark.png` |

源文件同时保存在 `qyunslation/static/`，构建时复制到 `qyunslation/static/app/` 的 `/app-assets` 命名空间。新 Vue 页面不依赖公网未开放的 `/static/*` 路径；旧静态入口仍保留 `/static` 版本。

## 变更范围

- `/next/login` 和工作台应用壳使用图标版 Logo。
- 兼容设置页和任务空态使用完整标志/图标版。
- Vite 入口 favicon、PWA manifest 和 README 使用新资产。
- `frontend/public/` 纳入构建所需的两个 PNG。
- `quanxin-logo.svg` 未删除，保留为回滚资产。

## 验证证据

- 提交：`66b5eba`（产品 Logo 替换）、`05987e2`（通过 `/app-assets` 提供新 Vue 资源）、`9f95acc`（刷新 PWA Logo 缓存壳）。
- `npm --prefix frontend run type-check`：PASS。
- `npm --prefix frontend run build`：PASS；仅保留已有大 chunk warning。
- `.venv/bin/python -m pytest -q tests/ui -o addopts=''`：49 passed。
- `qyunslation-office.service`：active；`http://127.0.0.1:8010/api/v1/health`：`{"schema":"034h","db":"ok"}`。
- 公网 `app-assets/qyunslation-logo.png`：HTTP 200，`image/png`，immutable cache。
- 公网 `app-assets/qyunslation-mark.png`：HTTP 200，`image/png`，immutable cache。
- 公网 `/next/login`：HTTP 200；`/api/v1/health`：HTTP 200；未认证 `/api/v1/me`：HTTP 401；`/auth/login`：HTTP 302。

## 未执行项

当前运行环境没有 Chrome DevTools MCP 或可用的隔离浏览器，因此 320/768/1024/1440px 的截图、DOM、控制台和 axe 浏览器门禁未执行（BLOCKED）。已完成的 HTTP/构建证据不能替代该门禁；下一次具备浏览器环境时应至少复核登录页 Logo 加载、无水平溢出和控制台无资源 404。
