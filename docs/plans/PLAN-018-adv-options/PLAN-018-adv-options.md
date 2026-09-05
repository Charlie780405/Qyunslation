# PLAN-018 高级选项展开修复与位置下移

## 目标

1. 修复左栏 `flex-wrap: wrap` 导致高级选项展开后内容与翻译/取消按钮「消失」。
2. 将「高级选项」手风琴移到翻译/取消按钮下方，向下展开；内容过高时内部纵向滚动。
3. 按取舍隐藏「保存设置」按钮；其余高级项（页码范围、术语表、水印、忽略缓存、仅输出翻译页、界面语言）保留可见。

## 根因

Gradio 规则给子项加了 `flex-wrap: wrap`。左栏列向 flex 高度锁死后，展开手风琴溢出会换到第二列，落到左栏可视区外。

## 改动

| 文件 | 内容 |
|------|------|
| 补丁 | `scripts/apply-pdf2zh-adv-options.py`（叠在 layout-polish 之后） |
| 服务 | `scripts/pdf2zh.service`（末位 ExecStartPre） |
| 验收 | `scripts/verify-plan-018.sh`、`docs/walkthroughs/WT-018-adv-options.md` |

## 验收

```bash
bash scripts/verify-plan-017.sh
bash scripts/verify-plan-017b.sh
bash scripts/verify-plan-018.sh
systemctl --user restart pdf2zh.service
```
