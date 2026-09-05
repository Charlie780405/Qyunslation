# PLAN-008a：完整性度量

`scripts/bench-scanned-page1.sh` 的 `measure_pdf_fonts` 增加：

- `truncated_blocks`：块尾无句末标点，且下一块像续句（英文小写或中文半句收尾字）
- `orphan_fragments`：`len<=4` 且不是页码/编号/「此致」

V5 基线写入 `docs/perf/baseline-008a.json`：OCR 层 truncated=6；译文 truncated=2、orphan=2（`‑` / `FDA‑`）。
