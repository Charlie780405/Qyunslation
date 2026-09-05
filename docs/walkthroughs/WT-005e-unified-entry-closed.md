# WT-005e 统一入口 — 已 superseded

**日期：** 2026-08-23  
**状态：** 已被 [WT-005e-unified-entry.md](WT-005e-unified-entry.md) 取代

早期门禁评估为「关闭」；用户后续明确要求「在 PDF 界面翻译、不单开域名」后已启用。

**现网：**

- 公网入口：**`https://translate.qyunsgen.com`**（:7860 pdf2zh）
- Word/图片：pdf2zh GUI 内路由到 sidecar `:8010`
- 旧域名 `office.qyunsgen.com` → 301 到 `translate.qyunsgen.com`（Caddy 保留兼容）
