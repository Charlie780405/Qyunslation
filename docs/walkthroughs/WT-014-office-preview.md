# WT-014 Office/DOCX 预览

## 目标

Word 译稿/原文在右侧预览可见，不再白屏。

## 根因

Gradio `PDF()` 只渲染 PDF；office sidecar 产出 `.docx` 被塞进该组件。

## 修复

| 项 | 说明 |
|----|------|
| 补丁 | `scripts/apply-pdf2zh-office-preview.py` → `preview_html` + mammoth/md/img |
| sidecar | 旁路下载 `html` 为 `{stem}.zh.html` |
| service | `ExecStartPre` 增加 office-preview |

## 验证

```bash
bash scripts/verify-plan-014.sh
systemctl --user restart pdf2zh.service
```

## 人工

1. https://translate.qyunsgen.com 上传 `.docx`，下拉选中后右侧应出现 HTML 正文
2. 翻译完成后选 `*_mono.docx` / `*.zh.docx` 仍可见正文
3. PDF 预览不回归
