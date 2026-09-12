# PLAN-048 表格译文保真：HPD 逻辑网格

## 目标

借鉴 Hermes 文献入库 HPD 视觉解析拿表格行列结构；PDF 文字层出精确字形与墨迹框；对齐后落笔。沉淀 SK-Q009。

## 根因

- `_merge_column_clusters` 无法区分格内碎片间隙与真列间隙 → 串格
- 047e 放宽 `COLUMN_CLUSTER_DRIFT` 让坏结构过闸落笔
- `caption_rules` 假阳性把图当表
- 区域左边界切列 → 双渲染器同表

## 子计划

| ID | 标题 | 状态 |
| --- | --- | --- |
| 048a | HPD 网格客户端与缓存 | 实现 |
| 048b | 行几何 × 列 HPD 对齐；删合并簇 | 实现 |
| 048c | 三闸门 + geometry_center 不落笔 | 实现 |
| 048d | 左边界扩展 + 降级阶梯 | 实现 |
| 048e | 角色字号归一 + 漏译 | 实现 |
| 048f | SK-Q009 skill | 实现 |
| 048g | 文档与验收 | 本文件 |

## 约束

- 原文与双栏左列不改
- HPD 文本不进译文
- 禁止运行时 `page.find_tables()`
- 样本走 `QYUNSLATION_PLAN048_SAMPLE`
- 模型不动；不触碰 PLAN-044 REGULATORY 软门禁

## 验收

`bash scripts/verify-plan-048.sh`
