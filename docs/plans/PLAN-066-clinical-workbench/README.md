# PLAN-066：Qyunslation 临床翻译工作台 UI/UX v2

状态：**进行中 · 基础壳、BFF 会话与 TranslationRun 台账切片已落地**

## 已完成

- `frontend/` 增加独立 `/next` Vue 工作台入口，保留旧 Vue/Gradio 根路径。
- 建立临床编辑工作台设计令牌、响应式布局、登录、工作台、设置和专业词库页面。
- 增加统一前端 API client、会话状态和本地预览模式；不把 token 或密钥写入浏览器存储。
- 增加 `/api/v1/me`、上传预检、个人偏好 API，以及 Alembic `066a0001` 基础表。
- 预检执行大小限制、扩展名白名单、SHA-256、租户隔离和 24 小时暂存 TTL；预检不会自动启动翻译。
- `066c0001` 提供 OIDC Authorization Code + PKCE BFF：state、PKCE verifier 和 nonce 服务端存储，浏览器只持有 HttpOnly 随机会话 ID；写请求启用双提交 CSRF，退出会立即撤销会话。
- `066e0001` 提供 TranslationRun 持久化台账、租户隔离、幂等创建、状态查询、取消和 generation 重试；已接入现有非 Gradio TranslationService，未初始化 runner 时明确落为 `blocked`，不伪造已开始翻译。
- 预检确认卡片已接入 Vue 工作台；用户明确点击“确认并开始翻译”后才创建 TranslationRun。

## 当前入口

- 开发预览：`cd frontend && npm run dev`，访问 `/next/login`。
- 构建产物：`qyunslation/static/app/`，由 FastAPI `/next` 和 `/app-assets` 提供。
- 旧入口：`/`、`/admin` 和现有 `pdf2zh_next --gui` 不在本切片中切换。

## 后续切片

1. 将 TranslationService 完整抽为独立 runner：Manifest、状态文件、取消/重启 reconcile、PDF `pdf2zh_next` CLI 和受控产物下载。
2. 接入 TranslationRun 轮询 generation 防串线、Artifact API 和真实进度/阶段映射。
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
