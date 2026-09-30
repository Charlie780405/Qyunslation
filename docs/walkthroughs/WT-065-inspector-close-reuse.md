# WT-065：专业词汇检查器关闭与入库复用说明

> 计划：[PLAN-065](../plans/PLAN-065-inspector-close-reuse/README.md)

## 工程验证记录

| 项目 | 结果 |
| --- | --- |
| 「关闭」隐藏 Gradio 检查器 | 已实现；专项测试待跑 |
| JS 抽屉 `data-open=false` 不占屏 | 已实现；专项测试待跑 |
| Esc 点顶部关闭 | 已实现 |
| 入库文案说明下一篇硬注入 | 已实现 |
| 浏览器关面板后可下载 | 待部署后补证 |

## 已执行本地命令

```bash
bash scripts/verify-plan-065.sh
```

## 部署记录

待 `deploy-translate-stack.sh` 后回填 SHA 与服务状态。

## 浏览器实点（LIVE）

1. 打开专业词汇检查器
2. 点「关闭」或 Esc，遮罩消失
3. 能点下载 / 预览 / 再译
4. 面板文案可见「列表是候选」与「下一篇登录翻译将自动使用确认译法」
