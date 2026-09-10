# PLAN-038：缺口总纲（登记、关联、随子计划关闭）

> 状态：**已完成**（038a–038g）
> 日期：2026-09-10
> 批准记录：用户确认 Cursor 计划「缺口总纲 PLAN-038」后实施
> 缺口 SSOT：[registry.md](./registry.md)
> 验收门：`bash scripts/verify-plan-038.sh`；总览 [WT-038](../../walkthroughs/WT-038-gap-closure.md)
> 编号纪律：**不空开 PLAN-034**（并入 038d/038e）；037 只补档不重做功能

## 一、目标

把仓内所有未闭环缺口登记为可追踪 `G-ID`，每条归属唯一子计划。子计划收口时同批：

1. verify PASS + WT-038x
2. `registry.md` 将该子计划名下全部 `G-ID` 标 `closed` 或显式 `wontfix`
3. 回写来源 WT/PLAN 遗留项为「已由 PLAN-038x 关闭」
4. `verify-plan-038.sh` 断言 closed 缺口不再以未关口吻出现在来源文档

## 二、子计划矩阵

| 编号 | 文件 | 交付 | 顺序 |
| --- | --- | --- | --- |
| [038a](./PLAN-038a-doc-status-sync.md) | 文档状态对齐 | 文件头/过时下一步与父纲领一致 | 1 |
| [038b](./PLAN-038b-plan037-docs.md) | PLAN-037 补档 | 纲领 + WT-037，不改行为 | 2 |
| [038c](./PLAN-038c-ops-hygiene.md) | 运维卫生 | 旧服务 disable、归档 --apply、STRICT_SAMPLE | 3 |
| [038d](./PLAN-038d-picture-tables.md) | 纯图片表 | OCR cell 网格 + table_cell_policy | 4 |
| [038e](./PLAN-038e-ppt-picture-ocr.md) | PPT 嵌图 OCR | 证明/加固 `_overlay_images` 链 | 5 |
| [038f](./PLAN-038f-layout-weak-items.md) | 版式弱项 | cap_body_gap / Figure 残影，或 wontfix | 6 |
| [038g](./PLAN-038g-product-polish.md) | 产品抛光 | 白牌/登录墙/术语表/会话取消/DOCX 续表 | 7 |

## 三、关闭协议

见总纲附计划；门禁实现见 `scripts/verify-plan-038.sh`。

## 四、非目标

- 复活空的 `docs/plans/PLAN-034-*` 目录
- 重写已关闭的 030/033/035/036 主线
- 提交 `glossaries/auto-proper-nouns.csv`

## 五、完成定义

- [registry.md](./registry.md) 覆盖全部 `G-*`（含 WONTFIX）
- 每个 `open` 缺口有且只有一个归属子计划
- `verify-plan-038.sh` PASS（可按子计划阶段分步放宽，最终 open 仅允许 INFO 人工项与显式等待确认的 OPS）
