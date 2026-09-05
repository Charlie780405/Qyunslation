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

## 部署

- **时间：** 2026-09-05
- **main：** `f522368`（merge PLAN-014）
- **动作：** 同步 `pdf2zh.service` → `systemctl --user restart pdf2zh`；`verify-plan-014.sh` 13/13
- **入口：** https://translate.qyunsgen.com
