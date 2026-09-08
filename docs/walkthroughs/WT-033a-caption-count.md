# WT-033a 题注空格与计数契约

> 计划：[PLAN-033a](../plans/PLAN-033-pdf-fidelity/PLAN-033a-caption-count.md)
> 日期：2026-09-09
> 验收门：`bash scripts/verify-plan-033a.sh` → `SUMMARY: PASS fail=0`

## 做了什么

`caption_anchors` 原先对 block 内 span 做 `"".join()`。ScienceDirect 把 `Table 2` 与 `Response...` 分成两个 span，拼成 `Table 2Response...`，正则要求数字后为空格或标点，Table 2–4 整表失踪。

改为 `join_span_texts` / `block_plain_text`：缺词界时补空格；逗号/连字符后、小数点后数字不加空格。扫描器版本 `1.1.0` → `1.2.0`，已有 `ManifestStore.get_current` 会丢掉旧缓存。

仓内合成夹具 `caption-span-gap.pdf` 复现无空格拼接，是主门。11 页 Elsevier PDF **不入库**，本机在场时作加强回归。

## 验证

| # | 结果 |
| --- | --- |
| V1 `Table 2Response` 正则仍为 None | 通过 |
| V2 合成夹具 table 2/3/4，正文 `see Table 4` 不计第二份 table 4 | 通过 |
| V3 外部样本 Figure=2 / Table=4 | 通过（本机样本在场，hash 吻合） |
| V4 caption + catalog | 14 passed |
| V5 scanner 1.2.0 | 通过 |
| 相邻结构套件 | 76 passed（column / unnumbered / table / figure / prescan） |

## 未做

033c 已接着做完，见 [WT-033c](./WT-033c-original-immutable.md)。
