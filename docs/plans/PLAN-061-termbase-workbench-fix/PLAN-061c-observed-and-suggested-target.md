# PLAN-061c：实际译法与 AI 推荐译法

> 父计划：[PLAN-061](./README.md)

- `align_observed`：L1 词库 preferred 出现在译文 → L2 源词在含 CJK 的译文中逐字保留 → L3 同比例窗口最长 CJK（短整句不猜）。
- 显式 span 的 `observed_target` 优先于窗口猜测。
- `suggest_targets`：只处理 window/none；整篇一次 `get_provider()`；幻觉片段不得写入实际译法；磁盘缓存；`QYUNSLATION_TERM_SUGGEST=0` 可关。
- `bridge._extract_candidates` 先攒齐再建议再入库。批量确认白名单仍为 `{exact, alias}`。
