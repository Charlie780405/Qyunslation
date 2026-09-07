# PLAN-029c 验收与交付

## 交付物

| 文件 | 说明 |
|---|---|
| `scripts/md_tables.py` | 期刊 Markdown 表注入 |
| `scripts/verify-plan-029.sh` | 自动化验收 |
| `docs/walkthroughs/WT-029-table-structuring.md` | 交付记录 |

## 断言点

```bash
bash scripts/verify-plan-029.sh
```

1. Hermes `lit_tables` 跨仓 import
2. 期刊样本 ok 表注入 + 数值零改写
3. pending/unstructured 静默跳过
4. 幻灯 17/17 判型 + profile 8→12
5. 期刊矢量仍为 12（PLAN-028 回归）
6. `export_md_docx` 两条路径挂载

## 样本

- 期刊：`41467_2024_Article_53384.pdf`（Nature Communications）
- 幻灯：`QX027N QnA-2026.08.19-临床.pdf`（16:9，17 页）
