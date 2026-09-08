# WT-030c：统一语义扫描与题注驱动 Figure/Table 归并

> 状态：**完成**
> 日期：2026-09-08
> 对应计划：[PLAN-030c](../plans/PLAN-030-semantic-layout-translation/PLAN-030c-unified-semantic-scan.md)
> 范围：PDF 题注扫描、manifest 装配、预扫描/UI 语义计数、纯表页 fail-closed 执行防护；未部署、未重启 pdf2zh

## 一、交付结果

`QY030-SEM-001` 已转绿。用户主计数改为题注编号去重，不再把位图候选与矢量聚类相加。

- 题注检测内联到 `qyunslation/structure/captions.py`，生产包不再依赖 `/home/dev/Hermes/scripts`。
- `PdfStructureScanner` 产出可校验的 Manifest v1；同一 PDF 两次扫描的 `manifest_id` 与 object ID 稳定。
- `find_figure_regions` 实现规则 A–D；`find_safe_vector_figures` 原签名保留给无题注页与幻灯。
- 预扫描摘要改为「共 N 张插图，其中 M 张将 OCR 嵌字翻译；另有 K 处表格，按文字层翻译。」
- 策略 B 非幻灯页改调 `find_figure_regions`；纯表页返回空区域，禁止 OCR 覆盖表格。

ljae439 实现注记：Figure 1–5 主要是位图，有 figure 题注的页必须合并 `get_image_info` bbox。Table 1 与 Table 2 同在第 5 页（一个 `pure_table` 页）；Table 3 与 Figure 4 同页（`mixed`）。断言是表题注集合 `{1,2,3}`，不是三个独立纯表页。

## 二、真实样本

| 样本 | 路径 | SHA-256 | 语义 / UI |
| --- | --- | --- | --- |
| ljae439 | `tests/fixtures/structure/reference/ljae439.pdf` | `8e9893b21e6aab4a057ba730eba40f6a9bd696f3538ed05ffc3fc5eb8470f10c` | Figure 1–5、Table 1–3；「共 5 张插图，其中 5 张将 OCR 嵌字翻译；另有 3 处表格，按文字层翻译。」 |
| Nature Communications | `tests/fixtures/structure/reference/nature_comm_53384.pdf` | `566f97dd5c43e3a8c5729c25ad5004fe9e6995a6be4ad95fe64c9f18b5e37723` | Figure 1–7、Table 1–3；「共 7 张插图，其中 7 张将 OCR 嵌字翻译；另有 3 处表格，按文字层翻译。」p4/p5/p9 纯表页零 OCR 区域 |
| 幻灯（不入仓） | `/home/dev/pdf2zh/pdf2zh_files/57114032-8727-41f9-b826-b5ff40fcf733/QX027N QnA-2026.08.19-临床.pdf` | — | PLAN-029b profile 仍为 12；`find_figure_regions` legacy 为 8 |

生产包 `qyunslation/**/*.py` 不含上述文件名或知识库 locator。

## 三、验证证据

`bash scripts/verify-plan-030c.sh`：

```text
PASS: PLAN-030c modules compile
PASS: focused caption, region, scan, guard, and baseline tests
PASS: ljae439 and Nature semantic gold samples
EXPECTED_RED: only PLAN-030g PPT image execution remains XFAIL
EXPECTED_RED: --runxfail proves the exact PLAN-030g PPT gap still fails
PASS: full pytest regression excluding recorded archive failures
EXPECTED_RED: three unchanged pre-PLAN-030 archive naming failures
SUMMARY: PASS expected_red=3 blocked=0 fail=0
```

`pytest -q tests/structure --no-cov -rxX`：`145 passed, 1 xfailed`（仅 `QY030-PPT-001`）。

`bash scripts/verify-plan-028.sh` 与 `bash scripts/verify-plan-029.sh` 均为 PASS。`git diff --check` 无空白错误。archive 三个既有失败精确不变。

### 028/029 断言变更（PLAN-030c 口径）

| 脚本 | 旧断言 | 新断言 |
| --- | --- | --- |
| `verify-plan-028.sh` | `vector_count == 12`、`table_count >= 19` | `figure_caption_count == 7`、`table_caption_count == 3` |
| `verify-plan-029.sh` | `journal vector still 12` | `journal translatable == 7`；legacy `find_safe_vector_figures` 几何合计仍回归为 12 |

## 四、部署边界

本阶段不重启 pdf2zh。`verify-plan-028.sh` 的幂等检查会调用 `apply-pdf2zh-prescan.py`：首次因 HELPER 文案更新写入了 site-packages `gui.py`，第二次已报 `already patched`。进程内仍是旧 helper，用户可见文案要等单独 WT 重启后才会变成语义计数。

## 五、下一阶段边界

PLAN-030d 消费本阶段 manifest，做 PDF 正文/Figure/Table 检测—翻译—回写闭环。不在 030c 范围：DocLayout、DOCX/PPTX 语义对象、跨格式对账、pdf2zh 服务重启。
