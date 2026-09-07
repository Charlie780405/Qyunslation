# PLAN-028c 子计划：验证与交付

## 交付物

- `scripts/verify-plan-028.sh`
- `docs/walkthroughs/WT-028-prescan-parity.md`

## 验收脚本断言

1. `table_rects` / `tables=` 参数存在
2. `scan_pdf_tier3` / `format_tier3_summary` 存在
3. 论文 PDF 矢量 12、表格 ≥ 19、Tier-3 < 15s
4. `tables=` 共享不改变矢量判定
5. `apply-pdf2zh-prescan.py` 幂等
6. `gui.py` `compile()` 通过

## 部署

```bash
python3 scripts/apply-pdf2zh-prescan.py
bash scripts/verify-plan-028.sh
systemctl --user restart pdf2zh
```
