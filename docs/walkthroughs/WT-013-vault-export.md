# WT-013 翻译产物落库与导出增强

## 目标

修复 Hermes Vault 落库停摆，扩展原文+译稿+Markdown/DOCX 入库，精简 Gradio 下载区。

## 已完成

| 项 | 结果 |
|----|------|
| sqlite fd 泄漏 | watcher 重启后 fd≈8（此前 1023） |
| letter-mono / zh.md 分组 | `FDA responses on PIND` → DT-2026-0016 |
| 积压回填 | DT-2026-0008 … 0016 |
| Vault 正文 | `body_source: translated_md`，原文仅 MinIO |
| 下载区补丁 | `_qy_downloads_ui`：仅译稿 / 原文+译稿 + PDF/MD/DOCX |
| Hermes indexer | 去掉函数内 `import json` 导致的 UnboundLocalError |

## 验证

```bash
bash scripts/verify-plan-013.sh
systemctl --user restart pdf2zh.service   # 加载 downloads 补丁
```

## 人工抽检

1. 打开 https://translate.qyunsgen.com ：下载区应只有内容单选 + 格式多选，ZIP 在折叠区
2. 勾选 Markdown 翻译一份扫描件信函 → session 出现 `{stem}.zh.md`
3. knowledge.qyunsgen.com 检索「PIND 会议」应命中 DT-2026-0016

## 部署

- `pdf2zh-archive-watch`：已重启（LimitNOFILE=4096）
- `pdf2zh`：需 restart 以加载 downloads GUI 补丁
- Hermes `rag/vault_indexer.py`：小修复（跨仓）
