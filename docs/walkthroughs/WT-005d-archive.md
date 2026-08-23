# WT-005d office 归档

**日期：** 2026-08-23  
**状态：** 已部署

## 变更

- 译完复制到 `/home/dev/pdf2zh/office_out/`
- `office-archive-watch.py` + user unit → 同一 `index.db` / MinIO / Vault `DT-2026-*`

## 回滚

`systemctl --user disable --now office-archive-watch`。
