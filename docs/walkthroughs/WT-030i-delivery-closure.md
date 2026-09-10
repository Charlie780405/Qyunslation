# WT-030i：UI、可观测、兼容与交付收口

> 日期：2026-09-10
> 纲领：[PLAN-030i](../plans/PLAN-030-semantic-layout-translation/PLAN-030i-delivery-closure.md)
> 验收门：`bash scripts/verify-plan-030i.sh`

## 交付摘要

| 子计划 | 交付 |
| --- | --- |
| 030ic | `versions-030.lock`、`runtime_probe.py`、`verify-runtime-deps.py`、上传 fail-fast |
| 030ia | GUI 内容画像下拉、PPTX 模式控件、旧 doc_profile 桥接 |
| 030ib | 预扫 manifest JSON 下载、`GET /service/manifest/{sha256}` |
| 030id | 补丁顺序文档、030i verify 串 BabelDOC 签名门 |

## 验证

```bash
bash scripts/verify-plan-030i.sh
bash scripts/verify-plan-030h.sh   # 回归
python3 scripts/verify-runtime-deps.py
python3 scripts/check-babeldoc-fidelity-033l.py
```

## 部署

1. merge `main` 后于目标机 `git pull`
2. 按 [`pdf2zh-patch-order.md`](../contracts/pdf2zh-patch-order.md) 重跑补丁或 `systemctl --user restart pdf2zh.service`
3. sidecar：`systemctl --user restart qyunslation`（或等价）

## 回滚

- `git revert` 030i merge commit
- 重跑 pdf2zh.service ExecStartPre 链
- `verify-plan-030h.sh` 仍为结构回归门

## 视觉金样

见 [`visual-gold-030.md`](../contracts/visual-gold-030.md)。

| 项 | 值 |
| --- | --- |
| 批准 | 用户 2026-09-10 明确批准三项 |
| HEAD | `e19e686` |
| 缺口 | G-DOC-009 → closed（PLAN-038a） |
