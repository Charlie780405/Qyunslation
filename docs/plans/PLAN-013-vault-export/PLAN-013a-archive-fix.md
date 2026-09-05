# PLAN-013a 落库链路修复

## 改动

1. `GroupStateDB` 改为长连接（或 `contextlib.closing`），消除 fd 泄漏
2. `ArchiveIndex._connect` 用 `closing` 包裹
3. `_OUTPUT_SUFFIX_RE` / `output_group_key` 识别 `letter-mono`、`.zh.md`、`.zh.docx`，剥掉 `.hpd-ocr` / `.no_watermark.<lang>`
4. watcher 同组附带原文 `{stem}.pdf` 上 MinIO（role=`source`）
5. `pdf2zh-archive-watch.service` 加 `LimitNOFILE=4096`
6. `--once` 回填积压 session

## 验收

- watcher 进程 fd 数稳定（不逼近 1024）
- letter-mono / BabelDOC mono 均可入库
- Vault 出现新 DT- 条目
