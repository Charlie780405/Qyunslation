# PLAN-005 Word / 扫描 PDF / 图片嵌字

在 PLAN-003/004 质量口径上，补齐可编辑 Word、扫描 PDF（HPD）、图片嵌字。双栈：PDF→:7860；Word/图→:8010。

| 文件 | 作用 |
| --- | --- |
| `PLAN-005-office-image.md` | 纲领 |
| `PLAN-005a-scanned-pdf-hpd.md` | 扫描 PDF + HPD 正规化 |
| `PLAN-005b-word-sidecar.md` | Word sidecar :8010 |
| `PLAN-005c-image-overlay.md` | 图片嵌字 |
| `PLAN-005d-archive.md` | office 归档 |
| `PLAN-005e-unified-entry-gate.md` | 统一入口（默认不做） |

verify：`scripts/verify-plan-005.sh`（`baseline | after-a | after-b | after-c | after-d`）

WT：`docs/walkthroughs/WT-005-*.md`
