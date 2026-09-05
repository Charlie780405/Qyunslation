# PLAN-015 翻译进度可见性与一屏布局

## 目标

Word 翻译时进度条不可见（绑在被隐藏的 PDF 预览上）；首页左右栏过短。改为双预览绑定进度，并锁一屏内滚。

## 子计划

| 文件 | 内容 |
|------|------|
| 补丁 | `scripts/apply-pdf2zh-office-preview.py`（进度 + 布局 CSS/锚点） |
| docprofile | `scripts/apply-pdf2zh-docprofile.py`（`allow_custom_value=True`） |
| 验收 | `scripts/verify-plan-015.sh`、WT-015 |

## 验收

```bash
bash scripts/verify-plan-015.sh
systemctl --user restart pdf2zh.service
```
