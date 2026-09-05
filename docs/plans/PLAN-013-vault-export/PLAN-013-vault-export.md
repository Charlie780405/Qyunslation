# PLAN-013 翻译产物落库与导出增强

## 一句话目标

修复已停摆的 Hermes Vault 落库链路，扩展为「原文 + 译稿 + Markdown/DOCX」全量入库，并精简 Gradio 下载区为「仅译稿 / 原文+译稿」两档加格式选择。

## Out of Scope

- 不改 Vue DocuTranslate 主 UI（本 PLAN 针对 pdf2zh Gradio）
- 不把翻译产物改走 LIT- 文献体系
- 不把原文 PDF 复制进 Vault git（仅 MinIO）

## 子计划

| 子计划 | 内容 |
|--------|------|
| [013a](PLAN-013a-archive-fix.md) | sqlite fd 泄漏修复、分组正则、原文 MinIO 归档、积压回填 |
| [013b](PLAN-013b-md-docx-export.md) | 扫描件 debug2md + 普通 PDF ConverterHpd 解析再翻译 |
| [013c](PLAN-013c-downloads-ui.md) | Gradio 下载区精简补丁 |
| [013d](PLAN-013d-vault-verify.md) | Vault 笔记增强、verify、WT |

## 验收

```bash
bash scripts/verify-plan-013.sh
```

详见 [WT-013](../../walkthroughs/WT-013-vault-export.md)。
