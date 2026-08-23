# PLAN-005a：扫描 / 纯图 PDF（HPD）

## Task A1 — 入库 HPD

- `scripts/hpd_ocr.py`（SSOT）
- `/home/dev/pdf2zh/hpd_ocr.py` 薄 re-export
- `scripts/test_hpd_ocr_smoke.py` mock `_parse`

## Task A2 — apply 补丁

- `scripts/apply-pdf2zh-hpd.py` 幂等打 `gui.py` HPD 分支
- `pdf2zh.service` ExecStartPre 增加该脚本
- HPD 失败须 `gr.Error`，禁止 `ocr_workaround`

## Task A3 — 验收

`docs/perf/baseline-005a.json`：扫描墙钟、Successful/Fallback、文字 PDF 不误入 HPD。

## 回滚

去掉 ExecStartPre HPD 行。
