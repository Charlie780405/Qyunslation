# PLAN-060c：译前术语策略接入

> 父计划：[PLAN-060](./README.md)

- 每份文件开始时在公司共享项目解析正式词、别名与缩写，并编译只读策略包。
- PDF 通过每任务输出目录的 glossary CSV 注入；既有用户 glossary 被保留。DOCX、PPTX、图片 OCR 和表格/脚注路径向 sidecar 传递同一策略与版本。独立图片、PDF 图像及 Office 内嵌图片在术语解析前执行受上限保护的 OCR（默认每文件 12 个资源），使仅出现在图内的已确认词也能成为硬约束；可用 `QYUNSLATION_TERM_POLICY_OCR_IMAGE_LIMIT=0` 显式关闭。
- 已确认术语再次出现走确定性精确/别名路径，不调用 bge-m3；策略版本是任务和缓存边界。
- 词库失效或降级不制作硬译法；翻译仍可完成并在 UI 明示。
