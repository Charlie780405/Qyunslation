# pdf2zh GUI 补丁顺序（PLAN-030id）

与 [`scripts/pdf2zh.service`](../../scripts/pdf2zh.service) `ExecStartPre` 链 1:1 对应。升级或回滚后须按此顺序重跑各 `apply-pdf2zh-*.py`。

| 序 | 脚本 | 负责 PLAN |
| --- | --- | --- |
| 1 | `apply-pdf2zh-throughput.py` | 吞吐 |
| 2 | `apply-pdf2zh-brand.py` | 031c 品牌 |
| 3 | `apply-pdf2zh-hpd.py` | HPD OCR |
| 4 | `apply-pdf2zh-docimg.py` | 027 嵌图 |
| 5 | `apply-pdf2zh-ocr-base.py` | OCR 基线 |
| 6 | `apply-pdf2zh-office-route.py` | 005e sidecar 路由 |
| 7 | `apply-pdf2zh-docprofile.py` | **030ia** 内容画像 |
| 8 | `apply-pdf2zh-downloads.py` | 下载区 |
| 9 | `apply-pdf2zh-office-preview.py` | Office 预览 |
| 10 | `apply-pdf2zh-settings-inline.py` | 内联设置 |
| 11 | `apply-pdf2zh-dual-preview.py` | 双预览 |
| 12 | `apply-pdf2zh-layout-polish.py` | 021 布局 |
| 13 | `apply-pdf2zh-adv-options.py` | 高级选项 |
| 14 | `apply-pdf2zh-left-dock.py` | 左栏 |
| 15 | `apply-pdf2zh-prescan.py` | **030ib** 预扫/manifest |
| 16 | `apply-pdf2zh-stale-guard.py` | 陈旧任务 |
| 17 | `apply-pdf2zh-sse-recover.py` | SSE 恢复 |
| 18 | `apply-pdf2zh-preview-url.py` | 预览 URL |
| 19 | `apply-pdf2zh-glossary-encoding.py` | 术语编码 |
| 20 | `apply-pdf2zh-no-store.py` | 无存储 |
| 21 | `apply-pdf2zh-css-has-fix.py` | CSS |
| 22 | `apply-pdf2zh-viewer.py` | 021 查看器 |
| 23 | `apply-pdf2zh-preview-dpi.py` | 预览 DPI |
| 24 | `apply-pdf2zh-fidelity-033h.py` | 033h 保真 |

部署前自检：

```bash
bash scripts/verify-plan-030i.sh
python3 scripts/check-babeldoc-fidelity-033l.py
```
