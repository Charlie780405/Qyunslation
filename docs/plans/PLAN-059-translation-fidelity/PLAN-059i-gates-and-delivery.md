# PLAN-059i：多格式金标、全量门禁与交付

> 父计划：[PLAN-059](./README.md)
> 状态：待执行（依赖 059g/059h 的真实证据）
> 依赖：059b–059h

## 交付

- 建立不提交版权文件的金标索引，至少覆盖 PDF 文献/综述、临床/监管表单、DOCX、PPTX、poster、单图和纯图片页，中英双向。
- 运行结构、文本、表格、图片、参考文献、样式、布局、模型 trace、性能和浏览器 smoke 门禁，写入 WT-059。
- 更新 `docs/plans/README.md`、必要的 UI/Manifest contract、部署脚本和回滚说明；以独立提交合入前审查。

## 验收标准

- [ ] 12 项错误和 2 项 P0 UI 问题均有 PASS 证据；任何 FAIL/BLOCKED 不得标记完成。
- [ ] 生产部署前完成强制刷新、重新登录、上传、翻译、下载、参考文献 preserve、图片/表格视觉抽查。
- [ ] 记录提交 SHA、服务重启时间、健康检查、日志异常、回滚目标和金标结果。

## 验证、依赖与范围

- 验证：聚焦测试→结构全量→PLAN-028/029/030e→034/041/045/050/058→PLAN-059 门禁；公网入口 HTTP/健康检查。
- 依赖：所有前序子计划。文件：`tests/`、`scripts/verify-plan-059.sh`、`docs/walkthroughs/WT-059-translation-fidelity.md`。
- 规模：Large；真实金标和 LIVE 资源缺失时只报告 BLOCKED。
