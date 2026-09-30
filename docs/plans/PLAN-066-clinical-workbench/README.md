# PLAN-066：Qyunslation 临床翻译工作台 UI/UX v2

状态：**进行中 · 第一切片已落地**

## 已完成

- `frontend/` 增加独立 `/next` Vue 工作台入口，保留旧 Vue/Gradio 根路径。
- 建立临床编辑工作台设计令牌、响应式布局、登录、工作台、设置和专业词库页面。
- 增加统一前端 API client、会话状态和本地预览模式；不把 token 或密钥写入浏览器存储。
- 增加 `/api/v1/me`、上传预检、个人偏好 API，以及 Alembic `066a0001` 基础表。
- 预检执行大小限制、扩展名白名单、SHA-256、租户隔离和 24 小时暂存 TTL；预检不会自动启动翻译。

## 当前入口

- 开发预览：`cd frontend && npm run dev`，访问 `/next/login`。
- 构建产物：`qyunslation/static/app/`，由 FastAPI `/next` 和 `/app-assets` 提供。
- 旧入口：`/`、`/admin` 和现有 `pdf2zh_next --gui` 不在本切片中切换。

## 后续切片

1. 完成 OIDC Authorization Code + PKCE BFF 会话与 PostgreSQL session store。
2. 将现有翻译服务抽为 TranslationRun runner，接入预检确认和状态轮询。
3. 接入 Manifest 文档画布、对象修订、QA blocker 和正式导出门禁。
4. 补齐词库分页、版本、候选审核和工作台术语命中联动。
5. 执行浏览器断点、无障碍、性能、Caddy 灰度和 `/legacy` 回滚验收。

## 验证

```bash
uv run python -m pytest -q -o addopts='' \
  tests/ui/test_plan066_next_surface.py \
  tests/persist/test_plan066_workbench_foundation.py
npm --prefix frontend run type-check
npm --prefix frontend run build
bash scripts/verify-plan-066.sh
```
