# qyunslation Skill Registry

SK-ID 前缀 `SK-Q`（避免与 qyunsgen `SK-A/B/C/D/E/F/G` 冲突）。

| SK-ID | slug | 状态 | canonical | pitfalls SSOT |
| --- | --- | --- | --- | --- |
| SK-Q001 | scanned-doc-layout-fidelity | active | 本仓 | pitfalls.md |
| SK-Q002 | image-overlay-translation | active | 本仓 | pitfalls.md |
| SK-Q003 | pdf-regulatory-form-fidelity | active | 本仓 | pitfalls.md |
| SK-Q004 | translate-stack-process-boundary | active | 本仓 | pitfalls.md |
| SK-Q005 | babeldoc-patch-safety | active | 本仓 | pitfalls.md |
| SK-Q006 | literature-paragraph-layout | active | 本仓 | pitfalls.md |
| SK-Q007 | translation-content-integrity | active | 本仓 | pitfalls.md |
| SK-Q008 | translation-pitfall-capture | active | 本仓 | pitfalls.md |
| SK-Q009 | table-translation-fidelity | active | 本仓 | pitfalls.md |

## 审计

| 日期 | 动作 |
| --- | --- |
| 2026-09-05 | 登记 SK-Q001（PLAN-010） |
| 2026-09-06 | 登记 SK-Q002（PLAN-022） |
| 2026-09-06 | SK-Q002 增补按通道纯色 / 可用区 / QC 六项（PLAN-023） |
| 2026-09-06 | SK-Q002 增补字号层级与全屏裁切铁律（PLAN-024） |
| 2026-09-06 | SK-Q002 增补墨迹锚点对齐与 C8（PLAN-025） |
| 2026-09-06 | SK-Q002 铁律按主题重组；补主行/左对齐组/墨迹度量与 C9（PLAN-025b） |
| 2026-09-06 | SK-Q002 增补通用原则/自检清单；文字带填充、竖向三段式、C10（PLAN-026） |
| 2026-09-06 | SK-Q002 增补文档内嵌图 Occurrence/Alpha/矢量 Fail-Closed/预扫描代际（PLAN-027） |
| 2026-09-06 | SK-Q002 增补 OCR 依赖转正 / 引擎可观测 / 跨 venv 门控铁律（PLAN-027f） |
| 2026-09-06 | SK-Q002 增补 300 DPI 回嵌与擦除残留铁律（PLAN-027g） |
| 2026-09-09 | SK-Q002 C3 改 draw_bbox 小窗，避免流程图短标签假空白（PLAN-033k） |
| 2026-09-09 | SK-Q002 C6 短边参照并映射 FONT_BELOW，触发高分率重绘（PLAN-033l） |
| 2026-09-09 | SK-Q002 线保护不覆盖竖排字，避免擦后残影回贴（PLAN-033） |
| 2026-09-11 | SK-Q002 双语原文不可变（横跨框裁右半）+ 禁止译后展开 Q2W（PLAN-033c/045a） |
| 2026-09-11 | 登记 SK-Q003（PLAN-041 监管表单保真） |
| 2026-09-12 | 登记 SK-Q004–SK-Q008；增补 SK-Q002/SK-Q003（PLAN-047） |
| 2026-09-12 | SK-Q004 进程边界指纹门禁；SK-Q005 never-drop；SK-Q008 capture+hooks |
| 2026-09-12 | 登记 SK-Q009 table-translation-fidelity（PLAN-048 HPD 网格） |
| 2026-09-12 | promote SIG-INBOX-UNMATCHED → SK-Q008（PLAN-047g） |
| 2026-09-13 | 复活 PLAN-034 医药 MVP 纲领落盘（文档阶段；Skill 待 034d0 实现后沉淀） |
| 2026-09-13 | PLAN-034d0 术语 SSOT 实现（四层预置 + session 导出 + service 桥接；不新建 Skill） |
