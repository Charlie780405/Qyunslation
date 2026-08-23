# PLAN-005b：可编辑 Word sidecar

## Task B1 — office.env

强制：35b、temp=0、concurrent=4、关自动术语、`/no_think`。

## Task B2 — user systemd

`qyunslation-office.service` → `127.0.0.1:8010`。`.doc` 用 LibreOffice 转 docx。

## Task B3 — 入口

Caddy 新增 `office.qyunsgen.com` → :8010；homepage 第二卡片。不改 translate→7860。

## Task B4 — SLO

~200 段 ≤8 min；样式保留；无漏段。

## 回滚

`disable --now qyunslation-office`；Caddy 删 office 块后 reload。
