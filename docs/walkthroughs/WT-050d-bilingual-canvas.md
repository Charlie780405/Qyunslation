# WT-050d：原译文双画布

对应 [PLAN-050d](../plans/PLAN-050-qyunslation-ui-ux/PLAN-050d-bilingual-canvas.md)

- 主视图仍是 `.qy-preview-src` / `.qy-preview-dst`（PLAN-017 + 021 viewer）
- 窄屏：`body.qy-050-src-only` / `qy-050-dst-only`；Alt+1 / Alt+2 切换
- 页定位：检查器页码 + `qy050:goto-page`；百分比滚动只作降级
- 高清/缩放/旋转沿用 `apply-pdf2zh-viewer.py` / `preview-dpi`
- 原文画布无编辑控件（只读）

## 生产上线记录：译文预览显示纯译文

- 代码提交：`8c03442db4a42bb3fd44fa6986c5330bdc428bac`（`fix: preview standalone translation in translated pane`），已推送 `origin/main`。
- 行为：任务同时产出 `*.mono.pdf` 与 `*.dual.pdf` 时，译文预览优先取纯译文；原文仍由原文栏单独显示。双栏同步滚动由现有查看器默认开启。
- 部署时间：2026-10-19 16:01（UTC+8），运行 `bash scripts/deploy-translate-stack.sh`；无数据库迁移。
- 部署门禁：迁移对齐、前端构建新鲜、API 路由注册均通过；sidecar 本地/远端指纹一致（`7542777de0fd`）；`pdf2zh.service` 与 `qyunslation-office.service` 均为 active。
- 上线后健康检查：公网 `/next/`、公网 `/api/v1/health`、本机 GUI `/` 均返回 HTTP 200。
- 代码检查：`py_compile` 与 `git diff --check` 通过；未运行聚焦测试。
- 浏览器走查：**BLOCKED**，当前环境没有 Chrome DevTools MCP，未能验证登录后的预览内容、同步滚动和控制台状态。
- LIVE 术语闭环：不适用；本次只调整译文预览的产物选择。未改动生产数据。

## 生产上线记录：扩大双栏预览并收起左侧导航

- 代码提交：`05e7dea3a857db8b0ea194385c107d425d14d840`（`feat: expand run preview and collapse sidebar`），已推送 `origin/main`。
- 行为：移除任务详情页右侧对象详情；原文和译文画布铺满详情内容区。左侧导航新增收起/展开按钮，收起时保留带可访问名称的图标导航。
- 部署时间：2026-10-19 16:29（UTC+8），运行 `bash scripts/deploy-translate-stack.sh`；无数据库迁移。
- 构建：`npm run build` 通过；构建提示浏览器兼容数据陈旧和 PDF 相关 chunk 超过 500 kB，无构建错误。未运行测试套件。
- 部署门禁：迁移对齐、前端构建新鲜、API 路由注册均通过；sidecar 本地/远端指纹一致（`7542777de0fd`）；`pdf2zh.service` 与 `qyunslation-office.service` 均为 active。
- 上线后健康检查：公网 `/next/` 与 `/api/v1/health`、本机 GUI `/` 与 sidecar health 均返回 HTTP 200；公网页面引用本次构建的 `index-B9e_yUhU.js` 和 `index-DA4Ax8hJ.css`。
- 浏览器走查：**BLOCKED**，当前环境没有 Chrome DevTools MCP，未能验证登录后的画布宽度、侧栏交互、键盘操作和控制台状态。
- LIVE 术语闭环：不适用；本次只调整工作台布局，没有修改生产数据。
