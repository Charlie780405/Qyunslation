# PLAN-033a：题注空格与计数契约

> 状态：**已完成**（`verify-plan-033a.sh` PASS）
> 父计划：[PLAN-033](./PLAN-033-pdf-fidelity.md)
> 验收门：`bash scripts/verify-plan-033a.sh`

## 目标

`caption_anchors` 不再把 `Table 2` + `Response...` 拼成 `Table 2Response...`。计数以唯一 `semantic_id` 为准。

## 改什么

1. `qyunslation/structure/captions.py`：按行/span 拼接，缺词界时补空格。
2. `PDF_STRUCTURE_SCANNER_VERSION`：`1.1.0` → `1.2.0`（已有 `get_current` 会丢掉旧缓存）。
3. 合成夹具 `caption-span-gap.pdf`：同一 block 两个 span，无空格；另有正文 `see Table 4`。
4. 外部 11 页 PDF 可选加强回归，路径由环境变量或已知本机位置解析，**不复制进仓**。

## 不改

- Manifest schema、表格提取器、GUI 补丁、栏式判定。

## 验收

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | `table_caption_num("Table 2Response...")` 仍为 None（证明问题在拼接不在正则） | 通过 |
| V2 | 合成夹具 `caption_anchors` 得到 table 2/3/4，且无 table 4 来自 `see Table 4` | 通过 |
| V3 | 外部样本在场时 PdfStructureScanner 为 Figure=2、Table=4 | 通过或 skip |
| V4 | `tests/structure/test_caption_anchors.py` + catalog | 全绿 |
| V5 | `PDF_STRUCTURE_SCANNER_VERSION == "1.3.0"`（033b 框线回退后升版） | 通过 |
