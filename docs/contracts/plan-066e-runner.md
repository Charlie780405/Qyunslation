# PLAN-066e：TranslationRun 独立 runner 契约

本契约描述 Vue 工作台与 PDF 非 GUI 执行器之间的边界。它不改变现有机器 Bearer API，也不把 Gradio 的会话状态暴露给浏览器。

## 运行目录

`QYUNSLATION_RUNNER_ROOT`（默认 `var/translation-runs`）下每个 generation 独占目录：

```text
<tenant_id>/<run_id>/generation-<n>/
├── state.json       # 0600，原子替换
├── runner.log       # 0600，仅 stdout/stderr
├── run.lock         # 0600，防止同一 generation 双启动
└── output/          # CLI 产物，只有此目录下的常规文件可投影为 Artifact
```

`state.json` 至少包含 `schema`、`task_id`、`generation`、`status`、`stage`、`progress`、`pid`、`outputs`、`reason` 和生命周期时间戳。`progress` 可为空；UI 不得把空值渲染为 0% 或伪造确定百分比。

## 启动与配置

- PDF 使用 `pdf2zh_next` CLI，不使用 `--gui`，也不通过 localhost HTTP 绕行 Gradio。
- 可由 `QYUNSLATION_PDF2ZH_CLI` 指定可执行文件；配置文件由 `QYUNSLATION_PDF2ZH_CONFIG` 指定，未设置时仅在 `/home/dev/pdf2zh/config.toml` 存在时使用。
- 语言、输出目录、页码、术语文件和扫描策略通过受控 argv 传入；模型密钥不能出现在 argv、状态文件、Artifact 响应或 UI 日志中。
- `QYUNSLATION_PDF_RUNNER=legacy` 仅作为迁移期显式回退开关；默认 PDF runner 为 CLI。缺少 CLI 时任务为 `blocked`，不得静默回到 Gradio。

## 状态与取消

- 进度只解析已验证的 `Progress: <0..1>, <label>` 或百分比行，阶段映射到 `structure`、`translating`、`rendering`、`qa` 等有限值。
- 取消先对独立进程组发送 `SIGTERM`，最多等待 10 秒，仍存活才发送 `SIGKILL`；最终状态必须写为 `cancelled`。
- 应用启动执行 reconcile：运行中的 PID 继续由 watcher 观察；PID 已不存在的 generation 记为 `degraded`，不自动重复执行。输出存在且可验证时才允许恢复为 `succeeded`。
- `run.lock` 和状态写入均按 generation 隔离，API 重试会创建新 generation，不覆盖旧状态或产物。

## API 投影

API 只读取 runner 的清洗状态，映射至已有 `TranslationRun` 字段；产物复制前验证路径位于对应 generation 目录，随后以不透明 Artifact ID 授权下载。服务器路径、PID、argv 和原始 runner 日志不返回给浏览器。
