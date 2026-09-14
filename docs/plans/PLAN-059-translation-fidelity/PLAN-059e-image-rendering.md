# PLAN-059e：图片 300 DPI、原图隔离与 OCR 嵌字适配

> 父计划：[PLAN-059](./README.md)  
> 状态：待批准  
> 依赖：059c/059d

## 交付

- 图片 OCR 和译后合成统一以 300 DPI 主图为输入；预览生成清晰主资源和按视口缩放的缩略图，二者不混用。
- 原始 PDF/DOCX/PPTX/media 使用只读 hash；擦除、翻译图片替换和导出全部写入派生工作目录。
- OCR 文本块按标题、轴标签、图例、面板字母、脚注等角色分层；字体适配使用 bounds、换行、行距、最小字号和溢出检测，禁止“一刀切”字号。

## 验收标准

- [ ] 主 OCR/合成资源 DPI=300；浏览器放大可读；原文源 hash 不变。
- [ ] 图片文字无溢出/遮挡；字号在角色上下限内，同角色差异不超过 0.75pt；不可适配时阻断而非缩到不可读。
- [ ] 图片翻译替换只出现在译文产物；失败、未译和降级状态进入 Manifest/QA。

## 验证、依赖与范围

- 验证：图片金标、DPI 检测、source hash、bbox fit/contrast/overflow 测试和 PDF 页面截图。
- 依赖：059c、059d。文件：`extensions/image_translate.py`、`image_tiles.py`、`role_fitter.py`、`scripts/apply-pdf2zh-preview-dpi.py`、测试夹具。
- 规模：Large。
