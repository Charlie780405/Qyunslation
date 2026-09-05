# PLAN-017 双预览 2:4:4 布局与进度槽位

## 目标

翻译页改为 2:4:4：左设置、中原文预览、右译文预览；进度条落到右栏预览下方独立槽位；logo/版权横跨中右底部居中；去掉多余 File(s) 标题与侧栏占位。

## 改动

| 文件 | 内容 |
|------|------|
| 补丁 | `scripts/apply-pdf2zh-dual-preview.py` |
| 服务 | `scripts/pdf2zh.service`（末位 ExecStartPre） |
| 验收 | `scripts/verify-plan-017.sh`、`docs/walkthroughs/WT-017-dual-preview.md` |

## 验收

```bash
bash scripts/verify-plan-017.sh
systemctl --user restart pdf2zh.service
```
