# PLAN-005b：可编辑 Word sidecar

## Task B1 — office.env

强制：35b、temp=0、concurrent=4、关自动术语、`/no_think`。

## Task B2 — user systemd

`qyunslation-office.service` → `127.0.0.1:8010`。`.doc` 用 LibreOffice 转 docx。

## Task B3 — 入口

Sidecar 监听 `:8010`（本机）；公网仍用 `translate.qyunsgen.com` → :7860，Word/图片经 pdf2zh 内路由到 sidecar。旧 `office.qyunsgen.com` 301 到 translate。

## Task B4 — SLO

~200 段 ≤8 min；样式保留；无漏段。

## 回滚

`disable --now qyunslation-office`；pdf2zh 去掉 office-route 补丁。
