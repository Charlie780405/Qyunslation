# WT-050a：真实运行时基线

日期：2026-09-13  
对应 [PLAN-050a](../plans/PLAN-050-qyunslation-ui-ux/PLAN-050a-runtime-baseline.md)

## 唯一施工面

**Gradio `pdf2zh_next --gui` 监听 `:7860`**，由 user unit `pdf2zh.service` 启动，`ExecStartPre` 为 `apply-pdf2zh-*.py` 链。

| 证据 | 结果 |
| --- | --- |
| `ss` | `0.0.0.0:7860` → `pdf2zh_next`；`127.0.0.1:8010` → sidecar |
| 未登录 `/` | HTTP 200，约 2.4KB，标题「Qyunslation 登录」 |
| 登录后 `/` | HTTP 200，约 599KB，`gradio-container`，标题「Qyunslation · 荃信翻译」 |
| DOM | `.qy-col-left` / `.qy-col-mid` / `.qy-col-right` / `.qy-prescan-bar` / `.qy-preview-src` / `.qy-preview-dst` |
| Vue | `frontend/dist` 不存在；登录后 HTML **无** Vue 根 |
| Caddy | `translate.qyunsgen.com` 兜底 7860；`/api/v1` → 8010 |

浏览器无障碍快照（登录后）：上传、当前文档、从…翻译 / 翻译为、文档类型、**翻译** / **取消**、高级选项；中央「原文」「译文」空态。

截图工具内 CJK 字体会糊，以 a11y 快照与 curl HTML 为准。

## 契约

[`docs/contracts/ui-runtime-050.md`](../contracts/ui-runtime-050.md)

## 本号未改

生产 UI、未重启服务（050a 完成定义：不改界面）。050b 起才打工作台补丁。
