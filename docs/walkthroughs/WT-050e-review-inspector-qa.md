# WT-050e：检查器 / TM / QA

对应 [PLAN-050e](../plans/PLAN-050-qyunslation-ui-ux/PLAN-050e-review-inspector-qa.md)

- 抽屉 `#qy050-inspector`：摘要、对象页跳转、术语/TM 说明、QA
- QA / 导出门：`qyunslation.ui.qa`；阻断 → 禁止正式导出，允许审阅稿
- 精确 TM reuse 仍只在 sidecar `lookup`；本界面不自动套用语义命中
- 参考文献 PRESERVE 计数进入摘要 `refs_protected`
- 表/图专用编辑器：本号提供入口与状态，不重写 BabelDOC 单元格引擎
