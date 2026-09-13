# WT-049：文献三线表交还 BabelDOC

对应 [PLAN-049](../plans/PLAN-049-literature-table-leave-babeldoc/PLAN-049-literature-table-leave-babeldoc.md)。

## 执行摘要

文献表不再整区擦除重画；047d 停止合并同行短数字；窄矮表仅字号归一。049e 按原文列居中；049f 西文半角 + 原文视觉行 y；049g HPD 补列、Noto 一族、原文三线补底线；049h 表头按格写；049i 表头 N= 回写、禁拆行压邻、表2 对行、EASI 七列；049j 按 origin 形态切粘连小数、七槽表头、Q4WSafety 拆分。监管表单单元格回写不变。

## 变更明细

| 文件 | 摘要 |
| --- | --- |
| `scripts/pdf_table_translate.py` | `literature_leave_babeldoc`；宽表不走 `.tblnorm`；049e/f 列居中 |
| `scripts/pdf_table_normalize.py` | `allow_translate` |
| `scripts/pdf_table_column_center.py` | 列居中；`normalize_ascii`；HPD 列；Noto；原文三线；049i N=/拆行/EASI；049j 形态切词 |
| `scripts/apply-pdf2zh-047d-para-layout.py` | `_numeric_cell` 门禁 |
| `tests/structure/test_plan049_literature_leave.py` | 半角 / NRS 续行 / Q4W 还原 / 049j 粘连 |
| `.cursor/skills/table-translation-fidelity/` | 铁律 H/I/L + 踩坑 |

## 验证结果

| # | 项 | 结果 | 备注 |
| --- | --- | --- | --- |
| V1 | `verify-plan-049.sh` | PASS | 含 049f |
| V2 | pytest 049 + 041（非实样） | PASS | 监管落笔仍写出 `.tbltr` |
| V3 | 对已塌列的 `36cc341b` `.mono` 重跑表格链 | PASS | 049a：无多列数据时 `dest==src` |
| V4 | 049e 后处理 `9a4d2075` mono | PASS | 表1/3 数据格落入原文列 |
| V5 | 049f 后处理 `9a4d2075` mono | PASS | NRS 两行三列；半角；Dose=`Q4W`；表体无全角括号 |
| V6 | 重译 ljae439 目视表 1/3 | 待手测 | 新作业走 047d + 049e/f/g |
| V7 | 049g 后处理 `6ab18daa` mono | PASS | 表1/3 `cols_source=hpd`；表3 七列 x≈77/135/203/272/351/430/496；底线 74.8–514.8；font=`NotoSansSCStatic-Regular` |
| V8 | 049h 表头按格 + DLQI 字号 | PASS | 表3 表头 剂量/访视/ADA/nAb/浓度/IGA/EASI 各列；Visit 仅一列；DLQI 8pt 两行 |
| V9 | 049i N= 回写 / 禁拆行 / 表2 / EASI | PASS | 回放 raw/049h：表1 `(N=130)` y≈104；DLQI 不压瘙痒；表2 行 y=624/640/651/658；表3 访视 x≈135、浓度/IGA/EASI 分列 |
| V10 | 合 main + 生产部署 | PASS | `main` `b5e1dc6`（049 merge `46baf41`）；`pdf2zh`/`qyunslation-office` active；`:7860` 200；sidecar 指纹一致 |
| V11 | 049j 粘连切分 / 七列 | PASS | 单测拆 `90.0111.2`；回放 ffc3 mono 表3：`90.0`/`1`/`11.2` 分列 x≈352/432/500；无三位小数 token；IGA/EASI 独立 |

## 生产

- 远程：https://github.com/Charlie780405/Qyunslation/commit/b5e1dc6
- 部署：`bash scripts/deploy-translate-stack.sh`（2026-09-12；049j 后再部署一次）
- 服务：`pdf2zh.service` + `qyunslation-office.service` active

## 回归确认

- 041 硬失败仍不写半成品
- `NOT_A_TABLE` 仍交图片链

## 已知限制

- 表头 `(N=130)`：049i 按三数据列回写；擦除带夹邻行
- 表1 底线缺右段：049g 从原文重描
- 表2：矮窄 `not_a_table` 仍按原文行 y 居中（大图假表仍跳过）
- 046b `min_scale==0.8` 断言与现网 `0.12` 不一致，本期未动

## 遗留问题与下阶段输入

- [ ] 用户重译 ljae439，对照第一次译稿表头 `N=` 与表1 底线
- Office 表格重建明确不做
