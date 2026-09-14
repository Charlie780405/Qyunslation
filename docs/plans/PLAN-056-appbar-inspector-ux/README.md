# PLAN-056：应用栏方向开关 + 检查器/帮助可见性

> 状态：**完成**
> 类型：Gradio 工作台壳层收口（不新开 050）
> 依赖：PLAN-050（已完成）；施工面仍为 `pdf2zh_next --gui :7860`
> 验收：`bash scripts/verify-plan-056.sh`

## 文件索引

| 类型 | 文件 |
| --- | --- |
| 纲领 | [PLAN-056-appbar-inspector-ux.md](./PLAN-056-appbar-inspector-ux.md) |
| 056a | [PLAN-056a-appbar-direction.md](./PLAN-056a-appbar-direction.md) |
| 056b | [PLAN-056b-inspector-help.md](./PLAN-056b-inspector-help.md) |
| 056c | [PLAN-056c-verify-gate.md](./PLAN-056c-verify-gate.md) |

Walkthrough：[WT-056-appbar-inspector-ux.md](../../walkthroughs/WT-056-appbar-inspector-ux.md)

## 执行规则

1. 先入列文档，再改 [`scripts/apply-pdf2zh-050-workbench.py`](../../../scripts/apply-pdf2zh-050-workbench.py)（文件名保留）。
2. 禁止写入 Gradio `js=` / `head=`。
3. 部署只用 `bash scripts/deploy-translate-stack.sh`。
