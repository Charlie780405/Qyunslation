# PLAN-019 高级选项吸底 + 图片翻译下载与中译英

## 目标

1. 左栏上传文件后翻译/取消与高级选项吸底固定，始终可见。
2. 修复图片翻译成功却报「翻译完成但无可用下载」。
3. PDF / DOCX / 图片三种格式支持中英双向互译。

## 根因摘要

- **A**：上传后左栏高度溢出，按钮被推到可视区外；改 sticky 吸底。
- **B**：`_build_export_map` 把 `ImageOverlayWorkflow` 写在 `DocxExportable` 分支内，Protocol 永远 False。
- **C**：DOCX/图片 GUI 补丁写死 `to_lang=简体中文`；图片链路 `del to_lang` + 固定 prompt；PDF 已具备双向，需实测。

## 改动

| 文件 | 内容 |
|------|------|
| `qyunslation/server/core.py` | export_map 独立 image 分支；ImageOverlayConfig 传 to_lang |
| `qyunslation/extensions/image_translate.py` | prompt 按 to_lang |
| `qyunslation/workflow/image_overlay_workflow.py` | Config.to_lang |
| `scripts/apply-pdf2zh-office-route.py` | 去硬编码 + 语言映射 + 去重 |
| `scripts/apply-pdf2zh-left-dock.py` | sticky 吸底 |
| `scripts/pdf2zh.service` | 末位 ExecStartPre |
| 验收 | `scripts/verify-plan-019.sh`、`docs/walkthroughs/WT-019-adv-dock-image.md` |

## 验收

```bash
bash scripts/verify-plan-017.sh
bash scripts/verify-plan-017b.sh
bash scripts/verify-plan-018.sh
bash scripts/verify-plan-019.sh
systemctl --user restart qyunslation-office.service pdf2zh.service
```
