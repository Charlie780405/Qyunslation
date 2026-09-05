# PLAN-015b 布局收敛与空态、版权条

## 目标

收掉满屏灰块：左栏控件回归自然高度、右栏空态细描边提示、底部荃信生物版权通栏。

## 根因

- `gr.Group` 灰底被 `height:100%` 撑满
- 左栏 Gradio `flex: 1 0 auto` 在满高列内把控件撑开
- `.qy-col-right > div` 通配强制 `display:flex`，隐藏预览组件变空盒

## 改动

| 文件 | 内容 |
|------|------|
| 补丁 | `scripts/apply-pdf2zh-office-preview.py`（CSS 重写 + `qy-page-footer`） |
| 验收 | `scripts/verify-plan-015.sh`、WT-015 |

## 验收

```bash
bash scripts/verify-plan-015.sh
systemctl --user restart pdf2zh.service
```
