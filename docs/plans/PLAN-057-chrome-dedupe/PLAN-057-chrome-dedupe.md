# PLAN-057：去掉方向与帮助/检查器双入口

> 状态：**完成**
> 日期：2026-09-14
> 依赖：PLAN-056（已关）；不重开 056
> 验收门：`bash scripts/verify-plan-057.sh`
> Walkthrough：[WT-057](../../walkthroughs/WT-057-chrome-dedupe.md)

## 一句话

顶栏保留方向/帮助/检查器为唯一用户面；隐藏左栏语言行与同名 Accordion 标题条；覆盖 019 吸底锁高，使专业模式「高级选项」可滚、下拉可弹出。

## 子计划

| ID | 交付 |
| --- | --- |
| [057a](./PLAN-057a-hide-lang-panels.md) | 藏 lang-row；帮助/检查器改 `visible=False` 面板 |
| [057b](./PLAN-057b-adv-scroll.md) | 覆盖 left-dock `max-height`；下拉不被裁切 |
| [057c](./PLAN-057c-verify-gate.md) | verify-057 + 部署 + 浏览器点验 |

## Out of Scope

- 专业模式再露全语种下拉
- 050e 对象编辑器；重写 019 吸底交互
- Vue `frontend/`

## 完成定义

- [x] 纲领 + 057a/b/c + README；plans 索引有 057
- [x] 左栏无「从…翻译/翻译为」；无常驻「帮助/检查器」标题条
- [x] 专业→展开高级→可滚到水印/术语；下拉完整弹出
- [x] `verify-plan-057.sh` PASS；强制刷新不白屏
