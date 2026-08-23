# PLAN-005d：归档

## Task D1 — office_out

`/home/dev/pdf2zh/office_out/` → 同一 `index.db` / MinIO / Vault `DT-2026-*`。

分组：`*.zh.docx` / `*.zh.png`，不误吞 mono/dual.pdf。

## Task D2 — 扫描 PDF

仍走 pdf2zh watcher。

## 回滚

停 office watcher；已入库 DT 不删。
