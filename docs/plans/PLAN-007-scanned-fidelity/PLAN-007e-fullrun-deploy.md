# PLAN-007e：全量验收与部署

## Task E1 — 20 页全量

确认 `ocr_workaround` 下信头/签名底图存活；不达标 → 决策门升级栅格渲染器。

## Task E2 — mono 空包

排查 `all_mono_translations.zip` 22 字节空包。

## Task E3 — verify

`scripts/verify-plan-007.sh [baseline|after-a|after-b|after-c|after-d]`

## Task E4 — 文档与部署

WT-007；restart `pdf2zh.service`；精确 commit + push。

## 验收

- verify after-d 全绿
- 公网复现一对一；`verify-plan-005.sh after-d` 仍 30/30

## 回滚

子计划逆序 revert。
