# WT-046：文献 PDF 结构保真整改

日期：2026-09-11  
纲领：[PLAN-046](../plans/PLAN-046-literature-structure-fidelity/PLAN-046-literature-structure-fidelity.md)

## 实施记录

| 子计划 | 状态 | 交付 |
| --- | --- | --- |
| 046a | 已完成 | isolate 复原；COLUMN_CLUSTER_DRIFT；FIGURE_TIER_MAX_PX；先试排后擦；不裁字 |
| 046b | 已完成 | 段落再合并补丁；min_scale=0.8；药名漂移告警 |
| 046c | 已完成 | 列簇二次合并；墨迹并集 bbox；SPAN_ORDER_DRIFT |
| 046d | 已完成 | 竖排旋转；面板字母放宽；OCR 垃圾；object_qc |
| 046e | 已完成 | PLAN 目录、verify、WT、服务重启 |

## 缺陷对照（ljae439）

| 现象 | 对策 |
| --- | --- |
| 摘要 4pt 串行 + 孤立 of | 046b 段落合并 + min_scale |
| Table 1 `37. )` / 错列 | 046a 跳过坏表 → 046c 列合并后可再落笔 |
| 图竖排巨字 / 白块 | 046a 字号上限 + 试排跳过 → 046d 旋转 |
| A/B/C 与 (a) 不一 | 046d 面板正则 |
| F08 垃圾字 | 046d OCR 垃圾门禁 |
| imgtr object_qc 全空 | 046d C6→object_qc |

## 验证

```bash
bash scripts/verify-plan-046.sh
# 重译后对照双栏 PDF：摘要字号一致、表数值完整或整表英文、轴标签旋转贴合
```

## 部署

```bash
cp scripts/pdf2zh.service ~/.config/systemd/user/pdf2zh.service
systemctl --user daemon-reload
systemctl --user restart pdf2zh.service
```

旧译文不会自愈，须重新提交翻译。实样不入库。
