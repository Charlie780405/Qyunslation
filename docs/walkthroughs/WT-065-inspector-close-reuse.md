# WT-065：专业词汇检查器关闭与入库复用说明

> 计划：[PLAN-065](../plans/PLAN-065-inspector-close-reuse/README.md)

## 执行摘要

`fa6c50e` 已推 `origin/main`。现场 `gui.py` 含 `_qy060_close_inspector`、抽屉 `data-open=false` 隐藏，以及「下一篇登录翻译将自动使用确认译法」。`verify-plan-065.sh`：`PASS fail=0 blocked=0`。

## 工程验证记录

| 项目 | 结果 |
| --- | --- |
| 「关闭」隐藏 Gradio 检查器 | PASS；`gui.py` 已写入 `_QY060_CLOSE_OUT` |
| JS 抽屉 `data-open=false` 不占屏 | PASS；050/060 CSS 均有 `display: none` |
| Esc 点顶部关闭 | PASS；050 JS 点 `#qy060-insp-close` |
| 入库文案说明下一篇硬注入 | PASS |
| `verify-plan-065.sh` | PASS fail=0 blocked=0 |
| 浏览器关面板后可下载 | BLOCKED：重启后需登录；未在对话中使用账号口令点译后面板 |

## 已执行本地命令

```bash
bash scripts/verify-plan-065.sh
# SUMMARY: PASS fail=0 blocked=0
git push origin main   # fa6c50e
systemctl --user daemon-reload
bash scripts/deploy-translate-stack.sh
# sidecar /service/image-translate-health 无凭证 → 401，脚本 FAIL
# pdf2zh.service + qyunslation-office.service 均为 active
```

## 部署记录

- 提交：`fa6c50e`（`merge: PLAN-065 inspector close and term reuse copy`）
- 远程：`origin/main` 已含该 merge
- GUI：ExecStartPre 已把 050/060 补丁打进 site-packages `gui.py`
- `pdf2zh.service`：active（`:7860` 登录页 200）
- `qyunslation-office.service`：active；健康检查匿名 401（部署脚本未带凭证，指纹门未跑）
- 登录页无检查器遮罩

## 浏览器实点（LIVE）

1. [x] 打开 `http://127.0.0.1:7860/` 为登录页，无全屏检查器
2. [ ] 登录后打开专业词汇，点「关闭」或 Esc，遮罩消失
3. [ ] 能点下载 / 预览 / 再译
4. [ ] 面板文案可见「列表是候选」与「下一篇登录翻译将自动使用确认译法」

未登录项留给现场手测。
