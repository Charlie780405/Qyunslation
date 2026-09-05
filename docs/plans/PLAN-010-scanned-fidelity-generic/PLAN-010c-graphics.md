# PLAN-010c：图形区检测与译后回插

## 目标

原文 logo/印章/图形按原位出现在译文页；logo 区不叠中文。

## 改动

- `scripts/graphic_regions.py` / `scripts/graphic_reinsert.py`
- `hpd_ocr` letter：检测 → 丢 suppress 行 → merge → deoverlap
- GUI / bench 译后回插

## 验收

`bash scripts/verify-plan-010.sh after-c`
