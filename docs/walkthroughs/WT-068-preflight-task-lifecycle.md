# WT-068：预检提速、语言选择与任务生命周期

## 发布范围

- 提交：`9c90742`（PLAN-068 实现），`5cc7046`（幂等键编码修复）。
- 数据库迁移：`068f0001`，已在生产数据库执行到 head。
- 发布方式：重启 `qyunslation-office.service`；未修改 Caddy 路由，也未触碰 Gradio/pdf2zh 服务。

## 功能证据

### 预检

- 上传改为分块落盘并同步计算 SHA-256，不再先把完整文件拼成第二份内存 `bytes`。
- 同一租户、同一操作者、同一摘要且文件未过期时复用预检记录。
- 浏览器通过 XHR 展示真实上传百分比，完成上传后再显示“正在检查文件”。
- 上传仍不会自动启动翻译。

### 语言

- 工作台上传区直接显示源语言和目标语言选择。
- 当前正式选项为 English / 简体中文；服务端拒绝相同语言、未知语言和不完整语言对。
- 任务快照保存 `source_language`、`target_language` 和规范化 `direction`；旧只传 `direction` 的调用继续兼容。

### 任务管理

- 任务支持查询、重命名、归档、恢复和终态删除。
- 默认列表隐藏归档任务；用户可以勾选显示已归档。
- 活动任务只能取消，服务端拒绝直接删除或归档活动任务。
- 删除会清理授权 artifact；没有其它 generation 引用时才清理预检暂存文件。

### 翻译启动错误修复

- 生产截图中的 `Failed to construct 'Headers': String contains non ISO-8859-1 code point.` 根因是把“简体中文”和中文文档类型直接拼入 `Idempotency-Key` 请求头。
- 工作台现在对幂等键的每个配置片段执行 `encodeURIComponent`，保持幂等语义，同时确保浏览器 `Headers` 接收的值为 ASCII。

## 自动化与生产验证

- `npm --prefix frontend run type-check`：PASS。
- `npm --prefix frontend run build`：PASS；仅有已有的大 chunk/browserslist 提示。
- `.venv/bin/python -m pytest -q tests/persist/test_plan066_workbench_foundation.py tests/persist/test_plan066e_translation_runs.py tests/ui/test_plan066_next_surface.py -o addopts=''`：15 passed。
- Alembic：`068f0001 (head)`。
- `qyunslation-office.service`：active。
- 本机 `/api/v1/health`：`{"schema":"034h","db":"ok"}`。
- 公网 `/next/login`：200；`/api/v1/health`：200；未认证 `/api/v1/me`：401。
- 公网新 bundle 包含“源语言”“目标语言”“上传中”“显示已归档”等功能标记；Logo 静态资源仍为 200。
- 修复部署后公网新 bundle 包含 `encodeURIComponent`；公网 `/next/login`：200，`/api/v1/health`：200，未认证 `/api/v1/me`：401；本机 sidecar health：`{"schema":"034h","db":"ok"}`。

## 未执行项

当前执行环境没有 Chrome DevTools MCP/隔离浏览器，因此真实浏览器的 320/768/1024/1440px 视觉、键盘和 axe 门禁仍为 BLOCKED。HTTP、构建和 API 测试证据不替代浏览器验收；具备浏览器环境后应补做语言切换、归档筛选、删除确认和大文件进度截图。
