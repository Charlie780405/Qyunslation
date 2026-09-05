# PLAN-012：扫描书信叠字 / 字号 / 并行 / 进度

修生产正式书信流水线：英文当插图贴回、疏页 13pt 偏大、OCR 同步卡住进度条；提速靠翻译并行 + 持久缓存。不改泰州 HPD。

## 根因摘要

| 症状 | 根因 |
| --- | --- |
| 中英叠字 | `graphic_regions` 吃了 pack/clamp 后的排版盒，漏擦英文行带被标 `graphic` 贴回 |
| 第 12 页字大 | `_flow_plan` 疏页升 13pt |
| 进度条卡 | `ocr_pdf_with_hpd` 在 async handler 同步跑 |
| 慢 | 串行译页 + 无磁盘缓存；HPD 并发实测更慢（默认 workers=1） |

## 实现

| 项 | 做法 |
| --- | --- |
| `hpd_ocr.py` | 擦除用 `raw_boxes ∪ cleaned`；预取架构 + `QYUNSLATION_HPD_WORKERS`（默认 1） |
| `graphic_regions.py` | `pad_pt=3.5`；`aspect>5 && h<60` 丢弃 |
| `graphic_reinsert.py` | `kinds=` 过滤；letter 默认 logo/stamp |
| `kv_reinsert.py` | 正文锁 12pt / 章节 14pt；LEAD_MAX 1.90 / GAP_MAX 26 |
| `letter_pipeline.py` | 按页并行 + sha1 磁盘缓存；`missing_zh` 只告警；`.warnings.json` |
| `apply-pdf2zh-docprofile.py` | OCR / 翻译均 `run_in_executor` + 进度泵 |
| Skill | 铁律 13–18；pitfalls 15–19 |

## 验收

```bash
bash scripts/verify-plan-012.sh
```

端到端（已有 debug）：第 2 页 `imgs=2` 且无英文句；信纸第 12 页 `body=12.0`。

部署：`systemctl --user restart pdf2zh.service`；`:7860` 200。
