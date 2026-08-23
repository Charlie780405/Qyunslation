# WT-005a 扫描 PDF HPD

**日期：** 2026-08-23  
**状态：** 已部署（A-V4 通过；全量扫描译 SLO 记入 baseline notes）

## 变更

| 项 | 内容 |
| --- | --- |
| SSOT | `scripts/hpd_ocr.py` |
| 薄包装 | `/home/dev/pdf2zh/hpd_ocr.py` importlib 加载 SSOT |
| apply | `scripts/apply-pdf2zh-hpd.py`；失败 → `gr.Error` |
| unit | `ExecStartPre` 含 apply-pdf2zh-hpd |

## 实测

见 `docs/perf/baseline-005a.json`：page1 **不**走 HPD；Abstract 需 HPD；HPD health ok。

## 回滚

去掉 ExecStartPre HPD 行并重启 pdf2zh。
