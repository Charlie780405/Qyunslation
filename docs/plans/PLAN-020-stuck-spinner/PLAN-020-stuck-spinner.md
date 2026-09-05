# PLAN-020 上传/翻译永久转圈与静默失败

## 目标

1. 消除「点了没反应、一直转圈、无任何提示」这一类静默失败。
2. 修掉两处确定会触发该状态的术语表编码崩溃。
3. 让部署后旧页面不再复用过期的 `gradio_config` 组件树。
4. 去掉吸底 JS 的全局重排开销。

## 现场证据

| 时间 | 事实 |
|------|------|
| 15:15:02 / 15:39:59 | 用户两次上传，`/tmp/gradio` 只留下 upload 接口自身的 3 个 0 字节临时文件 |
| 同期 | `pdf2zh.service` 无 `Processing file`，office sidecar 无请求 |
| 15:29:26–15:29:43 | 同一张 576KB 图，真实浏览器公网实测 17s 完成，译文与下载均正常 |
| 15:32:16 | 空 CSV 触发 `on_glossary_file_change` → `RuntimeError: coroutine raised StopIteration` |
| 15:25:58 | 非文本术语表触发 `_build_glossary_list` → `TypeError: decode() argument 'encoding' must be str, not None` |

成功上传同样不打日志，故「零日志」不能证明回调没跑；结合客户端表现，判定为**事件回执未被前端正确应用**。

## 根因

- **主因 · 预览载荷过大**（浏览器 Performance API 实测坐实）：
  `_qy_preview_payload` 把图片 base64 内联进 HTML，590KB 的图膨胀成 787105 字符，
  再作为组件值走 SSE 下发。原文一份、译文一份，`upload` 与 `change` 事件各推一次。
  复现记录：单条 `queue/data` 传输 789855 字节耗时 **27s**（≈29KB/s），
  其后 `queue/join` 从 550ms 劣化到 **16.6s**，累积即用户看到的 201.6s。
  链路快时（本机 API、公网首测）不复现，故此前误判为后端问题。
  DOCX 经 mammoth 转换同样内联 data URI，问题同源。

- **A 术语表编码**：`chardet.detect()` 对空文件/无法识别内容返回 `encoding=None`。
  `bytes.decode(None)` 抛 `TypeError`；生成器里则冒成 `StopIteration`。两处 `except`
  均未覆盖，异常在 `build_ui_inputs` 阶段逃逸，早于任何日志。
- **B 静默失败**：上述异常使 Gradio 返回 `success=False` 且 error 为空，
  前端只弹一个无文案的 "Error"，且**不解除加载态**，计时器无限累加。
- **C 陈旧组件树**（次要，防御性）：`index.html` 无 `cache-control`/`ETag`/`Last-Modified`，
  而 `window.gradio_config`（组件树 + 事件索引）内嵌其中。服务重启换代后仍开着的
  旧页面 fn_index 会与服务端错位。
- **E 空态提示挥之不去**：隐藏规则里写了嵌套 `:has()`
  （`:has(> .pdf-preview-fixed:not(.hidden):has(canvas))`）。`:has()` 内不允许再套
  `:has()`，选择器组中有一个非法成员会导致**整条规则被丢弃**，于是预览已渲染、
  下方仍挂着一个空框。JS 里 `element.matches()` 对单个选择器返回 true，
  但 `getComputedStyle(el,'::after').display` 仍是 `flex`，可据此确诊。

- **D 吸底 JS 开销**：400ms `setInterval` 叠加监听整个 `body` 的 MutationObserver，
  回调内 `getBoundingClientRect()` 强制同步重排；页面内联 ~790KB base64 图片。

## 改动

| 文件 | 内容 |
|------|------|
| `scripts/apply-pdf2zh-preview-url.py`（新） | 预览改走 `/gradio_api/file=`；DOCX 的 data URI 落盘外置。载荷 787105 → 373 字节 |
| `scripts/apply-pdf2zh-glossary-encoding.py`（新） | 两处 chardet 兜底：None → utf-8-sig → gbk → latin-1；空文件给明确提示；异常收敛为 `gr.Error` |
| `scripts/apply-pdf2zh-no-store.py`（新） | 给 `/` 与 `/config` 加 `Cache-Control: no-store`，旧页面不再复用过期组件树 |
| `scripts/apply-pdf2zh-left-dock.py` | 去掉 body MutationObserver 与 400ms 轮询，改 ResizeObserver 只观察折叠面板 |
| `scripts/apply-pdf2zh-stale-guard.py`（新） | app_id 漂移检测 + 回执丢失检测，弹出明确文案与刷新入口 |
| `scripts/apply-pdf2zh-css-has-fix.py`（新） | 嵌套 `:has()` 改写为后代组合器，空态提示恢复可隐藏 |
| `scripts/pdf2zh.service` | 追加新补丁的 ExecStartPre |
| 验收 | `scripts/verify-plan-020.sh`、`docs/walkthroughs/WT-020-stuck-spinner.md` |

## 验收

```bash
bash scripts/verify-plan-017.sh
bash scripts/verify-plan-017b.sh
bash scripts/verify-plan-018.sh
bash scripts/verify-plan-019.sh
bash scripts/verify-plan-020.sh
systemctl --user restart pdf2zh.service
```

## 实测结果

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 单次预览事件载荷 | 789855 B / 27.0s | 3031 B / 0.7s |
| 图片中译英端到端（不含上传） | — | 20s |
| 空态提示 | 预览已出仍挂空框 | `display: none` |

## 遗留：上传带宽

浏览器实测客户端→服务端上传仅 **11–13 KB/s**（两次 500KB 上传耗时 39.9s / 45.6s），
576KB 图片单是上传就要 45–70s。此为链路本身（Cloudflare 入口 SIN → Vultr）的
吞吐，不在本次改动范围内；本计划消除的是每次操作额外附加的约 1.6MB 可避免流量。
