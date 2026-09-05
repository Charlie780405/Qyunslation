# PLAN-014 Office/DOCX 预览

## 目标

Gradio `PDF()` 无法渲染 Word，导致右侧预览白屏。非 PDF 改为 HTML 预览。

## 子计划

| 文件 | 内容 |
|------|------|
| 补丁 | `scripts/apply-pdf2zh-office-preview.py` |
| sidecar | `scripts/apply-pdf2zh-office-route.py` 旁路下载 html |
| 验收 | `scripts/verify-plan-014.sh`、WT-014 |

## 验收

```bash
bash scripts/verify-plan-014.sh
systemctl --user restart pdf2zh.service
```
