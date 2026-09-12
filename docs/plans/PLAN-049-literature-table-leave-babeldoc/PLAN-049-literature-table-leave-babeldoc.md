# PLAN-049：文献三线表交还 BabelDOC

> 状态：**已实现**（049e–i）+ **049i N= 回写 / 禁拆行压邻 / 表2 对行 / EASI 七列**
> 日期：2026-09-12
> 前置：[PLAN-046](../PLAN-046-literature-structure-fidelity/PLAN-046-literature-structure-fidelity.md)
> Skill：[SK-Q009](../../../.cursor/skills/table-translation-fidelity/SKILL.md)
> 验收：`bash scripts/verify-plan-049.sh`；证据 [WT-049](../../walkthroughs/WT-049-literature-table-leave-babeldoc.md)

## 目标

ljae439 第一次译稿（BabelDOC，无 `.tbltr`）表 1/3 列齐可读；047d 同行合并把列粘死，结构链再整区擦除重画后不如第一次。本期恢复「文献表默认不落笔」，堵住 047d 对短数字邻居的合并；049e 按原文列居中；049f 非汉字半角英文 + 原文视觉行对齐（NRS 续行、表3 不叠墨）；049g 用 HPD 补列、Noto 统一字体、原文三线补底线。

## Out of Scope

- 换模型；改上传原文
- Office / DOCX 表格重建（`docx_table_exec` 只服务 Word 真单元格）
- 放宽 `literature_paint_safe` 或整区 `paint_fitted_blocks`
- 监管表单（REGULATORY）仍走单元格回写

## 关键决策

| # | 决策 | 理由 |
| --- | --- | --- |
| D1 | 文献 `RESEARCH_ARTICLE` / `REVIEW_ARTICLE` 不 `redact`+`paint` | 第一次译稿证明段流够用；擦了只能画垃圾 |
| D2 | 047d 禁止合并含数字的同行邻居 | 列塌缩开关；保留无数字的行尾孤字（如 `of`） |
| D3 | 仅对窄矮表区做字号归一、不补翻 | 对应「表 2 只处理字号」；宽表（表 1/3）不动 |
| D4 | 不上 Office 表格 | 源是矢量 PDF，不是 `.docx` |
| D5 | 列居中只挪位、不整区重绘 | 字已在；擦整表只能画回垃圾 |
| D6 | 表内非汉字半角英文；049g 起一族 NotoSansSC | `china-s` 拉开拉丁；混 helv 造成字体不统一、子集缺字 |
| D7 | 基线跟原文视觉行 y | dest `max(y1)` 会导致邻行叠墨 |
| D8 | 数据 `N=` 续行不 skip；表头 `(N=130)` **按格回写** | 邻行 `band=8` 会擦掉 N=；skip = 丢行 |
| D9 | 列几何 HPD 优先，空隙回退 | 表3 七列空隙会并；HPD 缓存 4/7 列已验证 |
| D10 | 三线横线从原文 drawings 重描 | 译文底线右段被 BabelDOC 截断 |
| D11 | 落笔单元是 HPD 格，含表头；溢出换行不缩字 | 049g 只挪数据、表头原位换字体 → 重叠/错列观感 |

## 子计划

| ID | 文件 | 交付 |
| --- | --- | --- |
| 049a | [PLAN-049a-skip-literature-paint.md](./PLAN-049a-skip-literature-paint.md) | 文献表 `literature_leave_babeldoc`，禁止整区擦除 |
| 049b | [PLAN-049b-047d-numeric-guard.md](./PLAN-049b-047d-numeric-guard.md) | 047d Pass1/2 数字邻居不合并 |
| 049c | [PLAN-049c-table2-font-only.md](./PLAN-049c-table2-font-only.md) | 窄矮表区 `allow_translate=False` 字号归一 |
| 049d | [PLAN-049d-verify-docs.md](./PLAN-049d-verify-docs.md) | verify / Skill / WT |
| 049e | [PLAN-049e-column-center.md](./PLAN-049e-column-center.md) | 原文列几何；数据列居中；禁止整区擦除 |
| 049f | [PLAN-049f-latin-ascii-origin-rows.md](./PLAN-049f-latin-ascii-origin-rows.md) | 西文半角 + helv；原文行 y；N= 续行 |
| 049g | [PLAN-049g-hpd-font-rules.md](./PLAN-049g-hpd-font-rules.md) | HPD 补列；Noto 统一字体；原文三线 |
| 049h | [PLAN-049h-hpd-cell-write.md](./PLAN-049h-hpd-cell-write.md) | 表头按格写；字号地板；Visit 锁列 |
| 049i | [PLAN-049i-n-eq-overlap-easi.md](./PLAN-049i-n-eq-overlap-easi.md) | N= 回写；禁拆行压邻；表2 对行；EASI 七列 |

## 变更文件清单

| 路径 | 操作 | 用途 |
| --- | --- | --- |
| `scripts/pdf_table_translate.py` | 修改 | 文献跳过落笔 |
| `scripts/pdf_table_normalize.py` | 修改 | `allow_translate` |
| `scripts/apply-pdf2zh-047d-para-layout.py` | 修改 | 数字邻居门禁 |
| `scripts/pdf_table_column_center.py` | 新增/修改 | 049e 列内居中；049f 西文半角 + 原文行 |
| `tests/structure/test_plan049_literature_leave.py` | 新增 | 文献不整区涂改；列中心落入中带 |
| `scripts/verify-plan-049.sh` | 新增 | 门禁 |
| `.cursor/skills/table-translation-fidelity/*` | 修改 | 阶梯 0 + 列居中只挪位 |

## 验证清单

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | `bash scripts/verify-plan-049.sh` | 全部 PASS |
| V2 | 定向 pytest `test_plan049*` `test_plan046b*` `test_plan041_quality_gates` | 不破坏监管落笔 |
| V3 | 部署后重译或后处理已有 mono | 表 1/3 列齐；NRS 两行；西文半角；表3 不叠墨；底线完整；字体一族 |

## 回滚预案

1. 还原 `pdf_table_translate.py` 文献早退与 047d 数字门禁
2. `bash scripts/deploy-translate-stack.sh`

## 影响范围

- `pdf2zh.service`（047d ExecStartPre）+ 表格后处理
- 不改 sidecar 嵌字、不改 Caddy
